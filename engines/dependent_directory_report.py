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
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from engines.year_structure import (
    normalize_directory_category,
    resolve_year_structure,
    strip_numeric_directory_prefix,
)


REPORT_FILENAME = "dependent_directory_report.json"
REPORT_SETTINGS_FILENAME = "dependent_directory_report_settings.json"
REPORT_TEXT_FILENAME = "dependent_directory_report.txt"
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
        structure_definition_path: str | Path | None = None,
        current_year: int | None = None,
    ) -> None:
        self.base_path = Path(base_path).expanduser()
        self.report_path = Path(report_path).expanduser()
        self.settings_path = (
            Path(settings_path).expanduser()
            if settings_path is not None
            else self.report_path.with_name(REPORT_SETTINGS_FILENAME)
        )
        self.structure_definition_path = (
            Path(structure_definition_path).expanduser()
            if structure_definition_path is not None
            else None
        )
        self.current_year = int(current_year or datetime.now().year)

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

    @classmethod
    def _directory_category_key(cls, folder_name: str) -> str:
        """Return the shared semantic key, including dynamic season folders."""
        return normalize_directory_category(folder_name)

    @classmethod
    def _directory_category_label(cls, folder_name: str) -> str:
        """Display all year-level categories with the neutral xx. prefix."""
        normalized = strip_numeric_directory_prefix(folder_name)
        if normalize_directory_category(normalized) == "___[]":
            return "xx. ___[...]"
        return f"xx. {normalized}"

    @classmethod
    def _normalise_directory_name_list(cls, values: Any) -> list[str]:
        if not isinstance(values, list):
            raise DependentDirectoryReportError(
                "La configuración de exclusiones debe contener una lista de nombres."
            )
        normalized = set()
        for value in values:
            if not isinstance(value, str):
                raise DependentDirectoryReportError(
                    "Cada nombre de carpeta excluida debe ser texto."
                )
            key = cls._directory_category_key(value)
            if not key or "/" in key or "\\" in key:
                raise DependentDirectoryReportError(
                    f"Nombre de carpeta no válido en las exclusiones: {value}"
                )
            normalized.add(key)
        return sorted(normalized)

    @classmethod
    def _normalise_legacy_path_list(cls, values: Any) -> list[str]:
        """Migrate schema-v1 year-relative paths to global folder categories."""
        if not isinstance(values, list):
            raise DependentDirectoryReportError(
                "La configuración anterior de exclusiones no contiene una lista."
            )
        names = set()
        for raw_path in values:
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise DependentDirectoryReportError(
                    "La configuración anterior contiene una ruta vacía."
                )
            parts = [
                part for part in raw_path.strip().replace("\\", "/").split("/")
                if part
            ]
            if (
                len(parts) < 2
                or not _YEAR_DIRECTORY_PATTERN.fullmatch(parts[0])
                or any(part in {".", ".."} for part in parts)
            ):
                raise DependentDirectoryReportError(
                    f"Ruta de exclusión anterior no válida: {raw_path}"
                )
            key = cls._directory_category_key(parts[-1])
            if key:
                names.add(key)
        return sorted(names)

    def load_exclusion_preferences(self) -> dict[str, Any]:
        """Load global folder-category exclusions, preserving older preferences."""
        defaults = {
            "schema_version": 2,
            "excluded_directory_names": [],
            "included_directory_names": [],
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

        if not isinstance(payload, dict):
            raise DependentDirectoryReportError(
                "La configuración de exclusiones no tiene una estructura compatible."
            )

        version = payload.get("schema_version")
        if version == 1:
            # Old settings were scoped to a year. Migrate each selected folder
            # to its semantic category so the same choice applies across years.
            excluded = set(
                self._normalise_legacy_path_list(
                    payload.get("excluded_directories", [])
                )
            )
            included = set(
                self._normalise_legacy_path_list(
                    payload.get("included_directories", [])
                )
            )
            # An explicit old inclusion is the clearest user override.
            excluded.difference_update(included)
        elif version == 2:
            excluded = set(
                self._normalise_directory_name_list(
                    payload.get("excluded_directory_names", [])
                )
            )
            included = set(
                self._normalise_directory_name_list(
                    payload.get("included_directory_names", [])
                )
            )
        else:
            raise DependentDirectoryReportError(
                "La configuración de exclusiones tiene una versión no compatible."
            )

        overlap = excluded & included
        if overlap:
            raise DependentDirectoryReportError(
                "Una categoría no puede estar excluida e incluida al mismo tiempo: "
                + ", ".join(sorted(overlap))
            )

        return {
            "schema_version": 2,
            "excluded_directory_names": sorted(excluded),
            "included_directory_names": sorted(included),
            "default_excluded_directory_names": list(
                DEFAULT_EXCLUDED_DIRECTORY_NAMES
            ),
        }

    def save_exclusion_preferences(
        self,
        excluded_directory_names: list[str],
        included_directory_names: list[str] | None = None,
    ) -> dict[str, Any]:
        """Persist global exclusions by semantic folder name."""
        excluded = set(
            self._normalise_directory_name_list(excluded_directory_names)
        )
        included = set(
            self._normalise_directory_name_list(included_directory_names or [])
        )
        overlap = excluded & included
        if overlap:
            raise DependentDirectoryReportError(
                "Una categoría no puede estar excluida e incluida al mismo tiempo: "
                + ", ".join(sorted(overlap))
            )

        payload = {
            "schema_version": 2,
            "updated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "excluded_directory_names": sorted(excluded),
            "included_directory_names": sorted(included),
            "default_excluded_directory_names": list(
                DEFAULT_EXCLUDED_DIRECTORY_NAMES
            ),
        }
        self._atomic_json_write(self.settings_path, payload)
        return payload

    @classmethod
    def is_default_excluded_directory_name(cls, folder_name: str) -> bool:
        """Match default exclusions independent of their numeric prefix."""
        return cls._directory_category_key(folder_name) in {
            cls._directory_category_key(name)
            for name in DEFAULT_EXCLUDED_DIRECTORY_NAMES
        }

    @classmethod
    def _is_excluded(
        cls,
        relative_path: str,
        folder_name: str,
        preferences: dict[str, Any],
    ) -> bool:
        del relative_path  # Exclusions are categories, not year-specific paths.
        key = cls._directory_category_key(folder_name)
        if key in set(preferences.get("included_directory_names", [])):
            return False
        if key in set(preferences.get("excluded_directory_names", [])):
            return True
        return cls.is_default_excluded_directory_name(folder_name)

    def list_directory_category_options(
        self,
        preferences: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """List categories defined by the same source used for year creation."""
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
        try:
            definition = resolve_year_structure(
                root,
                self.structure_definition_path,
                self.current_year,
            )
        except (OSError, ValueError) as error:
            raise DependentDirectoryReportError(
                f"No se pudo resolver la estructura de creación de años: {error}"
            ) from error

        expected_categories = definition["categories"]
        expected_counts: Counter[str] = Counter(
            self._directory_category_key(name)
            for name in expected_categories
        )
        category_labels = {
            self._directory_category_key(name): self._directory_category_label(name)
            for name in expected_categories
        }
        year_data: list[dict[str, Any]] = []
        mismatches: list[dict[str, Any]] = []

        for year_entry in self._directory_entries(root):
            if not _YEAR_DIRECTORY_PATTERN.fullmatch(year_entry.name):
                continue

            folder_entries = self._directory_entries(Path(year_entry.path))
            actual_counts: Counter[str] = Counter()
            actual_labels: dict[str, str] = {}
            for folder_entry in folder_entries:
                key = self._directory_category_key(folder_entry.name)
                actual_counts[key] += 1
                actual_labels.setdefault(
                    key,
                    self._directory_category_label(folder_entry.name),
                )

            missing_keys = list((expected_counts - actual_counts).elements())
            extra_keys = list((actual_counts - expected_counts).elements())
            if missing_keys or extra_keys:
                labels = {**actual_labels, **category_labels}
                mismatches.append(
                    {
                        "year": year_entry.name,
                        "expected_folder_count": sum(expected_counts.values()),
                        "actual_folder_count": len(folder_entries),
                        "missing": [
                            labels.get(key, key)
                            for key in sorted(set(missing_keys))
                        ],
                        "extra": [
                            labels.get(key, key)
                            for key in sorted(set(extra_keys))
                        ],
                    }
                )

            year_data.append(
                {
                    "year": year_entry.name,
                    "category_counts": actual_counts,
                }
            )

        year_data.sort(key=lambda item: item["year"])
        options = []
        for key in sorted(expected_counts):
            years_present = sum(
                item["category_counts"].get(key, 0) > 0
                for item in year_data
            )
            options.append(
                {
                    "key": key,
                    "name": category_labels.get(key, key),
                    "excluded": self._is_excluded(
                        "",
                        key,
                        current_preferences,
                    ),
                    "years_present": years_present,
                    "directory_count": expected_counts[key] * len(year_data),
                }
            )

        return {
            "years": [item["year"] for item in year_data],
            "year_count": len(year_data),
            "categories": options,
            "structure_consistent": not mismatches,
            "reference_folder_count": sum(expected_counts.values()),
            "structure_source": definition["source"],
            "template_year": definition["template_year"],
            "mismatches": mismatches,
        }

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

        # Resolve the expected layout through the exact source used by year creation:
        # folders.json first, then the same fallback-template year selection.
        try:
            definition = resolve_year_structure(
                root,
                self.structure_definition_path,
                self.current_year,
            )
        except (OSError, ValueError) as error:
            raise DependentDirectoryReportError(
                f"No se pudo resolver la estructura de creación de años: {error}"
            ) from error

        expected_counts: Counter[str] = Counter(
            self._directory_category_key(name)
            for name in definition["categories"]
        )
        category_labels = {
            self._directory_category_key(name): self._directory_category_label(name)
            for name in definition["categories"]
        }
        year_first_levels: list[
            tuple[os.DirEntry[str], list[os.DirEntry[str]]]
        ] = []
        mismatches: list[dict[str, Any]] = []

        for year_entry in year_entries:
            first_level = self._directory_entries(Path(year_entry.path))
            actual_counts: Counter[str] = Counter()
            actual_labels: dict[str, str] = {}
            for folder_entry in first_level:
                key = self._directory_category_key(folder_entry.name)
                actual_counts[key] += 1
                actual_labels.setdefault(
                    key,
                    self._directory_category_label(folder_entry.name),
                )

            missing_keys = list((expected_counts - actual_counts).elements())
            extra_keys = list((actual_counts - expected_counts).elements())
            if missing_keys or extra_keys:
                labels = {**actual_labels, **category_labels}
                mismatches.append(
                    {
                        "year": year_entry.name,
                        "expected_folder_count": sum(expected_counts.values()),
                        "actual_folder_count": len(first_level),
                        "missing": [
                            labels.get(key, key)
                            for key in sorted(set(missing_keys))
                        ],
                        "extra": [
                            labels.get(key, key)
                            for key in sorted(set(extra_keys))
                        ],
                    }
                )
            year_first_levels.append((year_entry, first_level))

        if mismatches:
            details = []
            for mismatch in mismatches:
                message = (
                    f"{mismatch['year']}: {mismatch['actual_folder_count']} carpetas "
                    f"(se esperaban {mismatch['expected_folder_count']})"
                )
                if mismatch["missing"]:
                    message += "; faltan: " + ", ".join(mismatch["missing"])
                if mismatch["extra"]:
                    message += "; sobran: " + ", ".join(mismatch["extra"])
                details.append(message)
            source_description = definition["source"]
            if definition["template_year"]:
                source_description += f" ({definition['template_year']})"
            raise DependentDirectoryReportError(
                "La estructura de carpetas no coincide con la plantilla usada "
                f"por AnuarySignature para crear años: {source_description}.\n"
                + "\n".join(details)
            )

        # Prepare a shallow scan plan so progress has a real total.
        # Excluded folders are never enumerated below their year-level directory.
        year_plans: list[dict[str, Any]] = []
        for year_entry, first_level in year_first_levels:
            year_name = year_entry.name
            if progress_callback is not None:
                progress_callback(0, 0, f"Preparando el año {year_name}…")

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
            "schema_version": 5,
            "generated_at": datetime.now().astimezone().isoformat(
                timespec="seconds"
            ),
            "root_path": str(root),
            "structure_source": definition["source"],
            "template_year": definition["template_year"],
            "expected_folder_count": sum(expected_counts.values()),
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
            "excluded_directory_names": sorted(
                preferences.get("excluded_directory_names", [])
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
    def render_tree_text(report: dict[str, Any]) -> str:
        """Render the inventory and credential references as a plain-text tree."""
        root_node: dict[str, Any] = {
            "name": Path(report["root_path"]).name or report["root_path"],
            "kind": "directory",
            "children": {},
            "annotation": "",
        }

        def ensure_directory(parts: list[str]) -> dict[str, Any]:
            node = root_node
            for part in parts:
                key = "dir:" + part.casefold()
                child = node["children"].get(key)
                if child is None:
                    child = {
                        "name": part,
                        "kind": "directory",
                        "children": {},
                        "annotation": "",
                    }
                    node["children"][key] = child
                node = child
            return node

        for directory in report.get("directories", []):
            parts = [
                part for part in str(directory["relative_path"]).replace("\\", "/").split("/")
                if part
            ]
            ensure_directory(parts)

        status_annotations = {
            "missing": " [credencial no encontrada]",
            "ambiguous": " [credenciales ambiguas]",
            "found_with_additional_candidates": (
                " [credencial principal y archivos adicionales]"
            ),
        }
        for character in report.get("character_credentials", []):
            folder_parts = [
                part for part in str(
                    character.get("character_relative_path", "")
                ).replace("\\", "/").split("/")
                if part
            ]
            character_node = ensure_directory(folder_parts)
            character_node["annotation"] = status_annotations.get(
                character.get("credential_status"),
                "",
            )
            for credential in character.get("credential_files", []):
                file_parts = [
                    part for part in str(
                        credential.get("relative_path", "")
                    ).replace("\\", "/").split("/")
                    if part
                ]
                if not file_parts:
                    continue
                parent_node = ensure_directory(file_parts[:-1])
                file_name = file_parts[-1]
                file_key = "file:" + file_name.casefold()
                parent_node["children"].setdefault(
                    file_key,
                    {
                        "name": file_name,
                        "kind": "file",
                        "children": {},
                        "annotation": "",
                    },
                )

        tree_lines: list[str] = []

        def append_children(node: dict[str, Any], prefix: str) -> None:
            children = sorted(
                node["children"].values(),
                key=lambda item: (
                    item["kind"] == "file",
                    item["name"].casefold(),
                ),
            )
            for index, child in enumerate(children):
                is_last = index == len(children) - 1
                connector = "└── " if is_last else "├── "
                tree_lines.append(
                    prefix + connector + child["name"] + child["annotation"]
                )
                if child["kind"] == "directory" and child["children"]:
                    append_children(
                        child,
                        prefix + ("    " if is_last else "│   "),
                    )

        append_children(root_node, "")
        excluded = report.get("excluded_directories", [])
        lines = [
            "REPORTE DE UNIDAD DEPENDIENTE",
            f"Unidad: {report.get('root_path', '')}",
            f"Generado: {report.get('generated_at', '')}",
            (
                "Estructura de referencia: "
                + str(report.get("structure_source", "desconocida"))
                + (
                    f" (año plantilla {report['template_year']})"
                    if report.get("template_year")
                    else ""
                )
            ),
            f"Carpetas esperadas por año: {report.get('expected_folder_count', 0)}",
            f"Años: {report.get('year_count', 0)}",
            f"Directorios registrados: {report.get('directory_count', 0)}",
            f"Carpetas excluidas: {report.get('excluded_directory_count', 0)}",
            f"Personajes: {report.get('character_count', 0)}",
            f"Credenciales encontradas: {report.get('credential_found_count', 0)}",
            f"Credenciales ausentes: {report.get('credential_missing_count', 0)}",
            f"Credenciales ambiguas: {report.get('credential_ambiguous_count', 0)}",
            "",
            "EXCLUSIONES:",
        ]
        lines.extend(
            f"  - {relative_path}" for relative_path in excluded
        )
        if not excluded:
            lines.append("  - Ninguna")
        lines.extend(["", "ÁRBOL DE DIRECTORIOS:"])
        lines.extend(tree_lines or ["  (sin directorios)"])
        return "\n".join(lines) + "\n"

    @staticmethod
    def _atomic_text_write(path: Path, content: str) -> None:
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
                temporary_file.write(content)

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
        report_format: str = "json",
    ) -> dict[str, Any]:
        """Generate either the structured JSON report or its plain-text tree."""
        selected_format = str(report_format or "json").strip().casefold()
        if selected_format not in {"json", "txt"}:
            raise DependentDirectoryReportError(
                f"Formato de reporte no compatible: {report_format}"
            )

        report = self.build_report(progress_callback=progress_callback)
        if selected_format == "json":
            output_path = self.report_path
            self._atomic_json_write(output_path, report)
        else:
            output_path = self.report_path.with_name(REPORT_TEXT_FILENAME)
            self._atomic_text_write(
                output_path,
                self.render_tree_text(report),
            )

        return {
            "report_path": str(output_path),
            "report_format": selected_format,
            "root_path": report["root_path"],
            "structure_source": report["structure_source"],
            "template_year": report["template_year"],
            "expected_folder_count": report["expected_folder_count"],
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
