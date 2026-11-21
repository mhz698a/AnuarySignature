"""Shallow dependent-drive inventory with character credential references.

The report records year directories, at most two directory levels below each
year, and credential file names/relative paths found directly inside character
folders under each year's album directory. Credential contents are never read.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


REPORT_FILENAME = "dependent_directory_report.json"
MAX_SUBFOLDER_LEVELS_AFTER_YEAR = 2
_YEAR_DIRECTORY_PATTERN = re.compile(r"^\d{4}$")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_CREDENTIAL_FILENAME_PATTERN = re.compile(r"^__.*\.json$", re.IGNORECASE)


class DependentDirectoryReportError(RuntimeError):
    """Raised when a complete directory and credential-reference report fails."""


class DependentDirectoryReportService:
    """Build and atomically write a shallow directory and credential report."""

    def __init__(
        self,
        base_path: str | Path,
        report_path: str | Path,
    ) -> None:
        self.base_path = Path(base_path).expanduser()
        self.report_path = Path(report_path).expanduser()

    @staticmethod
    def _is_real_directory(entry: os.DirEntry[str]) -> bool:
        """Ignore files, symlinks and Windows reparse-point directories."""
        if not entry.is_dir(follow_symlinks=False):
            return False
        attributes = getattr(
            entry.stat(follow_symlinks=False),
            "st_file_attributes",
            0,
        )
        return not bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)

    @staticmethod
    def _is_real_file(entry: os.DirEntry[str]) -> bool:
        """Accept only regular files; ignore symlinks and reparse points."""
        if not entry.is_file(follow_symlinks=False):
            return False
        attributes = getattr(
            entry.stat(follow_symlinks=False),
            "st_file_attributes",
            0,
        )
        return not bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)

    @classmethod
    def _directory_entries(cls, parent: Path) -> list[os.DirEntry[str]]:
        """Return immediate child directories without following links."""
        try:
            with os.scandir(parent) as iterator:
                directories = [
                    entry
                    for entry in iterator
                    if cls._is_real_directory(entry)
                ]
        except OSError as error:
            raise DependentDirectoryReportError(
                f"No se pudo leer el directorio:\n{parent}\n\n{error}"
            ) from error

        return sorted(directories, key=lambda entry: entry.name.casefold())

    @staticmethod
    def _parse_character_folder(
        folder_name: str,
        album_prefix: str,
    ) -> dict[str, Any] | None:
        """Validate the existing album character-folder naming convention."""
        prefix = f"{album_prefix}. "
        if not folder_name.startswith(prefix):
            return None

        remainder = folder_name[len(prefix):]
        if remainder.count(";") != 4:
            return None

        parts = remainder.split(";")
        if len(parts) != 5:
            return None

        raw_position, alterego, name, birthday, raw_age = parts
        try:
            position = int(raw_position)
            age = int(raw_age)
            datetime.strptime(birthday, "%Y-%m-%d")
        except (TypeError, ValueError):
            return None

        if not name.strip() or not alterego.strip():
            return None

        return {
            "position": position,
            "alterego": alterego,
            "name": name,
            "birthday": birthday,
            "age": age,
        }

    def _credential_files(
        self,
        character_dir: Path,
    ) -> list[os.DirEntry[str]]:
        """Find direct __*.json files without reading their contents."""
        try:
            with os.scandir(character_dir) as iterator:
                candidates = [
                    entry
                    for entry in iterator
                    if _CREDENTIAL_FILENAME_PATTERN.fullmatch(entry.name)
                    and self._is_real_file(entry)
                ]
        except OSError as error:
            raise DependentDirectoryReportError(
                "No se pudo inspeccionar la carpeta del personaje "
                f"{character_dir}: {error}"
            ) from error

        return sorted(candidates, key=lambda entry: entry.name.casefold())

    def _character_credential_records(
        self,
        root: Path,
        year_entry: os.DirEntry[str],
        album_prefix: str,
        album_dir: Path,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        year_name = year_entry.name

        for character_entry in self._directory_entries(album_dir):
            identity = self._parse_character_folder(
                character_entry.name,
                album_prefix,
            )
            if identity is None:
                continue

            character_dir = Path(character_entry.path)
            candidates = self._credential_files(character_dir)
            credential_files = [
                {
                    "file_name": candidate.name,
                    "relative_path": Path(candidate.path).relative_to(root).as_posix(),
                }
                for candidate in candidates
            ]

            status = (
                "missing"
                if not credential_files
                else "found"
                if len(credential_files) == 1
                else "ambiguous"
            )
            selected = credential_files[0] if status == "found" else None

            records.append(
                {
                    "year": year_name,
                    "position": identity["position"],
                    "name": identity["name"],
                    "alterego": identity["alterego"],
                    "birthday": identity["birthday"],
                    "age": identity["age"],
                    "character_folder": character_entry.name,
                    "character_relative_path": character_dir.relative_to(root).as_posix(),
                    "credential_status": status,
                    "credential_file": (
                        selected["file_name"] if selected is not None else None
                    ),
                    "credential_relative_path": (
                        selected["relative_path"] if selected is not None else None
                    ),
                    "credential_files": credential_files,
                }
            )

        return records

    def build_report(self) -> dict[str, Any]:
        """Read year roots, two directory levels and album credential filenames."""
        root = self.base_path.resolve()
        if not root.exists() or not root.is_dir():
            raise DependentDirectoryReportError(
                f"La unidad dependiente no está disponible o no es un directorio:\n{root}"
            )

        directories: list[dict[str, Any]] = []
        year_names: list[str] = []
        character_credentials: list[dict[str, Any]] = []

        for year_entry in self._directory_entries(root):
            year_name = year_entry.name
            if not _YEAR_DIRECTORY_PATTERN.fullmatch(year_name):
                continue

            year_path = Path(year_entry.path)
            year_names.append(year_name)
            directories.append(
                {
                    "year": year_name,
                    "relative_path": year_name,
                    "depth_after_year": 0,
                }
            )

            first_level = self._directory_entries(year_path)
            for first_entry in first_level:
                first_path = Path(first_entry.path)
                first_relative = f"{year_name}\\{first_entry.name}"
                directories.append(
                    {
                        "year": year_name,
                        "relative_path": first_relative,
                        "depth_after_year": 1,
                    }
                )

                second_level = self._directory_entries(first_path)
                for second_entry in second_level:
                    directories.append(
                        {
                            "year": year_name,
                            "relative_path": (
                                f"{first_relative}\\{second_entry.name}"
                            ),
                            "depth_after_year": 2,
                        }
                    )

            album_name = f"{max(0, int(year_name) - 2003):02d}. album"
            album_entry = next(
                (
                    entry for entry in first_level
                    if entry.name.casefold() == album_name.casefold()
                ),
                None,
            )
            if album_entry is not None:
                character_credentials.extend(
                    self._character_credential_records(
                        root,
                        year_entry,
                        album_name.split(".", 1)[0],
                        Path(album_entry.path),
                    )
                )

        directories.sort(
            key=lambda item: (
                item["year"],
                item["relative_path"].casefold(),
            )
        )
        character_credentials.sort(
            key=lambda item: (
                item["year"],
                item["position"],
                item["name"].casefold(),
                item["alterego"].casefold(),
            )
        )

        credential_file_count = sum(
            len(item["credential_files"]) for item in character_credentials
        )
        found_count = sum(
            item["credential_status"] == "found"
            for item in character_credentials
        )
        missing_count = sum(
            item["credential_status"] == "missing"
            for item in character_credentials
        )
        ambiguous_count = sum(
            item["credential_status"] == "ambiguous"
            for item in character_credentials
        )

        return {
            "schema_version": 2,
            "generated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "root_path": str(root),
            "max_subfolder_levels_after_year": (
                MAX_SUBFOLDER_LEVELS_AFTER_YEAR
            ),
            "year_count": len(year_names),
            "directory_count": len(directories),
            "character_count": len(character_credentials),
            "credential_file_count": credential_file_count,
            "credential_found_count": found_count,
            "credential_missing_count": missing_count,
            "credential_ambiguous_count": ambiguous_count,
            "directories": directories,
            "character_credentials": character_credentials,
        }

    def _write_report(self, report: dict[str, Any]) -> None:
        if not self.report_path.parent.is_dir():
            raise DependentDirectoryReportError(
                "No existe el directorio local del repositorio Structure. "
                "Comprueba que el repositorio privado esté clonado.\n"
                f"{self.report_path.parent}"
            )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=f".{self.report_path.name}.",
                suffix=".tmp",
                dir=self.report_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    report,
                    temporary_file,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary_file.write("\n")

            os.replace(temporary_path, self.report_path)
        except OSError as error:
            raise DependentDirectoryReportError(
                f"No se pudo escribir el reporte de directorios:\n"
                f"{self.report_path}\n\n{error}"
            ) from error
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def generate_or_update(self) -> dict[str, Any]:
        """Build the complete report and replace the previous report atomically."""
        report = self.build_report()
        self._write_report(report)
        return {
            "report_path": str(self.report_path),
            "root_path": report["root_path"],
            "year_count": report["year_count"],
            "directory_count": report["directory_count"],
            "character_count": report["character_count"],
            "credential_file_count": report["credential_file_count"],
            "credential_found_count": report["credential_found_count"],
            "credential_missing_count": report["credential_missing_count"],
            "credential_ambiguous_count": report["credential_ambiguous_count"],
            "max_subfolder_levels_after_year": (
                report["max_subfolder_levels_after_year"]
            ),
            "generated_at": report["generated_at"],
        }
