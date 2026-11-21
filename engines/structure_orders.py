"""Validated, approval-gated orders from the private Structure repository.

Supported actions only create or update dependent-drive data. No delete, remove,
move, recycle, wipe, or arbitrary command operation is supported.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from engines.character_credential_backup import CharacterCredentialBackupService
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

        if operation_type == "update_dependent_json":
            relative = self._safe_relative_path(operation.get("path", ""))
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
            "Solo se aceptan update_character_credential, "
            "update_dependent_json y create_directory."
        )

    def _find_character_credential(self, target: dict[str, Any]) -> tuple[Path, dict]:
        candidates = self.character_manager._cache.get(str(target["year"]), [])
        matches = [
            item for item in candidates
            if str(item.get("name", "")).casefold() == target["name"].casefold()
            and str(item.get("alterego", "")).casefold() == target["alterego"].casefold()
        ]
        if len(matches) != 1:
            raise StructureOrderError(
                "El personaje no se encontró de forma única en characters_cache.json. "
                "No se modificó ningún archivo."
            )

        cached_character = matches[0]
        raw_path = str(cached_character.get("character_json_path") or "").strip()
        if not raw_path:
            raise StructureOrderError(
                "El personaje no tiene character_json_path en la caché."
            )
        credential_path = Path(raw_path).expanduser().resolve()
        if not credential_path.is_relative_to(self.dependent_root):
            raise StructureOrderError(
                "La credencial del personaje está fuera de la unidad dependiente."
            )
        if not credential_path.is_file():
            raise StructureOrderError(
                f"No existe la credencial del personaje: {credential_path}"
            )
        return credential_path, cached_character

    def _create_prechange_backup(
        self,
        order_id: str,
        target_path: Path,
        current_bytes: bytes,
    ) -> dict[str, str]:
        relative = target_path.resolve().relative_to(self.dependent_root)
        backup_dir = self.backup_root / order_id / Path(*relative.parts)
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write_bytes(backup_dir, current_bytes)
        return {
            "backup_path": str(backup_dir),
            "sha256": hashlib.sha256(current_bytes).hexdigest(),
            "dependent_relative_path": relative.as_posix(),
        }

    def _write_result(self, order_id: str, payload: dict[str, Any]) -> None:
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

        backup = self._create_prechange_backup(
            validated["id"],
            credential_path,
            credential_path.read_bytes(),
        )
        character_data.update(validated["fields"])
        _atomic_write_json(credential_path, payload)

        cached_character.update(validated["fields"])
        self.character_manager.save_cache_file()

        backup_result = CharacterCredentialBackupService(
            self.dependent_root,
            structure_dir=self.structure_dir,
        ).backup_character(cached_character)

        return {
            "operation": validated["operation_type"],
            "dependent_relative_path": credential_path.relative_to(
                self.dependent_root
            ).as_posix(),
            "backup": backup,
            "updated_fields": sorted(validated["fields"]),
            "character_backup": backup_result,
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

        operation_type = validated["operation_type"]
        if operation_type == "update_character_credential":
            details = self._apply_credential_update(validated)
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
        if not self.pending_root.is_dir():
            return []

        state = self._load_state()
        orders = []
        for order_path in sorted(
            self.pending_root.glob("*.json"),
            key=lambda path: path.name.casefold(),
        ):
            try:
                order = json.loads(order_path.read_text(encoding="utf-8"))
                validated = self.validate_order(order)
                if validated["id"] in state["applied"]:
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
            return (
                f"Actualizar credencial: {target['name']} / {target['alterego']} "
                f"({target['year']}).\nCampos: "
                + ", ".join(sorted(validated["fields"]))
            )
        if operation == "update_dependent_json":
            return (
                f"Actualizar JSON existente: {validated['path']}\n"
                "Se creará un respaldo del contenido anterior."
            )
        if operation == "create_directory":
            return f"Crear directorio: {validated['path']}"
        return "Operación no reconocida."
