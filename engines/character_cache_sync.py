"""Review and apply Structure character-cache changes to local credential JSON files."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engines.character_credential_backup import ALLOWED_IMAGE_EXTENSIONS
from engines.structure_orders import (
    CHARACTER_STRING_FIELDS,
    StructureOrderError,
    StructureOrderService,
)
from engines.structure_paths import get_structure_dir, get_structure_repo_root


class CharacterCacheSyncError(RuntimeError):
    """Raised when cached character data cannot be safely applied locally."""


SYNC_FIELDS = frozenset(CHARACTER_STRING_FIELDS | {"type_underwear"})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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


class CharacterCacheSyncService:
    """Generate a diff between Structure cache and local credentials, then apply selected fields."""

    def __init__(
        self,
        dependent_path: str | Path,
        character_manager,
        structure_dir: str | Path | None = None,
        cache_path: str | Path | None = None,
        state_root: str | Path | None = None,
    ) -> None:
        self.dependent_root = Path(dependent_path).expanduser().resolve()
        self.character_manager = character_manager
        self.structure_dir = (
            Path(structure_dir).expanduser().resolve()
            if structure_dir is not None
            else get_structure_dir().resolve()
        )
        self.cache_path = (
            Path(cache_path)
            if cache_path is not None
            else Path(character_manager.cache_path)
        )
        local_state_root = (
            Path(state_root)
            if state_root is not None
            else get_structure_repo_root().parent / "CharacterCacheSync"
        )
        self.local_state_root = local_state_root
        self.pending_snapshot_path = local_state_root / "pending_characters_cache.json"
        self.backup_root = local_state_root / "Backups"
        self.history_path = local_state_root / "history.json"
        self.resolver = StructureOrderService(
            dependent_path=self.dependent_root,
            character_manager=character_manager,
            structure_dir=self.structure_dir,
            state_path=local_state_root / "resolver_state.json",
            backup_root=self.backup_root / "_resolver",
        )

    @staticmethod
    def _is_plain_file(path: Path) -> bool:
        return StructureOrderService._is_plain_file(path)

    def _read_cache(self, path: Path) -> dict[str, Any]:
        if not self._is_plain_file(path):
            raise CharacterCacheSyncError(
                f"El archivo de caché no existe o no es un archivo regular: {path}"
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CharacterCacheSyncError(
                f"No se pudo leer characters_cache.json: {error}"
            ) from error
        if not isinstance(payload, dict):
            raise CharacterCacheSyncError(
                "characters_cache.json debe contener un objeto JSON por año."
            )
        return payload

    def capture_pending_snapshot(self) -> dict[str, Any]:
        """Preserve the current cache without overwriting a different pending snapshot."""
        payload = self._read_cache(self.cache_path)
        raw = self.cache_path.read_bytes()
        if self.pending_snapshot_path.exists() or self.pending_snapshot_path.is_symlink():
            if not self._is_plain_file(self.pending_snapshot_path):
                raise CharacterCacheSyncError(
                    "El snapshot pendiente no es un archivo regular. No se leerá ni sobrescribirá."
                )
            existing = self.pending_snapshot_path.read_bytes()
            if existing != raw:
                raise CharacterCacheSyncError(
                    "Ya existe otra versión pendiente de aplicar de characters_cache.json. "
                    "Se conservó intacta y no se sobrescribió."
                )
        else:
            _atomic_write_bytes(self.pending_snapshot_path, raw)
        return {
            "snapshot_path": str(self.pending_snapshot_path),
            "year_count": len(payload),
            "character_count": sum(
                len(items) for items in payload.values() if isinstance(items, list)
            ),
        }

    def discard_pending_snapshot(self) -> bool:
        """Discard only the local review snapshot; dependent credentials and Git files are untouched."""
        if not self.pending_snapshot_path.exists():
            return False
        if not self._is_plain_file(self.pending_snapshot_path):
            raise CharacterCacheSyncError(
                "El snapshot pendiente no es un archivo regular y no se eliminará."
            )
        self.pending_snapshot_path.unlink()
        return True

    def ensure_pending_snapshot(self) -> None:
        """Use an existing deferred snapshot, or capture the current cache for manual review."""
        if self.pending_snapshot_path.exists() or self.pending_snapshot_path.is_symlink():
            if not self._is_plain_file(self.pending_snapshot_path):
                raise CharacterCacheSyncError(
                    "El snapshot pendiente no es un archivo regular. No se sobrescribirá."
                )
            return
        self.capture_pending_snapshot()

    def has_pending_snapshot(self) -> bool:
        return self._is_plain_file(self.pending_snapshot_path)

    def _load_source(self) -> dict[str, Any]:
        source = (
            self.pending_snapshot_path
            if self.has_pending_snapshot()
            else self.cache_path
        )
        return self._read_cache(source)

    @staticmethod
    def _normalize_field(field_name: str, value: Any) -> Any:
        if field_name == "type_underwear" and isinstance(value, str):
            return [value] if value else []
        return value

    def _validate_asset_reference(
        self,
        field_name: str,
        value: Any,
        credential_path: Path,
    ) -> None:
        if field_name not in {"icon_path", "background_path"} or not value:
            return
        if not isinstance(value, str):
            raise CharacterCacheSyncError(
                f"{field_name} debe ser una ruta de imagen de texto."
            )
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = credential_path.parent / candidate
        if not self._is_plain_file(candidate):
            raise CharacterCacheSyncError(
                f"{field_name} debe apuntar a un archivo de imagen regular, sin enlaces."
            )
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise CharacterCacheSyncError(
                f"La imagen indicada por {field_name} no existe en este equipo: {value}"
            ) from error
        character_root = credential_path.parent.resolve()
        if (
            not resolved.is_relative_to(self.dependent_root)
            or not resolved.is_relative_to(character_root)
            or not self._is_plain_file(resolved)
            or resolved.suffix.lower() not in ALLOWED_IMAGE_EXTENSIONS
        ):
            raise CharacterCacheSyncError(
                f"{field_name} debe señalar una imagen regular dentro de la carpeta "
                "local del personaje. Para transferir una imagen entre equipos utiliza "
                "una orden replace_character_asset."
            )

    def _resolve_character(
        self,
        year: int,
        cached_character: dict[str, Any],
    ) -> tuple[Path, dict[str, Any]]:
        name = str(cached_character.get("name") or "").strip()
        alterego = str(cached_character.get("alterego") or "").strip()
        if not name or not alterego:
            raise CharacterCacheSyncError(
                "El registro cacheado no contiene name y alterego para identificar "
                "un personaje de forma segura."
            )
        target = {"year": year, "name": name, "alterego": alterego}
        try:
            return self.resolver.find_character_credential(
                target,
                cache_records=[],
            )
        except (StructureOrderError, OSError, ValueError) as error:
            raise CharacterCacheSyncError(str(error)) from error

    def preview_changes(self) -> list[dict[str, Any]]:
        """Return per-field differences; malformed or ambiguous records remain visible as errors."""
        cache = self._load_source()
        rows: list[dict[str, Any]] = []
        seen: set[tuple[int, str, str]] = set()

        for year_key, characters in cache.items():
            try:
                year = int(year_key)
            except (TypeError, ValueError):
                rows.append({
                    "error": f"Clave de año no válida en caché: {year_key!r}",
                    "year": str(year_key),
                })
                continue
            if not isinstance(characters, list):
                rows.append({
                    "error": f"El registro del año {year} no es una lista.",
                    "year": year,
                })
                continue

            for cached_character in characters:
                if not isinstance(cached_character, dict):
                    rows.append({
                        "error": f"Hay un registro de personaje inválido en {year}.",
                        "year": year,
                    })
                    continue

                identity = (
                    year,
                    str(cached_character.get("name") or "").strip().casefold(),
                    str(cached_character.get("alterego") or "").strip().casefold(),
                )
                if identity in seen:
                    rows.append({
                        "error": (
                            f"El caché contiene una identidad duplicada en {year}: "
                            f"{cached_character.get('name', '')}."
                        ),
                        "year": year,
                        "name": cached_character.get("name", ""),
                    })
                    continue
                seen.add(identity)

                try:
                    credential_path, disk_character = self._resolve_character(
                        year, cached_character
                    )
                except CharacterCacheSyncError as error:
                    rows.append({
                        "error": str(error),
                        "year": year,
                        "name": cached_character.get("name", ""),
                        "alterego": cached_character.get("alterego", ""),
                    })
                    continue

                fields: dict[str, Any] = {}
                for field_name in sorted(SYNC_FIELDS):
                    if field_name not in cached_character:
                        continue
                    fields[field_name] = self._normalize_field(
                        field_name, cached_character[field_name]
                    )

                if not fields:
                    continue

                try:
                    StructureOrderService._validate_character_fields(fields)
                except StructureOrderError as error:
                    rows.append({
                        "error": str(error),
                        "year": year,
                        "name": cached_character.get("name", ""),
                        "alterego": cached_character.get("alterego", ""),
                    })
                    continue

                for field_name, cached_value in fields.items():
                    local_value = self._normalize_field(
                        field_name, disk_character.get(field_name, [] if field_name == "type_underwear" else "")
                    )
                    if _canonical(local_value) == _canonical(cached_value):
                        continue
                    field_error = ""
                    try:
                        self._validate_asset_reference(
                            field_name, cached_value, credential_path
                        )
                    except CharacterCacheSyncError as error:
                        field_error = str(error)
                    rows.append({
                        "year": year,
                        "name": cached_character.get("name", ""),
                        "alterego": cached_character.get("alterego", ""),
                        "field": field_name,
                        "local_value": local_value,
                        "structure_value": cached_value,
                        "credential_path": str(credential_path),
                        "error": field_error,
                    })

        return rows

    def _load_history(self) -> dict[str, Any]:
        if not self.history_path.is_file():
            return {"schema_version": 1, "batches": []}
        try:
            payload = json.loads(self.history_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CharacterCacheSyncError(
                f"No se pudo leer el historial de aplicación local: {error}"
            ) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("batches"), list):
            raise CharacterCacheSyncError(
                "El historial local de sincronización tiene un formato inválido."
            )
        return payload

    def apply_selected(self, selected_rows: list[dict[str, Any]]) -> dict[str, Any]:
        """Apply only reviewed rows, backing up each original credential before its atomic update."""
        if not selected_rows:
            return {"applied_characters": 0, "applied_fields": 0, "issues": []}

        cache = self._load_source()
        cached_by_identity: dict[tuple[int, str, str], dict[str, Any]] = {}
        for year_key, records in cache.items():
            try:
                year = int(year_key)
            except (TypeError, ValueError):
                continue
            if not isinstance(records, list):
                continue
            for record in records:
                if isinstance(record, dict):
                    key = (
                        year,
                        str(record.get("name") or "").strip().casefold(),
                        str(record.get("alterego") or "").strip().casefold(),
                    )
                    cached_by_identity[key] = record

        grouped: dict[tuple[int, str, str], dict[str, Any]] = {}
        for row in selected_rows:
            target = (
                int(row["year"]),
                str(row["name"]).strip().casefold(),
                str(row["alterego"]).strip().casefold(),
            )
            grouped.setdefault(target, {"identity": row, "fields": {}})
            grouped[target]["fields"][row["field"]] = row

        batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8]
        history = self._load_history()
        batch_record = {
            "batch_id": batch_id,
            "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "applied_characters": [],
            "issues": [],
        }
        applied_fields = 0

        for identity, group in grouped.items():
            year, name_key, alterego_key = identity
            cached_character = cached_by_identity.get(identity)
            if cached_character is None:
                issue = f"No se encontró en el snapshot la identidad {year}/{name_key}/{alterego_key}."
                batch_record["issues"].append(issue)
                continue
            target = {
                "year": year,
                "name": str(cached_character.get("name") or ""),
                "alterego": str(cached_character.get("alterego") or ""),
            }
            try:
                credential_path, disk_character = self._resolve_character(
                    year, cached_character
                )
                payload = json.loads(credential_path.read_text(encoding="utf-8"))
                character_data = payload.get("character_data")
                if not isinstance(character_data, dict):
                    raise CharacterCacheSyncError(
                        "La credencial no contiene un objeto character_data."
                    )

                fields_to_apply: dict[str, Any] = {}
                for field_name, preview_row in group["fields"].items():
                    cached_value = self._normalize_field(
                        field_name, cached_character[field_name]
                    )
                    local_value = self._normalize_field(
                        field_name,
                        character_data.get(
                            field_name,
                            [] if field_name == "type_underwear" else "",
                        ),
                    )
                    if _canonical(cached_value) != _canonical(
                        preview_row["structure_value"]
                    ):
                        raise CharacterCacheSyncError(
                            f"El caché cambió después de la previsualización ({field_name}). "
                            "Vuelve a revisar las diferencias."
                        )
                    if _canonical(local_value) != _canonical(
                        preview_row["local_value"]
                    ):
                        raise CharacterCacheSyncError(
                            f"La credencial local cambió después de la previsualización "
                            f"({field_name}). Vuelve a comprobar antes de aplicar."
                        )
                    fields_to_apply[field_name] = cached_value

                StructureOrderService._validate_character_fields(fields_to_apply)
                for field_name, value in fields_to_apply.items():
                    self._validate_asset_reference(field_name, value, credential_path)

                relative_path = credential_path.relative_to(self.dependent_root)
                backup_path = self.backup_root / batch_id / relative_path
                if backup_path.exists():
                    raise CharacterCacheSyncError(
                        "Ya existe un respaldo para esta credencial y no será sobrescrito."
                    )
                original_bytes = credential_path.read_bytes()
                backup_path.parent.mkdir(parents=True, exist_ok=True)
                _atomic_write_bytes(backup_path, original_bytes)

                character_data.update(fields_to_apply)
                serialized = (
                    json.dumps(payload, ensure_ascii=False, indent=4) + "\n"
                ).encode("utf-8")
                _atomic_write_bytes(credential_path, serialized)

                batch_record["applied_characters"].append({
                    "year": year,
                    "name": target["name"],
                    "alterego": target["alterego"],
                    "fields": sorted(fields_to_apply),
                    "credential_relative_path": relative_path.as_posix(),
                    "backup_path": str(backup_path),
                    "backup_sha256": hashlib.sha256(original_bytes).hexdigest(),
                    "result_sha256": hashlib.sha256(serialized).hexdigest(),
                })
                applied_fields += len(fields_to_apply)
            except (OSError, ValueError, KeyError, TypeError, StructureOrderError, CharacterCacheSyncError) as error:
                batch_record["issues"].append(
                    f"{year}/{target['name']}: {error}"
                )

        history_saved = True
        history["schema_version"] = 1
        history["batches"].append(batch_record)
        try:
            _atomic_write_json(self.history_path, history)
        except OSError as error:
            history_saved = False
            batch_record["issues"].append(
                "Las credenciales modificadas ya fueron escritas y respaldadas, "
                "pero no se pudo guardar el historial local de esta operación: "
                f"{error}. Conserva los respaldos y revisa las credenciales antes "
                "de volver a intentar la sincronización."
            )

        remaining: list[dict[str, Any]] | None
        remaining_check_error = ""
        try:
            remaining = self.preview_changes()
        except (OSError, CharacterCacheSyncError) as error:
            remaining = None
            remaining_check_error = str(error)
            batch_record["issues"].append(
                "No se pudo volver a comparar el caché después de la aplicación: "
                f"{error}"
            )

        if (
            history_saved
            and remaining is not None
            and self.has_pending_snapshot()
            and not remaining
        ):
            self.pending_snapshot_path.unlink(missing_ok=True)

        return {
            "batch_id": batch_id,
            "applied_characters": len(batch_record["applied_characters"]),
            "applied_fields": applied_fields,
            "issues": batch_record["issues"],
            "history_saved": history_saved,
            "remaining_changes": len(remaining) if remaining is not None else None,
            "remaining_check_error": remaining_check_error,
            "backup_root": str(self.backup_root / batch_id),
        }
