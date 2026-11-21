"""Back up character credentials and their selected images to private Structure.

The dependent-drive originals are always read-only from this service. Previous
backup assets may be replaced only inside this dedicated Structure backup tree.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

from engines.structure_paths import get_structure_dir


BACKUP_DIRECTORY_NAME = "character_credentials"
ALLOWED_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"
}
MAX_IMAGE_BYTES = 25 * 1024 * 1024


class CharacterCredentialBackupError(RuntimeError):
    """Raised when a character backup cannot be completed safely."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", ascii_value.casefold()).strip("-_")
    if not slug:
        raise CharacterCredentialBackupError(
            "No se pudo construir un identificador estable para el personaje."
        )
    return slug[:70]


class CharacterCredentialBackupService:
    """Create one replaceable, version-controlled backup per character."""

    def __init__(
        self,
        dependent_root: str | Path,
        structure_dir: str | Path | None = None,
        max_image_bytes: int = MAX_IMAGE_BYTES,
    ) -> None:
        self.dependent_root = Path(dependent_root).expanduser().resolve()
        self.structure_dir = (
            Path(structure_dir).expanduser().resolve()
            if structure_dir is not None
            else get_structure_dir().resolve()
        )
        self.backup_root = self.structure_dir / BACKUP_DIRECTORY_NAME
        self.max_image_bytes = int(max_image_bytes)

    def _character_backup_dir(self, character: dict[str, Any]) -> Path:
        try:
            year = int(character.get("year"))
        except (TypeError, ValueError) as error:
            raise CharacterCredentialBackupError(
                "El personaje no tiene un año válido."
            ) from error
        if year < 1900 or year > 9999:
            raise CharacterCredentialBackupError("El año del personaje no es válido.")

        name = _slug(str(character.get("name") or ""))
        alterego = _slug(str(character.get("alterego") or name))
        return self.backup_root / str(year) / f"{alterego}--{name}"

    @staticmethod
    def _resolve_asset(raw_path: str, credential_path: Path) -> Path | None:
        value = str(raw_path or "").strip()
        if not value:
            return None
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            candidate = credential_path.parent / candidate
        return candidate.resolve()

    def _copy_asset(
        self,
        source: Path,
        destination: Path,
        slot: str,
    ) -> dict[str, Any]:
        if not source.is_file():
            raise CharacterCredentialBackupError(
                f"La imagen seleccionada no existe: {source.name}"
            )
        extension = source.suffix.lower()
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            raise CharacterCredentialBackupError(
                f"Formato no permitido para {slot}: {extension or '(sin extensión)'}"
            )
        size = source.stat().st_size
        if size <= 0 or size > self.max_image_bytes:
            raise CharacterCredentialBackupError(
                f"La imagen {source.name} supera el límite de "
                f"{self.max_image_bytes // (1024 * 1024)} MB o está vacía."
            )

        target = destination / f"{slot}{extension}"
        destination.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=f".{slot}.",
                suffix=".tmp",
                dir=destination,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                with source.open("rb") as source_file:
                    shutil.copyfileobj(source_file, temporary_file)
            if temporary_path.stat().st_size != size:
                raise CharacterCredentialBackupError(
                    f"La copia temporal de {source.name} quedó incompleta."
                )
            os.replace(temporary_path, target)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

        return {
            "backup_path": target.name,
            "sha256": _sha256_file(target),
            "size_bytes": target.stat().st_size,
            "source_filename": source.name,
        }

    @staticmethod
    def _safe_previous_asset_path(
        backup_dir: Path,
        manifest: dict[str, Any],
        slot: str,
    ) -> Path | None:
        previous = (manifest.get("assets") or {}).get(slot) or {}
        previous_name = previous.get("backup_path")
        if not isinstance(previous_name, str) or not previous_name:
            return None
        candidate = (backup_dir / previous_name).resolve()
        if candidate.parent != backup_dir.resolve():
            return None
        if candidate.name.casefold().startswith(f"{slot}.") and candidate.is_file():
            return candidate
        return None

    @staticmethod
    def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{path.name}.",
                suffix=".tmp",
                dir=path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(payload, temporary_file, ensure_ascii=False, indent=2)
                temporary_file.write("\n")
            os.replace(temporary_path, path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def backup_character(self, character: dict[str, Any]) -> dict[str, Any]:
        """Back up the on-disk credential and the currently selected icon/background."""
        if not isinstance(character, dict):
            raise CharacterCredentialBackupError("El registro de personaje no es válido.")

        credential_value = str(character.get("character_json_path") or "").strip()
        if not credential_value:
            raise CharacterCredentialBackupError(
                "El personaje no tiene una ruta de credencial."
            )

        credential_path = Path(credential_value).expanduser().resolve()
        if not credential_path.is_file():
            raise CharacterCredentialBackupError(
                f"No se encontró la credencial: {credential_path}"
            )
        try:
            credential_relative = credential_path.relative_to(self.dependent_root)
        except ValueError as error:
            raise CharacterCredentialBackupError(
                "La credencial está fuera de la unidad dependiente configurada."
            ) from error

        try:
            credential_payload = json.loads(
                credential_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CharacterCredentialBackupError(
                f"No se pudo leer el JSON de credenciales: {error}"
            ) from error
        if (
            not isinstance(credential_payload, dict)
            or not isinstance(credential_payload.get("character_data"), dict)
        ):
            raise CharacterCredentialBackupError(
                "El archivo no contiene el objeto character_data esperado."
            )

        backup_dir = self._character_backup_dir(character)
        backup_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = backup_dir / "backup_manifest.json"
        try:
            previous_manifest = (
                json.loads(manifest_path.read_text(encoding="utf-8"))
                if manifest_path.is_file()
                else {}
            )
        except (OSError, json.JSONDecodeError):
            previous_manifest = {}

        existing_credential = backup_dir / "credential.json"
        credential_bytes = credential_path.read_bytes()
        credential_temp: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".credential.",
                suffix=".tmp",
                dir=backup_dir,
                delete=False,
            ) as temporary_file:
                credential_temp = Path(temporary_file.name)
                temporary_file.write(credential_bytes)
            os.replace(credential_temp, existing_credential)
        finally:
            if credential_temp is not None and credential_temp.exists():
                credential_temp.unlink(missing_ok=True)

        asset_records: dict[str, dict[str, Any]] = dict(
            previous_manifest.get("assets") or {}
        )
        asset_warnings: list[str] = []
        replaced_backup_assets: list[Path] = []

        for field_name, slot in (
            ("icon_path", "icon"),
            ("background_path", "background"),
        ):
            raw_asset = str(character.get(field_name) or "").strip()
            if not raw_asset:
                continue
            source_asset = self._resolve_asset(raw_asset, credential_path)
            if source_asset is None:
                continue
            try:
                asset_record = self._copy_asset(source_asset, backup_dir, slot)
            except (OSError, CharacterCredentialBackupError) as error:
                asset_warnings.append(f"{field_name}: {error}")
                continue

            old_asset = self._safe_previous_asset_path(
                backup_dir,
                previous_manifest,
                slot,
            )
            if old_asset is not None and old_asset.name != asset_record["backup_path"]:
                replaced_backup_assets.append(old_asset)
            asset_records[slot] = {
                **asset_record,
                "credential_field": field_name,
            }

        manifest = {
            "schema_version": 1,
            "backed_up_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "character": {
                "year": int(character.get("year")),
                "name": str(character.get("name") or ""),
                "alterego": str(character.get("alterego") or ""),
            },
            "source_credential_relative_path": credential_relative.as_posix(),
            "credential": {
                "backup_path": "credential.json",
                "sha256": hashlib.sha256(credential_bytes).hexdigest(),
                "size_bytes": len(credential_bytes),
            },
            "assets": asset_records,
            "warnings": asset_warnings,
        }

        self._atomic_json_write(manifest_path, manifest)

        # Only remove obsolete copies inside this character's dedicated backup folder.
        # The original image on the dependent drive is never touched.
        removed_backup_copies = []
        for obsolete_path in replaced_backup_assets:
            try:
                obsolete_path.unlink(missing_ok=True)
                removed_backup_copies.append(obsolete_path.name)
            except OSError as error:
                asset_warnings.append(
                    f"No se pudo retirar la copia anterior {obsolete_path.name}: {error}"
                )
        if removed_backup_copies or asset_warnings != manifest["warnings"]:
            manifest["warnings"] = asset_warnings
            self._atomic_json_write(manifest_path, manifest)

        return {
            "year": int(character.get("year")),
            "name": str(character.get("name") or ""),
            "alterego": str(character.get("alterego") or ""),
            "backup_dir": str(backup_dir),
            "credential_path": str(existing_credential),
            "assets_backed_up": sorted(asset_records),
            "warnings": asset_warnings,
            "replaced_backup_copies": removed_backup_copies,
        }

    def backup_all(self, characters_by_year: dict[str, list[dict]]) -> dict[str, Any]:
        """Back up all characters in cache without aborting the batch on one failure."""
        results = []
        failures = []
        for year in sorted(characters_by_year, key=lambda value: int(value)):
            for character in characters_by_year[year]:
                try:
                    results.append(self.backup_character(character))
                except Exception as error:
                    failures.append(
                        {
                            "year": year,
                            "name": str(character.get("name") or ""),
                            "alterego": str(character.get("alterego") or ""),
                            "error": str(error),
                        }
                    )
        return {
            "total": sum(len(items) for items in characters_by_year.values()),
            "backed_up": len(results),
            "failed": len(failures),
            "asset_warning_count": sum(
                len(item.get("warnings", [])) for item in results
            ),
            "results": results,
            "failures": failures,
        }
