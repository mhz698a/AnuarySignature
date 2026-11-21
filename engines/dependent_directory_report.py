"""Shallow directory-only inventory for the configured dependent drive.

The report intentionally records year directories and at most two directory
levels below each year. It never opens or records files.
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


class DependentDirectoryReportError(RuntimeError):
    """Raised when a complete directory-only report cannot be generated."""


class DependentDirectoryReportService:
    """Build and atomically write a shallow directory-only report."""

    def __init__(
        self,
        base_path: str | Path,
        report_path: str | Path,
    ) -> None:
        self.base_path = Path(base_path).expanduser()
        self.report_path = Path(report_path).expanduser()

    @staticmethod
    def _is_real_directory(entry: os.DirEntry[str]) -> bool:
        """Ignore files, symlinks and Windows reparse points/junctions."""
        if not entry.is_dir(follow_symlinks=False):
            return False

        try:
            attributes = getattr(
                entry.stat(follow_symlinks=False),
                "st_file_attributes",
                0,
            )
        except OSError:
            raise

        return not bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)

    @classmethod
    def _directory_entries(cls, parent: Path) -> list[os.DirEntry[str]]:
        """Return immediate child directories only; never descend into files."""
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

    def build_report(self) -> dict[str, Any]:
        """Read only the year roots and their first two directory levels."""
        root = self.base_path.resolve()
        if not root.exists() or not root.is_dir():
            raise DependentDirectoryReportError(
                f"La unidad dependiente no está disponible o no es un directorio:\n{root}"
            )

        records: list[dict[str, Any]] = []
        year_names: list[str] = []

        for year_entry in self._directory_entries(root):
            year_name = year_entry.name
            if not _YEAR_DIRECTORY_PATTERN.fullmatch(year_name):
                continue

            year_path = Path(year_entry.path)
            year_names.append(year_name)
            records.append(
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
                records.append(
                    {
                        "year": year_name,
                        "relative_path": first_relative,
                        "depth_after_year": 1,
                    }
                )

                second_level = self._directory_entries(first_path)
                for second_entry in second_level:
                    records.append(
                        {
                            "year": year_name,
                            "relative_path": (
                                f"{first_relative}\\{second_entry.name}"
                            ),
                            "depth_after_year": 2,
                        }
                    )

        records.sort(
            key=lambda item: (
                item["year"],
                item["relative_path"].casefold(),
            )
        )
        return {
            "schema_version": 1,
            "generated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "root_path": str(root),
            "max_subfolder_levels_after_year": (
                MAX_SUBFOLDER_LEVELS_AFTER_YEAR
            ),
            "year_count": len(year_names),
            "directory_count": len(records),
            "directories": records,
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
            "max_subfolder_levels_after_year": (
                report["max_subfolder_levels_after_year"]
            ),
            "generated_at": report["generated_at"],
        }
