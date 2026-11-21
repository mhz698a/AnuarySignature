"""Validated, approval-gated orders from the private Structure repository.

Supported actions only create or update dependent-drive data. No delete, remove,
move, recycle, wipe, or arbitrary command operation is supported.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from engines.character_credential_backup import (
    ALLOWED_IMAGE_EXTENSIONS,
    MAX_IMAGE_BYTES,
    CharacterCredentialBackupService,
)
from engines.structure_paths import get_structure_dir, get_structure_repo_root


ORDER_SCHEMA_VERSION = 1
ORDER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{7,79}$")
CHARACTER_STRING_FIELDS = {
    "icon_path",
    "background_path",
    "short_masked_alterego",
    "color_group",
    "secondary_color",
    "profession_group",
    "time_of_year",
}
CHARACTER_ALLOWED_COLORS = {
    "", "rojo", "azul", "verde", "amarillo", "dorado", "naranja",
    "morado", "rosa", "blanco", "negro", "gris", "marrón",
    "turquesa", "cian", "magenta", "arcoiris",
}
CHARACTER_ALLOWED_SEASONS = {"", "invierno", "primavera", "verano", "otoño"}


class StructureOrderError(RuntimeError):
    """Raised when an incoming Structure order cannot be safely applied."""


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    content = (
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    _atomic_write_bytes(path, content)


class StructureOrderService:
    """Load, validate, preview and apply one explicitly approved order at a time."""

    def __init__(
        self,
        dependent_path: str | Path,
        character_manager,
        structure_dir: str | Path | None = None,
        state_path: str | Path | None = None,
        backup_root: str | Path | None = None,
    ) -> None:
        self.dependent_root = Path(dependent_path).expanduser().resolve()
        self.structure_dir = (
            Path(structure_dir).expanduser().resolve()
            if structure_dir is not None
            else get_structure_dir().resolve()
        )
        self.orders_root = self.structure_dir / "orders"
        self.pending_root = self.orders_root / "pending"
        self.results_root = self.orders_root / "results"
        self.character_manager = character_manager
        app_data_root = get_structure_repo_root().parent
        self.state_path = (
            Path(state_path)
            if state_path is not None
            else app_data_root / "OrderState" / "applied_orders.json"
        )
        self.backup_root = (
            Path(backup_root)
            if backup_root is not None
            else app_data_root / "Backups" / "DependentOrders"
        )

    @staticmethod
    def _is_plain_directory(path: Path) -> bool:
        try:
            info = path.lstat()
        except OSError:
            return False
        return (
            stat.S_ISDIR(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and not bool(getattr(info, "st_file_attributes", 0) & 0x400)
        )

    @staticmethod
    def _is_plain_file(path: Path) -> bool:
        try:
            info = path.lstat()
        except OSError:
            return False
        return (
            stat.S_ISREG(info.st_mode)
            and not stat.S_ISLNK(info.st_mode)
            and not bool(getattr(info, "st_file_attributes", 0) & 0x400)
        )

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return {"schema_version": 1, "applied": {}}
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StructureOrderError(
                f"No se pudo leer el registro local de órdenes aplicadas: {error}"
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("applied"), dict):
            raise StructureOrderError(
                "El registro local de órdenes aplicadas tiene un formato inválido."
            )
        return payload

    @staticmethod
    def _safe_relative_path(raw_path: str) -> PurePosixPath:
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise StructureOrderError("La ruta relativa de la orden está vacía.")
        if "\\" in raw_path or raw_path.startswith(("/", "\\")):
            raise StructureOrderError(
                "Las rutas de órdenes deben ser relativas y utilizar separadores '/'."
            )
        relative = PurePosixPath(raw_path)
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise StructureOrderError(
                "La ruta contiene componentes absolutos o traversal no permitidos."
            )
        if relative.parts and re.match(r"^[A-Za-z]:", relative.parts[0]):
            raise StructureOrderError("No se permiten rutas con unidad de disco.")
        return relative

    def _resolve_dependent_path(self, raw_path: str) -> Path:
        relative = self._safe_relative_path(raw_path)
        candidate = (self.dependent_root / Path(*relative.parts)).resolve()
        if not candidate.is_relative_to(self.dependent_root):
            raise StructureOrderError(
                "La ruta resuelta sale de la unidad dependiente configurada."
            )
        return candidate

    @staticmethod
    def _validate_character_fields(fields: dict[str, Any]) -> None:
        if not isinstance(fields, dict) or not fields:
            raise StructureOrderError(
                "La orden debe incluir al menos un campo de credencial para actualizar."
            )
        unknown = set(fields) - CHARACTER_STRING_FIELDS - {"type_underwear"}
        if unknown:
            if unknown & {"delete", "remove", "move", "unlink"}:
                raise StructureOrderError(
                    "Las órdenes de eliminar, borrar o mover están deshabilitadas."
                )
            raise StructureOrderError(
                "Campos no permitidos en credenciales: " + ", ".join(sorted(unknown))
            )

        for field_name in CHARACTER_STRING_FIELDS & set(fields):
            value = fields[field_name]
            if not isinstance(value, str):
                raise StructureOrderError(
                    f"El campo {field_name} debe ser texto."
                )
        for field_name in ("color_group", "secondary_color"):
            if field_name in fields and fields[field_name] not in CHARACTER_ALLOWED_COLORS:
                raise StructureOrderError(
                    f"Color no permitido para {field_name}: {fields[field_name]}"
                )
        if "time_of_year" in fields and fields["time_of_year"] not in CHARACTER_ALLOWED_SEASONS:
            raise StructureOrderError("El valor de time_of_year no es válido.")
        if "type_underwear" in fields:
            value = fields["type_underwear"]
            if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
                raise StructureOrderError(
                    "type_underwear debe ser una lista de textos."
                )

    def validate_order(self, order: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(order, dict):
            raise StructureOrderError("La orden debe ser un objeto JSON.")
        if order.get("schema_version") != ORDER_SCHEMA_VERSION:
            raise StructureOrderError("Versión de esquema de órdenes no compatible.")

        order_id = order.get("id")
        if not isinstance(order_id, str) or not ORDER_ID_PATTERN.fullmatch(order_id):
            raise StructureOrderError(
                "El identificador debe contener entre 8 y 80 caracteres alfanuméricos, '_' o '-'."
            )
        for field_name in ("title", "description", "created_at"):
            if not isinstance(order.get(field_name), str) or not order[field_name].strip():
                raise StructureOrderError(f"La orden no contiene {field_name}.")

        try:
            created_at = datetime.fromisoformat(order["created_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise StructureOrderError("created_at no es una fecha ISO-8601 válida.") from error

        expires_at = order.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            except ValueError as error:
                raise StructureOrderError("expires_at no es una fecha ISO-8601 válida.") from error
            now = datetime.now(timezone.utc)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=timezone.utc)
            if expiry <= now:
                raise StructureOrderError("La orden ya expiró.")

        operation = order.get("operation")
        if not isinstance(operation, dict):
            raise StructureOrderError("La orden no contiene un objeto operation.")
        operation_type = operation.get("type")

        if operation_type == "update_character_credential":
            target = operation.get("target")
            if not isinstance(target, dict):
                raise StructureOrderError("Falta el personaje de destino.")
            try:
                year = int(target.get("year"))
            except (TypeError, ValueError) as error:
                raise StructureOrderError("El año del personaje no es válido.") from error
            if not isinstance(target.get("name"), str) or not target["name"].strip():
                raise StructureOrderError("Falta el nombre del personaje.")
            if not isinstance(target.get("alterego"), str) or not target["alterego"].strip():
                raise StructureOrderError("Falta el alterego del personaje.")
            fields = operation.get("fields")
            self._validate_character_fields(fields)
            return {
                "id": order_id,
                "title": order["title"].strip(),
                "description": order["description"].strip(),
                "operation_type": operation_type,
                "target": {
                    "year": year,
                    "name": target["name"].strip(),
                    "alterego": target["alterego"].strip(),
                },
                "fields": dict(fields),
            }

        if operation_type == "replace_character_asset":
            target = operation.get("target")
            if not isinstance(target, dict):
                raise StructureOrderError("Falta el personaje de destino.")
            try:
                year = int(target.get("year"))
            except (TypeError, ValueError) as error:
                raise StructureOrderError("El año del personaje no es válido.") from error
            if not isinstance(target.get("name"), str) or not target["name"].strip():
                raise StructureOrderError("Falta el nombre del personaje.")
            if not isinstance(target.get("alterego"), str) or not target["alterego"].strip():
                raise StructureOrderError("Falta el alterego del personaje.")
            field_name = operation.get("field")
            if field_name not in {"icon_path", "background_path"}:
                raise StructureOrderError(
                    "field debe ser icon_path o background_path."
                )
            asset_relative = self._safe_relative_path(
                operation.get("asset_path", "")
            )
            if len(asset_relative.parts) != 2 or asset_relative.parts[0] != "assets":
                raise StructureOrderError(
                    "La ruta de imagen debe tener el formato assets/<archivo>."
                )
            if (
                not self._is_plain_directory(self.orders_root)
                or not self._is_plain_directory(self.orders_root / "assets")
            ):
                raise StructureOrderError(
                    "La carpeta orders/assets no es un directorio regular."
                )
            source_candidate = self.orders_root / Path(*asset_relative.parts)
            if not self._is_plain_file(source_candidate):
                raise StructureOrderError(
                    "El recurso de imagen debe ser un archivo regular, sin enlaces simbólicos."
                )
            source_path = source_candidate.resolve()
            if not source_path.is_relative_to(self.orders_root.resolve()):
                raise StructureOrderError(
                    "La imagen resuelta sale del repositorio local de Structure."
                )
            if (
                source_path.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS
                or source_path.stat().st_size <= 0
                or source_path.stat().st_size > MAX_IMAGE_BYTES
            ):
                raise StructureOrderError(
                    "La imagen de la orden debe tener un formato admitido y pesar "
                    f"como máximo {MAX_IMAGE_BYTES // (1024 * 1024)} MB."
                )
            return {
                "id": order_id,
                "title": order["title"].strip(),
                "description": order["description"].strip(),
                "operation_type": operation_type,
                "target": {
                    "year": year,
                    "name": target["name"].strip(),
                    "alterego": target["alterego"].strip(),
                },
                "field": field_name,
                "asset_path": asset_relative.as_posix(),
            }

        if operation_type == "update_dependent_json":
            relative = self._safe_relative_path(operation.get("path", ""))
            if relative.name.startswith("__") and relative.name.endswith("__.json"):
                raise StructureOrderError(
                    "Los JSON de credenciales de personajes deben modificarse con "
                    "update_character_credential para mantener sincronizada la caché."
                )
            if relative.suffix.casefold() != ".json":
                raise StructureOrderError(
                    "update_dependent_json solo puede modificar archivos .json."
                )
            document = operation.get("document")
            if not isinstance(document, (dict, list)):
                raise StructureOrderError(
                    "document debe ser un objeto o una lista JSON."
                )
            return {
                "id": order_id,
                "title": order["title"].strip(),
                "description": order["description"].strip(),
                "operation_type": operation_type,
                "path": relative.as_posix(),
                "document": document,
            }

        if operation_type == "create_directory":
            relative = self._safe_relative_path(operation.get("path", ""))
            return {
                "id": order_id,
                "title": order["title"].strip(),
                "description": order["description"].strip(),
                "operation_type": operation_type,
                "path": relative.as_posix(),
            }

        if operation_type in {
            "delete", "delete_file", "delete_directory", "remove",
            "move", "rename", "unlink", "wipe", "trash",
        }:
            raise StructureOrderError(
                "Las órdenes de eliminar, borrar, mover o renombrar están "
                "deshabilitadas. Esta versión no ejecuta operaciones destructivas."
            )

        raise StructureOrderError(
            f"Tipo de operación no permitido: {operation_type!r}. "
            "Solo se aceptan update_character_credential, replace_character_asset, "
            "update_dependent_json y create_directory."
        )

    @staticmethod
    def _is_plain_directory(path: Path) -> bool:
        """Reject symlinks and Windows reparse-point directories."""
        import stat

        try:
            info = path.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode):
            return False
        if getattr(info, "st_file_attributes", 0) & 0x400:
            return False
        return stat.S_ISDIR(info.st_mode)

    def _find_character_credential(
        self,
        target: dict[str, Any],
        cache_records: list[dict[str, Any]] | None = None,
    ) -> tuple[Path, dict]:
        """Resolve a character directly on disk; the six-item UI cache is not authoritative."""
        year = int(target["year"])
        year_root = self.dependent_root / str(year)
        prefix = f"{max(0, year - 2003):02d}"
        album_root = year_root / f"{prefix}. album"

        if not self._is_plain_directory(year_root) or not self._is_plain_directory(album_root):
            raise StructureOrderError(
                f"No existe el directorio de álbum para {year} en la unidad dependiente."
            )

        matches: list[tuple[Path, dict[str, Any]]] = []
        try:
            character_directories = sorted(
                (
                    path for path in album_root.iterdir()
                    if self._is_plain_directory(path)
                ),
                key=lambda path: path.name.casefold(),
            )
        except OSError as error:
            raise StructureOrderError(
                f"No se pudieron enumerar los personajes del año {year}: {error}"
            ) from error

        for character_dir in character_directories:
            folder_name = character_dir.name
            folder_prefix = f"{prefix}. "
            if not folder_name.startswith(folder_prefix):
                continue
            if folder_name.count(";") != 4:
                continue
            parts = folder_name[len(folder_prefix):].split(";")
            if len(parts) != 5:
                continue
            raw_position, folder_alterego, folder_name_value, birthday, raw_age = parts
            try:
                int(raw_position)
                int(raw_age)
                datetime.strptime(birthday, "%Y-%m-%d")
            except (TypeError, ValueError):
                continue

            if (
                folder_name_value.casefold() != target["name"].casefold()
                or folder_alterego.casefold() != target["alterego"].casefold()
            ):
                continue

            expected_json = character_dir / f"__{folder_name_value}__.json"
            if expected_json.is_file():
                credential_path = expected_json
            else:
                try:
                    json_candidates = sorted(
                        path for path in character_dir.glob("__*.json")
                        if path.is_file() and not path.is_symlink()
                    )
                except OSError as error:
                    raise StructureOrderError(
                        f"No se pudo localizar la credencial de {folder_name_value}: {error}"
                    ) from error
                if len(json_candidates) != 1:
                    raise StructureOrderError(
                        f"La carpeta de {folder_name_value} no contiene una credencial "
                        "única __*.json."
                    )
                credential_path = json_candidates[0]

            if not self._is_plain_file(credential_path):
                raise StructureOrderError(
                    "La credencial debe ser un archivo regular, no un enlace simbólico."
                )
            credential_path = credential_path.resolve()
            if not credential_path.is_relative_to(self.dependent_root):
                raise StructureOrderError(
                    "La credencial no es un archivo regular dentro de la unidad dependiente."
                )
            try:
                payload = json.loads(credential_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise StructureOrderError(
                    f"No se pudo leer la credencial de {folder_name_value}: {error}"
                ) from error

            character_data = payload.get("character_data")
            if not isinstance(character_data, dict):
                raise StructureOrderError(
                    f"La credencial de {folder_name_value} no contiene character_data."
                )

            disk_name = str(character_data.get("name") or folder_name_value)
            disk_alterego = str(character_data.get("alterego") or folder_alterego)
            if (
                disk_name.casefold() != target["name"].casefold()
                or disk_alterego.casefold() != target["alterego"].casefold()
            ):
                raise StructureOrderError(
                    "El contenido de la credencial no coincide con el personaje "
                    "declarado en el nombre de carpeta."
                )

            runtime_character = dict(character_data)
            runtime_character.update({
                "year": year,
                "name": disk_name,
                "alterego": disk_alterego,
                "position": int(raw_position),
                "birthday": birthday,
                "age": int(raw_age),
                "character_json_path": str(credential_path.resolve()),
            })
            matches.append((credential_path.resolve(), runtime_character))

        if len(matches) != 1:
            raise StructureOrderError(
                "El personaje no se encontró de forma única en el directorio del año. "
                "No se modificó ningún archivo."
            )

        credential_path, disk_character = matches[0]
        if not credential_path.is_relative_to(self.dependent_root):
            raise StructureOrderError(
                "La credencial del personaje está fuera de la unidad dependiente."
            )

        candidate_records = (
            cache_records
            if cache_records is not None
            else self.character_manager._cache.get(str(year), [])
        )
        cached_match = next(
            (
                item
                for item in candidate_records
                if str(item.get("name", "")).casefold() == target["name"].casefold()
                and str(item.get("alterego", "")).casefold() == target["alterego"].casefold()
            ),
            None,
        )
        if cached_match is not None:
            cached_match.update({
                key: value for key, value in disk_character.items()
                if key in {
                    "year", "name", "alterego", "character_json_path",
                    "icon_path", "background_path", "color_group", "secondary_color",
                }
            })
            return credential_path, cached_match

        return credential_path, disk_character

    def find_character_credential(
        self,
        target: dict[str, Any],
        cache_records: list[dict[str, Any]] | None = None,
    ) -> tuple[Path, dict]:
        """Public, read/write-safe resolver for one exact year/name/alterego identity."""
        return self._find_character_credential(target, cache_records=cache_records)

    def _create_prechange_backup(
        self,
        order_id: str,
        target_path: Path,
        current_bytes: bytes,
    ) -> dict[str, str]:
        relative = target_path.resolve().relative_to(self.dependent_root)
        backup_path = self.backup_root / order_id / Path(*relative.parts)
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if backup_path.exists():
            raise StructureOrderError(
                "Ya existe un respaldo previo para esta orden y ruta. "
                "Se bloqueó el reintento para no sobrescribir el estado anterior; "
                "revisa el resultado o el intento parcial."
            )
        _atomic_write_bytes(backup_path, current_bytes)
        return {
            "backup_path": str(backup_path),
            "sha256": hashlib.sha256(current_bytes).hexdigest(),
            "dependent_relative_path": relative.as_posix(),
        }

    def _write_result(self, order_id: str, payload: dict[str, Any]) -> None:
        if not self._is_plain_directory(self.orders_root):
            raise StructureOrderError(
                "El directorio raíz de órdenes no es un directorio regular."
            )
        if not self.results_root.exists():
            self.results_root.mkdir(parents=True, exist_ok=False)
        if not self._is_plain_directory(self.results_root):
            raise StructureOrderError(
                "El directorio de resultados no es un directorio regular."
            )
        result_path = self.results_root / f"{order_id}.json"
        if result_path.exists():
            raise StructureOrderError(
                f"Ya existe un resultado para la orden {order_id}; no se sobrescribirá."
            )
        _atomic_write_json(result_path, payload)

    def _apply_credential_update(self, validated: dict[str, Any]) -> dict[str, Any]:
        credential_path, cached_character = self._find_character_credential(
            validated["target"]
        )
        try:
            payload = json.loads(credential_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StructureOrderError(
                f"No se pudo leer la credencial antes de modificarla: {error}"
            ) from error
        character_data = payload.get("character_data")
        if not isinstance(character_data, dict):
            raise StructureOrderError("La credencial no contiene character_data.")

        for asset_field in ("icon_path", "background_path"):
            if asset_field not in validated["fields"]:
                continue
            asset_value = validated["fields"][asset_field]
            if not asset_value:
                continue
            asset_candidate = Path(asset_value).expanduser()
            if not asset_candidate.is_absolute():
                asset_candidate = credential_path.parent / asset_candidate
            asset_resolved = asset_candidate.resolve()
            if (
                not asset_resolved.is_relative_to(self.dependent_root)
                or not asset_resolved.is_file()
                or asset_resolved.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS
            ):
                raise StructureOrderError(
                    f"{asset_field} debe apuntar a una imagen existente dentro "
                    "de la unidad dependiente. Esta orden no copia ni descarga "
                    "archivos de imagen."
                )

        backup = self._create_prechange_backup(
            validated["id"],
            credential_path,
            credential_path.read_bytes(),
        )
        character_data.update(validated["fields"])
        _atomic_write_json(credential_path, payload)

        cached_character.update(validated["fields"])
        self.character_manager.save_cache_file()

        backup_warning = ""
        try:
            backup_result = CharacterCredentialBackupService(
                self.dependent_root,
                structure_dir=self.structure_dir,
            ).backup_character(cached_character)
        except Exception as error:
            # The dependent credential is already safely updated and its previous
            # version is backed up in AppData; do not make the order retryable.
            backup_result = None
            backup_warning = str(error)

        return {
            "operation": validated["operation_type"],
            "dependent_relative_path": credential_path.relative_to(
                self.dependent_root
            ).as_posix(),
            "backup": backup,
            "updated_fields": sorted(validated["fields"]),
            "character_backup": backup_result,
            "character_backup_warning": backup_warning,
        }

    def _apply_character_asset_replacement(
        self,
        validated: dict[str, Any],
    ) -> dict[str, Any]:
        credential_path, cached_character = self._find_character_credential(
            validated["target"]
        )
        try:
            payload = json.loads(credential_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StructureOrderError(
                f"No se pudo leer la credencial antes de cambiar su imagen: {error}"
            ) from error

        character_data = payload.get("character_data")
        if not isinstance(character_data, dict):
            raise StructureOrderError("La credencial no contiene character_data.")

        asset_relative = PurePosixPath(validated["asset_path"])
        if (
            len(asset_relative.parts) != 2
            or asset_relative.parts[0] != "assets"
            or not self._is_plain_directory(self.orders_root / "assets")
        ):
            raise StructureOrderError(
                "La carpeta de recursos de órdenes ya no es válida."
            )
        asset_candidate = self.orders_root / Path(*asset_relative.parts)
        if not self._is_plain_file(asset_candidate):
            raise StructureOrderError(
                "La imagen de la orden ya no es un archivo regular."
            )
        asset_path = asset_candidate.resolve()
        if not asset_path.is_relative_to(self.orders_root.resolve()):
            raise StructureOrderError(
                "La imagen de la orden sale del repositorio de Structure."
            )
        extension = asset_path.suffix.lower()
        size = asset_path.stat().st_size
        if extension not in ALLOWED_IMAGE_EXTENSIONS or size <= 0 or size > MAX_IMAGE_BYTES:
            raise StructureOrderError("El archivo de imagen ya no cumple los límites permitidos.")

        slot = validated["field"].removesuffix("_path")
        destination_name = (
            f"__structure_order_{validated['id']}_{slot}{extension}"
        )
        destination_path = credential_path.parent / destination_name
        if destination_path.exists():
            raise StructureOrderError(
                "Ya existe el destino de imagen de esta orden. No se sobrescribirá."
            )

        prechange_backup = self._create_prechange_backup(
            validated["id"],
            credential_path,
            credential_path.read_bytes(),
        )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{destination_name}.",
                suffix=".tmp",
                dir=credential_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                with asset_path.open("rb") as source:
                    shutil.copyfileobj(source, temporary_file)
            if temporary_path.stat().st_size != size:
                raise StructureOrderError("La copia temporal de imagen quedó incompleta.")
            os.replace(temporary_path, destination_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

        character_data[validated["field"]] = destination_name
        _atomic_write_json(credential_path, payload)
        cached_character[validated["field"]] = destination_name
        self.character_manager.save_cache_file()

        backup_warning = ""
        try:
            character_backup = CharacterCredentialBackupService(
                self.dependent_root,
                structure_dir=self.structure_dir,
            ).backup_character(cached_character)
        except Exception as error:
            character_backup = None
            backup_warning = str(error)

        return {
            "operation": validated["operation_type"],
            "dependent_relative_path": credential_path.relative_to(
                self.dependent_root
            ).as_posix(),
            "new_image_relative_path": destination_path.relative_to(
                self.dependent_root
            ).as_posix(),
            "image_sha256": hashlib.sha256(destination_path.read_bytes()).hexdigest(),
            "image_size_bytes": size,
            "prechange_backup": prechange_backup,
            "previous_image_preserved": True,
            "character_backup": character_backup,
            "character_backup_warning": backup_warning,
        }

    def _apply_json_update(self, validated: dict[str, Any]) -> dict[str, Any]:
        target_path = self._resolve_dependent_path(validated["path"])
        if not target_path.is_file():
            raise StructureOrderError(
                f"El archivo JSON destino no existe: {validated['path']}"
            )
        try:
            json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise StructureOrderError(
                f"El JSON existente no se puede validar: {error}"
            ) from error

        old_bytes = target_path.read_bytes()
        backup = self._create_prechange_backup(
            validated["id"],
            target_path,
            old_bytes,
        )
        _atomic_write_json(target_path, validated["document"])
        return {
            "operation": validated["operation_type"],
            "dependent_relative_path": target_path.relative_to(
                self.dependent_root
            ).as_posix(),
            "backup": backup,
        }

    def _apply_create_directory(self, validated: dict[str, Any]) -> dict[str, Any]:
        target_path = self._resolve_dependent_path(validated["path"])
        if target_path.exists():
            raise StructureOrderError(
                f"El directorio ya existe: {validated['path']}. No se modificó."
            )
        target_path.mkdir(parents=True, exist_ok=False)
        return {
            "operation": validated["operation_type"],
            "created_relative_path": target_path.relative_to(
                self.dependent_root
            ).as_posix(),
        }

    def apply_order(self, order: dict[str, Any]) -> dict[str, Any]:
        """Apply one already reviewed order. This method never deletes files."""
        validated = self.validate_order(order)
        state = self._load_state()
        order_id = validated["id"]
        if order_id in state["applied"]:
            raise StructureOrderError(
                f"La orden {order_id} ya fue aplicada en este equipo."
            )
        if (self.results_root / f"{order_id}.json").exists():
            raise StructureOrderError(
                f"Ya existe un resultado para la orden {order_id}; no se ejecutará otra vez."
            )

        operation_type = validated["operation_type"]
        if operation_type == "update_character_credential":
            details = self._apply_credential_update(validated)
        elif operation_type == "replace_character_asset":
            details = self._apply_character_asset_replacement(validated)
        elif operation_type == "update_dependent_json":
            details = self._apply_json_update(validated)
        elif operation_type == "create_directory":
            details = self._apply_create_directory(validated)
        else:
            raise StructureOrderError("La operación dejó de ser válida.")

        applied_at = datetime.now().astimezone().isoformat(timespec="seconds")
        result = {
            "schema_version": 1,
            "order_id": order_id,
            "title": validated["title"],
            "status": "applied",
            "applied_at": applied_at,
            "details": details,
            "destructive_operations": False,
        }

        # Persist local idempotency before publishing a result file in Structure.
        state["schema_version"] = 1
        state["applied"][order_id] = {
            "applied_at": applied_at,
            "operation": operation_type,
        }
        _atomic_write_json(self.state_path, state)
        self._write_result(order_id, result)
        return result

    def load_pending_orders(self) -> list[dict[str, Any]]:
        """Return unprocessed order JSON files, including validation errors."""
        if not self._is_plain_directory(self.orders_root):
            return []
        if not self._is_plain_directory(self.pending_root):
            return []

        state = self._load_state()
        orders = []
        for order_path in sorted(
            self.pending_root.glob("*.json"),
            key=lambda path: path.name.casefold(),
        ):
            if not self._is_plain_file(order_path):
                orders.append({
                    "path": order_path,
                    "order": {},
                    "validated": None,
                    "error": "El archivo de orden debe ser un JSON regular, sin enlaces simbólicos.",
                })
                continue
            try:
                order = json.loads(order_path.read_text(encoding="utf-8"))
                validated = self.validate_order(order)
                if validated["id"] in state["applied"]:
                    continue
                shared_result_path = (
                    self.results_root / f"{validated['id']}.json"
                )
                if shared_result_path.is_file():
                    try:
                        shared_result = json.loads(
                            shared_result_path.read_text(encoding="utf-8")
                        )
                    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                        shared_result = {}
                    if shared_result.get("status") == "applied":
                        continue
                    orders.append({
                        "path": order_path,
                        "order": order,
                        "validated": None,
                        "error": (
                            "Existe un archivo de resultado para esta orden, "
                            "pero su contenido no confirma status=applied. "
                            "Revísalo manualmente; no se ejecutará de nuevo."
                        ),
                    })
                    continue
                orders.append({
                    "path": order_path,
                    "order": order,
                    "validated": validated,
                    "error": "",
                })
            except Exception as error:
                orders.append({
                    "path": order_path,
                    "order": {},
                    "validated": None,
                    "error": str(error),
                })
        return orders

    @staticmethod
    def describe_order(validated: dict[str, Any]) -> str:
        operation = validated["operation_type"]
        if operation == "update_character_credential":
            target = validated["target"]
            field_preview = json.dumps(
                validated["fields"],
                ensure_ascii=False,
                indent=2,
            )
            return (
                f"Actualizar credencial: {target['name']} / {target['alterego']} "
                f"({target['year']}).\nCambios propuestos:\n{field_preview}"
            )
        if operation == "replace_character_asset":
            target = validated["target"]
            return (
                f"Reemplazar imagen seleccionada ({validated['field']}) de "
                f"{target['name']} / {target['alterego']} ({target['year']}).\n"
                f"Recurso: {validated['asset_path']}\n"
                "La imagen anterior se conservará en la unidad dependiente."
            )
        if operation == "update_dependent_json":
            document_preview = json.dumps(
                validated["document"],
                ensure_ascii=False,
                indent=2,
            )
            if len(document_preview) > 3000:
                document_preview = document_preview[:3000] + "\n… (contenido truncado)"
            return (
                f"Actualizar JSON existente: {validated['path']}\n"
                "Se creará un respaldo del contenido anterior.\n"
                f"Nuevo contenido:\n{document_preview}"
            )
        if operation == "create_directory":
            return f"Crear directorio: {validated['path']}"
        return "Operación no reconocida."
