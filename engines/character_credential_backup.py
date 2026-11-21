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
import stat
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
        if not self.structure_dir.is_dir() or not (self.structure_dir / ".git").exists():
            raise CharacterCredentialBackupError(
                "El repositorio privado Structure no está clonado correctamente. "
                "No se creó un respaldo fuera del checkout Git."
            )

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

    @staticmethod
    def _is_plain_directory(path: Path) -> bool:
        """Exclude symlinks and Windows junction/reparse-point directories."""
        try:
            info = path.lstat()
        except OSError:
            return False
        if stat.S_ISLNK(info.st_mode):
            return False
        if getattr(info, "st_file_attributes", 0) & 0x400:
            return False
        return stat.S_ISDIR(info.st_mode)

    def discover_characters(
        self,
        characters_by_year: dict[str, list[dict]] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
        """Discover every character credential in the year album folders.

        The on-disk scan is authoritative because the UI cache may be capped to
        six displayed profiles per year. Only immediate character directories
        and their __*.json credential files are inspected.
        """
        if not self.dependent_root.is_dir():
            raise CharacterCredentialBackupError(
                f"La unidad dependiente no está disponible: {self.dependent_root}"
            )

        discovered: dict[tuple[str, str, str], dict[str, Any]] = {}
        failures: list[dict[str, str]] = []

        try:
            year_entries = sorted(
                (
                    entry for entry in self.dependent_root.iterdir()
                    if self._is_plain_directory(entry)
                    and re.fullmatch(r"\d{4}", entry.name)
                ),
                key=lambda item: item.name,
            )
        except OSError as error:
            raise CharacterCredentialBackupError(
                f"No se pudieron leer los directorios de años: {error}"
            ) from error

        for year_entry in year_entries:
            year = int(year_entry.name)
            prefix = f"{max(0, year - 2003):02d}"
            album_dir = year_entry / f"{prefix}. album"
            if not self._is_plain_directory(album_dir):
                continue

            try:
                character_directories = sorted(
                    (
                        entry for entry in album_dir.iterdir()
                        if self._is_plain_directory(entry)
                    ),
                    key=lambda item: item.name.casefold(),
                )
            except OSError as error:
                failures.append({
                    "year": year_entry.name,
                    "name": "",
                    "alterego": "",
                    "error": f"No se pudo leer {album_dir}: {error}",
                })
                continue

            for character_dir in character_directories:
                folder_name = character_dir.name
                prefix_to_check = f"{prefix}. "
                if not folder_name.startswith(prefix_to_check):
                    continue
                if folder_name.count(";") != 4:
                    continue
                parts = folder_name[len(prefix_to_check):].split(";")
                if len(parts) != 5:
                    continue

                raw_position, folder_alterego, folder_name_value, birthday, raw_age = parts
                try:
                    int(raw_position)
                    int(raw_age)
                    datetime.strptime(birthday, "%Y-%m-%d")
                except (TypeError, ValueError):
                    continue
                expected_json = character_dir / f"__{folder_name_value}__.json"
                if expected_json.is_file():
                    credential_path = expected_json
                else:
                    try:
                        candidates = sorted(
                            item for item in character_dir.glob("__*.json")
                            if item.is_file()
                        )
                    except OSError as error:
                        failures.append({
                            "year": year_entry.name,
                            "name": folder_name_value,
                            "alterego": folder_alterego,
                            "error": str(error),
                        })
                        continue
                    credential_path = candidates[0] if candidates else None

                if credential_path is None:
                    failures.append({
                        "year": year_entry.name,
                        "name": folder_name_value,
                        "alterego": folder_alterego,
                        "error": "No se encontró un JSON __*.json en la carpeta del personaje.",
                    })
                    continue

                try:
                    payload = json.loads(credential_path.read_text(encoding="utf-8"))
                    char_data = payload.get("character_data")
                    if not isinstance(char_data, dict):
                        raise ValueError("El documento no contiene character_data.")
                except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
                    failures.append({
                        "year": year_entry.name,
                        "name": folder_name_value,
                        "alterego": folder_alterego,
                        "error": f"Credencial inválida: {error}",
                    })
                    continue

                character = dict(char_data)
                character["year"] = year
                character.setdefault("name", folder_name_value)
                character.setdefault("alterego", folder_alterego)
                character["character_json_path"] = str(credential_path.resolve())
                identity = (
                    str(year),
                    str(character.get("name") or "").casefold(),
                    str(character.get("alterego") or "").casefold(),
                )
                discovered[identity] = character

        # Cache entries outside a recognized album folder remain eligible only
        # when their credential JSON actually exists under the configured root.
        for year, items in (characters_by_year or {}).items():
            for cached in items:
                raw_path = str(cached.get("character_json_path") or "").strip()
                if not raw_path:
                    continue
                candidate = Path(raw_path).expanduser().resolve()
                try:
                    candidate.relative_to(self.dependent_root)
                except ValueError:
                    continue
                if not candidate.is_file():
                    continue
                identity = (
                    str(cached.get("year") or year),
                    str(cached.get("name") or "").casefold(),
                    str(cached.get("alterego") or "").casefold(),
                )
                discovered.setdefault(identity, dict(cached))

        return list(discovered.values()), failures

    def backup_all(self, characters_by_year: dict[str, list[dict]]) -> dict[str, Any]:
        """Back up every discoverable on-disk character plus safe cache fallbacks."""
        characters, discovery_failures = self.discover_characters(
            characters_by_year
        )
        results = []
        failures = list(discovery_failures)
        for character in characters:
            try:
                results.append(self.backup_character(character))
            except Exception as error:
                failures.append(
                    {
                        "year": str(character.get("year") or ""),
                        "name": str(character.get("name") or ""),
                        "alterego": str(character.get("alterego") or ""),
                        "error": str(error),
                    }
                )
        return {
            "total": len(characters) + len(discovery_failures),
            "discovered": len(characters),
            "backed_up": len(results),
            "failed": len(failures),
            "asset_warning_count": sum(
                len(item.get("warnings", [])) for item in results
            ),
            "results": results,
            "failures": failures,
        }
