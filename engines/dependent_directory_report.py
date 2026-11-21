"""Dependent-drive directory inventory and character credential reference report.

The report includes year directories and at most two directory levels below
each year. Character credential filenames and relative paths are indexed
without reading credential contents. User exclusions are persisted in Structure.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable


REPORT_FILENAME = "dependent_directory_report.json"
REPORT_SETTINGS_FILENAME = "dependent_directory_report_settings.json"
MAX_SUBFOLDER_LEVELS_AFTER_YEAR = 2
DEFAULT_EXCLUDED_DIRECTORY_NAMES = ("resources.local.personal",)
_YEAR_DIRECTORY_PATTERN = re.compile(r"^\d{4}$")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400
_CREDENTIAL_FILENAME_PATTERN = re.compile(r"^__.*\.json$", re.IGNORECASE)

ProgressCallback = Callable[[int, int, str], None]


class DependentDirectoryReportError(RuntimeError):
    """Raised when a complete directory and credential-reference report fails."""


class DependentDirectoryReportService:
    """Build and atomically write a directory and character credential report."""

    def __init__(
        self,
        base_path: str | Path,
        report_path: str | Path,
        settings_path: str | Path | None = None,
    ) -> None:
        self.base_path = Path(base_path).expanduser()
        self.report_path = Path(report_path).expanduser()
        self.settings_path = (
            Path(settings_path).expanduser()
            if settings_path is not None
            else self.report_path.with_name(REPORT_SETTINGS_FILENAME)
        )

    @staticmethod
    def _is_real_directory(entry: os.DirEntry[str]) -> bool:
        """Ignore files, symbolic links and Windows reparse-point directories."""
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
        """Accept only regular files; ignore symbolic links and reparse points."""
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
    def _canonical_relative_directory(raw_path: str) -> str:
        """Validate and normalize a year-relative directory identifier."""
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise DependentDirectoryReportError(
                "La ruta relativa de exclusión está vacía."
            )

        normalized = raw_path.strip().replace("\\", "/")
        relative = PurePosixPath(normalized)
        if (
            relative.is_absolute()
            or len(relative.parts) < 2
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise DependentDirectoryReportError(
                f"Ruta de exclusión no válida: {raw_path}"
            )
        if not _YEAR_DIRECTORY_PATTERN.fullmatch(relative.parts[0]):
            raise DependentDirectoryReportError(
                f"La exclusión debe comenzar con un año de cuatro dígitos: {raw_path}"
            )
        return relative.as_posix().casefold()

    @classmethod
    def _normalise_exclusion_list(cls, values: Any) -> list[str]:
        if not isinstance(values, list):
            raise DependentDirectoryReportError(
                "La configuración de exclusiones debe contener listas de rutas."
            )
        normalized = {
            cls._canonical_relative_directory(value)
            for value in values
        }
        return sorted(normalized)

    def load_exclusion_preferences(self) -> dict[str, Any]:
        """Load shared report exclusions, using the privacy folder as a default."""
        defaults = {
            "schema_version": 1,
            "excluded_directories": [],
            "included_directories": [],
            "default_excluded_directory_names": list(
                DEFAULT_EXCLUDED_DIRECTORY_NAMES
            ),
        }
        if not self.settings_path.exists():
            return defaults

        if self.settings_path.is_symlink():
            raise DependentDirectoryReportError(
                "El archivo de preferencias del reporte no puede ser un enlace simbólico."
            )

        try:
            payload = json.loads(
                self.settings_path.read_text(encoding="utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DependentDirectoryReportError(
                f"No se pudo leer la configuración de exclusiones: {error}"
            ) from error

        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise DependentDirectoryReportError(
                "La configuración de exclusiones tiene una versión o estructura no compatible."
            )

        excluded = self._normalise_exclusion_list(
            payload.get("excluded_directories", [])
        )
        included = self._normalise_exclusion_list(
            payload.get("included_directories", [])
        )
        overlap = set(excluded) & set(included)
        if overlap:
            raise DependentDirectoryReportError(
                "Una carpeta no puede estar excluida e incluida al mismo tiempo: "
                + ", ".join(sorted(overlap))
            )

        return {
            "schema_version": 1,
            "excluded_directories": excluded,
            "included_directories": included,
            "default_excluded_directory_names": list(
                DEFAULT_EXCLUDED_DIRECTORY_NAMES
            ),
        }

    def save_exclusion_preferences(
        self,
        excluded_directories: list[str],
        included_directories: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist the user's per-year folder exclusions in the Structure checkout."""
        excluded = self._normalise_exclusion_list(excluded_directories)
        included = self._normalise_exclusion_list(included_directories or [])
        overlap = set(excluded) & set(included)
        if overlap:
            raise DependentDirectoryReportError(
                "Una carpeta no puede estar excluida e incluida al mismo tiempo: "
                + ", ".join(sorted(overlap))
            )

        payload = {
            "schema_version": 1,
            "updated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "excluded_directories": excluded,
            "included_directories": included,
            "default_excluded_directory_names": list(
                DEFAULT_EXCLUDED_DIRECTORY_NAMES
            ),
        }
        self._atomic_json_write(self.settings_path, payload)
        return payload

    @classmethod
    def _is_excluded(
        cls,
        relative_path: str,
        folder_name: str,
        preferences: dict[str, Any],
    ) -> bool:
        key = cls._canonical_relative_directory(relative_path)
        if key in set(preferences.get("included_directories", [])):
            return False
        if key in set(preferences.get("excluded_directories", [])):
            return True

        default_names = {
            str(name).strip().casefold()
            for name in DEFAULT_EXCLUDED_DIRECTORY_NAMES
        }
        return str(folder_name).casefold() in default_names

    def list_year_directory_options(
        self,
        preferences: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """List each year and its immediate folders for the exclusion tree."""
        root = self.base_path.resolve()
        if not root.exists() or not root.is_dir():
            raise DependentDirectoryReportError(
                f"La unidad dependiente no está disponible o no es un directorio:\n{root}"
            )

        current_preferences = (
            preferences
            if preferences is not None
            else self.load_exclusion_preferences()
        )
        years: list[dict[str, Any]] = []
        for year_entry in self._directory_entries(root):
            if not _YEAR_DIRECTORY_PATTERN.fullmatch(year_entry.name):
                continue

            folders = []
            for folder_entry in self._directory_entries(Path(year_entry.path)):
                relative_path = f"{year_entry.name}/{folder_entry.name}"
                folders.append(
                    {
                        "name": folder_entry.name,
                        "relative_path": relative_path,
                        "excluded": self._is_excluded(
                            relative_path,
                            folder_entry.name,
                            current_preferences,
                        ),
                    }
                )
            years.append(
                {
                    "year": year_entry.name,
                    "folders": folders,
                }
            )
        return years

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
        year_name: str,
        album_prefix: str,
        character_entries: list[os.DirEntry[str]],
    ) -> list[dict[str, Any]]:
        """Create report references for the already-enumerated album children."""
        records: list[dict[str, Any]] = []

        for character_entry in character_entries:
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

            expected_filename = f"__{identity['name']}__.json".casefold()
            preferred_index = next(
                (
                    index for index, candidate in enumerate(candidates)
                    if candidate.name.casefold() == expected_filename
                ),
                None,
            )
            if preferred_index is not None:
                status = (
                    "found"
                    if len(credential_files) == 1
                    else "found_with_additional_candidates"
                )
                selected = credential_files[preferred_index]
            elif len(credential_files) == 1:
                status = "found"
                selected = credential_files[0]
            elif credential_files:
                status = "ambiguous"
                selected = None
            else:
                status = "missing"
                selected = None

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

    def build_report(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Build the report while reporting the current year and folder."""
        root = self.base_path.resolve()
        if not root.exists() or not root.is_dir():
            raise DependentDirectoryReportError(
                f"La unidad dependiente no está disponible o no es un directorio:\n{root}"
            )

        preferences = self.load_exclusion_preferences()
        year_entries = [
            entry
            for entry in self._directory_entries(root)
            if _YEAR_DIRECTORY_PATTERN.fullmatch(entry.name)
        ]

        # Prepare a shallow scan plan so progress has a real total.
        # Excluded folders are never enumerated below their year-level directory.
        year_plans: list[dict[str, Any]] = []
        for year_entry in year_entries:
            year_name = year_entry.name
            if progress_callback is not None:
                progress_callback(0, 0, f"Preparando el año {year_name}…")

            first_level = self._directory_entries(Path(year_entry.path))
            folder_plans = []
            for first_entry in first_level:
                relative_path = f"{year_name}/{first_entry.name}"
                excluded = self._is_excluded(
                    relative_path,
                    first_entry.name,
                    preferences,
                )
                second_level = (
                    []
                    if excluded
                    else self._directory_entries(Path(first_entry.path))
                )
                folder_plans.append(
                    {
                        "entry": first_entry,
                        "relative_path": relative_path,
                        "excluded": excluded,
                        "second_level": second_level,
                    }
                )
                if progress_callback is not None:
                    state = "excluida" if excluded else "lista"
                    progress_callback(
                        0,
                        0,
                        f"Preparando carpeta {year_name}/{first_entry.name} ({state})…",
                    )

            year_plans.append(
                {
                    "entry": year_entry,
                    "folders": folder_plans,
                }
            )

        total_steps = sum(
            1
            + len(year_plan["folders"])
            + sum(
                len(folder_plan["second_level"])
                for folder_plan in year_plan["folders"]
            )
            for year_plan in year_plans
        )
        completed_steps = 0

        def advance(message: str) -> None:
            nonlocal completed_steps
            completed_steps += 1
            if progress_callback is not None:
                progress_callback(
                    completed_steps,
                    total_steps,
                    message,
                )

        directories: list[dict[str, Any]] = []
        year_names: list[str] = []
        character_credentials: list[dict[str, Any]] = []
        excluded_directory_paths: list[str] = []

        for year_plan in year_plans:
            year_entry = year_plan["entry"]
            year_name = year_entry.name
            year_names.append(year_name)
            directories.append(
                {
                    "year": year_name,
                    "relative_path": year_name,
                    "depth_after_year": 0,
                }
            )
            advance(f"Año {year_name}")

            album_name = f"{max(0, int(year_name) - 2003):02d}. album"
            album_prefix = album_name.split(".", 1)[0]

            for folder_plan in year_plan["folders"]:
                first_entry = folder_plan["entry"]
                first_relative = f"{year_name}\\{first_entry.name}"

                if folder_plan["excluded"]:
                    excluded_directory_paths.append(
                        folder_plan["relative_path"]
                    )
                    advance(
                        f"Carpeta omitida: {year_name}/{first_entry.name}"
                    )
                    continue

                directories.append(
                    {
                        "year": year_name,
                        "relative_path": first_relative,
                        "depth_after_year": 1,
                    }
                )
                advance(f"Carpeta {year_name}/{first_entry.name}")

                second_level = folder_plan["second_level"]
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
                    advance(
                        f"Carpeta {year_name}/{first_entry.name}/{second_entry.name}"
                    )

                if first_entry.name.casefold() == album_name.casefold():
                    character_credentials.extend(
                        self._character_credential_records(
                            root,
                            year_name,
                            album_prefix,
                            second_level,
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
            item["credential_status"] in {
                "found",
                "found_with_additional_candidates",
            }
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
        additional_candidate_count = sum(
            item["credential_status"] == "found_with_additional_candidates"
            for item in character_credentials
        )

        return {
            "schema_version": 3,
            "generated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "root_path": str(root),
            "max_subfolder_levels_after_year": (
                MAX_SUBFOLDER_LEVELS_AFTER_YEAR
            ),
            "year_count": len(year_names),
            "directory_count": len(directories),
            "excluded_directory_count": len(excluded_directory_paths),
            "excluded_directories": sorted(
                excluded_directory_paths,
                key=str.casefold,
            ),
            "character_count": len(character_credentials),
            "credential_file_count": credential_file_count,
            "credential_found_count": found_count,
            "credential_missing_count": missing_count,
            "credential_ambiguous_count": ambiguous_count,
            "credential_additional_candidates_count": additional_candidate_count,
            "directories": directories,
            "character_credentials": character_credentials,
        }

    @staticmethod
    def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
        if not path.parent.is_dir():
            raise DependentDirectoryReportError(
                "No existe el directorio del repositorio Structure:\n"
                f"{path.parent}"
            )

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
                json.dump(
                    payload,
                    temporary_file,
                    ensure_ascii=False,
                    indent=2,
                )
                temporary_file.write("\n")

            os.replace(temporary_path, path)
        except OSError as error:
            raise DependentDirectoryReportError(
                f"No se pudo escribir el archivo:\n{path}\n\n{error}"
            ) from error
        finally:
            if temporary_path is not None and temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    def generate_or_update(
        self,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        """Build the report and replace the previous report atomically."""
        report = self.build_report(progress_callback=progress_callback)
        self._atomic_json_write(self.report_path, report)
        return {
            "report_path": str(self.report_path),
            "root_path": report["root_path"],
            "year_count": report["year_count"],
            "directory_count": report["directory_count"],
            "excluded_directory_count": report["excluded_directory_count"],
            "excluded_directories": report["excluded_directories"],
            "character_count": report["character_count"],
            "credential_file_count": report["credential_file_count"],
            "credential_found_count": report["credential_found_count"],
            "credential_missing_count": report["credential_missing_count"],
            "credential_ambiguous_count": report["credential_ambiguous_count"],
            "credential_additional_candidates_count": (
                report["credential_additional_candidates_count"]
            ),
            "max_subfolder_levels_after_year": (
                report["max_subfolder_levels_after_year"]
            ),
            "generated_at": report["generated_at"],
        }
