"""Recoverable local snapshots for the private Structure repository."""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from engines.structure_paths import (
    get_structure_backup_root,
    get_structure_repo_root,
)


BACKUP_MANIFEST = "__backup_manifest__.json"


class StructureBackupError(RuntimeError):
    """Raised when a Structure backup cannot be created or restored safely."""


class StructureBackupManager:
    """Create verified ZIP snapshots outside the Git working tree."""

    def __init__(
        self,
        repo_root: str | Path | None = None,
        backup_root: str | Path | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else get_structure_repo_root()
        self.backup_root = (
            Path(backup_root) if backup_root else get_structure_backup_root()
        )

    @staticmethod
    def _sha256(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _ensure_repo_root(self) -> None:
        if not self.repo_root.is_dir():
            raise StructureBackupError(
                f"No existe el directorio local de Structure: {self.repo_root}"
            )

    def create_backup(
        self,
        operation: str = "manual",
        source_commit: str = "",
    ) -> Path:
        self._ensure_repo_root()
        self.backup_root.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now(timezone.utc)
        stamp = timestamp.strftime("%Y%m%dT%H%M%SZ")
        target = self.backup_root / f"structure-{stamp}-{operation}.zip"
        suffix = 1
        while target.exists():
            target = self.backup_root / f"structure-{stamp}-{operation}-{suffix}.zip"
            suffix += 1

        files: list[dict[str, Any]] = []
        try:
            with zipfile.ZipFile(
                target,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=6,
            ) as archive:
                for path in sorted(self.repo_root.rglob("*")):
                    relative = path.relative_to(self.repo_root)
                    if any(part.casefold() == ".git" for part in relative.parts) or path.is_dir() or path.is_symlink():
                        continue
                    if not path.is_file():
                        continue

                    content = path.read_bytes()
                    relative_name = relative.as_posix()
                    archive.writestr(relative_name, content)
                    files.append(
                        {
                            "path": relative_name,
                            "size": len(content),
                            "sha256": self._sha256(content),
                        }
                    )

                manifest = {
                    "backup_version": 1,
                    "created_at": timestamp.isoformat(),
                    "operation": operation,
                    "source_commit": source_commit,
                    "repository": "mhz698a/AnuarySignature-Structure",
                    "file_count": len(files),
                    "files": files,
                }
                archive.writestr(
                    BACKUP_MANIFEST,
                    json.dumps(manifest, indent=2, ensure_ascii=False),
                )
        except Exception as error:
            target.unlink(missing_ok=True)
            raise StructureBackupError(
                f"No se pudo crear el respaldo local: {error}"
            ) from error

        return target

    def list_backups(self) -> list[dict[str, Any]]:
        if not self.backup_root.is_dir():
            return []

        backups = []
        for path in self.backup_root.glob("structure-*.zip"):
            try:
                with zipfile.ZipFile(path, "r") as archive:
                    manifest = json.loads(archive.read(BACKUP_MANIFEST).decode("utf-8"))
                backups.append(
                    {
                        "path": str(path),
                        "name": path.name,
                        "created_at": manifest.get("created_at", ""),
                        "operation": manifest.get("operation", "unknown"),
                        "source_commit": manifest.get("source_commit", ""),
                        "file_count": manifest.get("file_count", 0),
                    }
                )
            except (OSError, KeyError, ValueError, zipfile.BadZipFile):
                continue

        return sorted(
            backups,
            key=lambda item: item["created_at"],
            reverse=True,
        )

    @staticmethod
    def _safe_archive_path(name: str) -> PurePosixPath:
        path = PurePosixPath(name)
        if (
            path.is_absolute()
            or ".." in path.parts
            or not path.parts
            or "\\" in name
            or (len(name) >= 2 and name[1] == ":")
        ):
            raise StructureBackupError(
                f"El respaldo contiene una ruta no permitida: {name}"
            )
        if any(part.casefold() == ".git" for part in path.parts):
            raise StructureBackupError(
                "El respaldo no puede modificar los metadatos de Git."
            )
        return path

    def restore_backup(
        self,
        backup_path: str | Path,
        create_pre_restore_backup: bool = True,
        source_commit: str = "",
    ) -> dict[str, Path | None]:
        self._ensure_repo_root()
        selected = Path(backup_path).expanduser().resolve()
        backup_root = self.backup_root.resolve()
        try:
            selected.relative_to(backup_root)
        except ValueError as error:
            raise StructureBackupError(
                "El respaldo seleccionado está fuera del directorio autorizado."
            ) from error

        if not selected.is_file() or selected.suffix.lower() != ".zip":
            raise StructureBackupError("El respaldo seleccionado no existe o no es ZIP.")

        pre_restore_backup = None
        if create_pre_restore_backup:
            pre_restore_backup = self.create_backup(
                operation="before_restore",
                source_commit=source_commit,
            )

        staging_root = Path(
            tempfile.mkdtemp(prefix="anuary-structure-restore-", dir=str(self.backup_root))
        )
        try:
            with zipfile.ZipFile(selected, "r") as archive:
                try:
                    manifest = json.loads(
                        archive.read(BACKUP_MANIFEST).decode("utf-8")
                    )
                except (KeyError, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise StructureBackupError(
                        "El respaldo no contiene un manifiesto válido."
                    ) from error

                expected_files = manifest.get("files")
                if not isinstance(expected_files, list):
                    raise StructureBackupError(
                        "El manifiesto del respaldo no tiene una lista de archivos."
                    )

                for entry in expected_files:
                    if not isinstance(entry, dict):
                        raise StructureBackupError("Entrada inválida en el manifiesto.")
                    name = str(entry.get("path", ""))
                    relative = self._safe_archive_path(name)
                    try:
                        content = archive.read(name)
                    except KeyError as error:
                        raise StructureBackupError(
                            f"Falta el archivo '{name}' dentro del respaldo."
                        ) from error

                    if self._sha256(content) != entry.get("sha256"):
                        raise StructureBackupError(
                            f"El archivo '{name}' no supera la verificación SHA-256."
                        )

                    destination = staging_root.joinpath(*relative.parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(content)

            # La copia actual ya está respaldada. Se conserva .git para que
            # restaurar una instantánea produzca cambios locales revisables.
            for child in self.repo_root.iterdir():
                if child.name == ".git":
                    continue
                if child.is_dir() and not child.is_symlink():
                    shutil.rmtree(child)
                else:
                    child.unlink(missing_ok=True)

            for child in staging_root.iterdir():
                destination = self.repo_root / child.name
                if child.is_dir():
                    shutil.copytree(child, destination)
                else:
                    shutil.copy2(child, destination)

        except StructureBackupError:
            raise
        except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
            raise StructureBackupError(
                f"No se pudo restaurar el respaldo: {error}"
            ) from error
        finally:
            shutil.rmtree(staging_root, ignore_errors=True)

        return {
            "restored_backup": selected,
            "pre_restore_backup": pre_restore_backup,
        }
