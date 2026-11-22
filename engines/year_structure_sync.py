"""Rebuild Structure/folders.json from the real directory trees of all years."""
from __future__ import annotations

import json
import os
import re
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engines.structure_paths import get_structure_backup_root
from engines.year_structure import (
    is_real_directory,
    normalize_directory_category,
    strip_numeric_directory_prefix,
)


_YEAR_DIRECTORY = re.compile(r"^\d{4}$")
_REPARSE_POINT = 0x400


class YearStructureSyncError(RuntimeError):
    """Raised when the physical year structure cannot be synchronized safely."""


class YearStructureSyncService:
    """Build folders.json from the union of all valid year directories.

    Categories and subfolders are retained while they exist in at least one
    year. Numeric year prefixes are removed, and dynamic season names collapse
    to the stable folders.json key `___[]`.
    """

    def __init__(
        self,
        dependent_root: str | Path,
        folders_json_path: str | Path,
        backup_root: str | Path | None = None,
    ) -> None:
        self.dependent_root = Path(dependent_root).expanduser()
        self.folders_json_path = Path(folders_json_path).expanduser()
        self.backup_root = (
            Path(backup_root).expanduser()
            if backup_root is not None
            else get_structure_backup_root() / "year_structure_sync"
        )

    @staticmethod
    def _is_regular_file(path: Path) -> bool:
        try:
            info = path.lstat()
        except FileNotFoundError:
            return False
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise YearStructureSyncError(
                f"El archivo no es un archivo regular: {path}"
            )
        if getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
            raise YearStructureSyncError(
                f"El archivo es un punto de reanálisis de Windows: {path}"
            )
        return True

    def _year_directories(self) -> list[Path]:
        if not is_real_directory(self.dependent_root):
            raise YearStructureSyncError(
                f"La unidad dependiente no está disponible o no es una carpeta real: "
                f"{self.dependent_root}"
            )
        try:
            years = [
                item
                for item in self.dependent_root.iterdir()
                if _YEAR_DIRECTORY.fullmatch(item.name)
                and is_real_directory(item)
            ]
        except OSError as error:
            raise YearStructureSyncError(
                f"No se pudo examinar la unidad dependiente: {error}"
            ) from error

        years.sort(key=lambda item: int(item.name), reverse=True)
        if not years:
            raise YearStructureSyncError(
                "No se encontraron carpetas de año de cuatro dígitos. "
                "folders.json no se modificó."
            )
        return years

    @staticmethod
    def _display_name(folder_name: str) -> str:
        clean_name = strip_numeric_directory_prefix(folder_name)
        if normalize_directory_category(clean_name) == "___[]":
            return "___[]"
        return clean_name.strip()

    def _read_current_data(self) -> tuple[dict[str, Any], bytes | None]:
        path = self.folders_json_path
        if path.is_symlink():
            raise YearStructureSyncError(
                f"No se reemplazará un enlace simbólico: {path}"
            )
        if not self._is_regular_file(path):
            return {}, None

        try:
            raw_content = path.read_bytes()
            payload = json.loads(raw_content.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise YearStructureSyncError(
                f"No se pudo leer folders.json como JSON UTF-8 válido: {error}"
            ) from error

        if not isinstance(payload, dict):
            raise YearStructureSyncError(
                "folders.json debe contener un objeto JSON. No se modificó."
            )
        for category, subfolders in payload.items():
            if (
                not isinstance(category, str)
                or not category.strip()
                or not isinstance(subfolders, list)
                or not all(
                    isinstance(name, str) and name.strip()
                    for name in subfolders
                )
            ):
                raise YearStructureSyncError(
                    "folders.json tiene categorías o subcarpetas no válidas. "
                    "No se modificó."
                )
        return payload, raw_content

    @staticmethod
    def _ordered_names(
        discovered: dict[str, str],
        existing_names: list[str],
    ) -> list[str]:
        """Keep surviving JSON order, then append newly discovered names."""
        ordered_keys: list[str] = []
        seen: set[str] = set()
        for name in existing_names:
            key = normalize_directory_category(name)
            if key in discovered and key not in seen:
                ordered_keys.append(key)
                seen.add(key)
        for key in sorted(
            (key for key in discovered if key not in seen),
            key=lambda item: discovered[item].casefold(),
        ):
            ordered_keys.append(key)
        return ordered_keys

    def _build_from_years(
        self,
        years: list[Path],
    ) -> dict[str, dict[str, Any]]:
        discovered: dict[str, dict[str, Any]] = {}
        for year_dir in years:
            try:
                top_level = sorted(
                    (
                        item for item in year_dir.iterdir()
                        if is_real_directory(item)
                    ),
                    key=lambda item: item.name.casefold(),
                )
            except OSError as error:
                raise YearStructureSyncError(
                    f"No se pudo leer la estructura del año {year_dir.name}: {error}"
                ) from error

            for category_dir in top_level:
                category_key = normalize_directory_category(category_dir.name)
                if not category_key:
                    continue
                category = discovered.setdefault(
                    category_key,
                    {
                        "name": self._display_name(category_dir.name),
                        "subfolders": {},
                    },
                )
                try:
                    children = sorted(
                        (
                            item for item in category_dir.iterdir()
                            if is_real_directory(item)
                        ),
                        key=lambda item: item.name.casefold(),
                    )
                except OSError as error:
                    raise YearStructureSyncError(
                        "No se pudo leer la categoría "
                        f"'{category_dir.name}' del año {year_dir.name}: {error}"
                    ) from error

                for child in children:
                    child_key = normalize_directory_category(child.name)
                    if not child_key:
                        continue
                    category["subfolders"].setdefault(
                        child_key,
                        self._display_name(child.name),
                    )
        return discovered

    @staticmethod
    def _existing_category(
        current: dict[str, Any],
        category_key: str,
    ) -> tuple[str | None, list[str]]:
        for name, subfolders in current.items():
            if normalize_directory_category(name) == category_key:
                return name, list(subfolders)
        return None, []

    def preview(self) -> dict[str, Any]:
        """Return the proposed JSON and a comparison without changing files."""
        years = self._year_directories()
        current, _raw = self._read_current_data()
        discovered = self._build_from_years(years)

        folders_data: dict[str, list[str]] = {}
        added_categories: list[str] = []
        added_subfolders: list[dict[str, str]] = []
        removed_subfolders: list[dict[str, str]] = []

        discovered_names = {
            key: value["name"] for key, value in discovered.items()
        }
        ordered_category_keys = self._ordered_names(
            discovered_names,
            list(current),
        )

        for category_key in ordered_category_keys:
            category_data = discovered[category_key]
            existing_name, existing_subfolders = self._existing_category(
                current,
                category_key,
            )
            category_name = category_data["name"]
            if existing_name is None:
                added_categories.append(category_name)

            child_names = category_data["subfolders"]
            ordered_child_keys = self._ordered_names(
                child_names,
                existing_subfolders,
            )
            folders_data[category_name] = [
                child_names[key] for key in ordered_child_keys
            ]

            existing_child_keys = {
                normalize_directory_category(name)
                for name in existing_subfolders
            }
            discovered_child_keys = set(child_names)
            for key in sorted(
                discovered_child_keys - existing_child_keys,
                key=lambda item: child_names[item].casefold(),
            ):
                added_subfolders.append(
                    {"category": category_name, "name": child_names[key]}
                )
            for name in existing_subfolders:
                key = normalize_directory_category(name)
                if key not in discovered_child_keys:
                    removed_subfolders.append(
                        {"category": existing_name or category_name, "name": name}
                    )

        removed_categories = [
            name
            for name in current
            if normalize_directory_category(name) not in discovered
        ]
        return {
            "years": [item.name for item in years],
            "year_count": len(years),
            "folders_data": folders_data,
            "category_count": len(folders_data),
            "subfolder_count": sum(len(items) for items in folders_data.values()),
            "added_categories": added_categories,
            "removed_categories": removed_categories,
            "added_subfolders": added_subfolders,
            "removed_subfolders": removed_subfolders,
            "changed": folders_data != current,
        }

    def _create_backup(self, original_bytes: bytes) -> Path:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        backup_path = self.backup_root / f"folders.json.{timestamp}.bak"
        try:
            with backup_path.open("xb") as backup_file:
                backup_file.write(original_bytes)
        except OSError as error:
            raise YearStructureSyncError(
                f"No se pudo respaldar folders.json. No se modificó el original: {error}"
            ) from error
        return backup_path

    def _write_atomic(self, payload: dict[str, list[str]]) -> None:
        parent = self.folders_json_path.parent
        parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                prefix=".folders.json.",
                suffix=".tmp",
                dir=parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(
                    payload,
                    temporary_file,
                    indent=2,
                    ensure_ascii=False,
                )
                temporary_file.write("\n")
            os.replace(temporary_path, self.folders_json_path)
        except OSError as error:
            raise YearStructureSyncError(
                f"No se pudo guardar folders.json: {error}"
            ) from error
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)

    def synchronize(self) -> dict[str, Any]:
        """Re-scan, back up the old JSON and atomically write the new structure."""
        preview = self.preview()
        if not preview["changed"]:
            return {
                **preview,
                "written": False,
                "backup_path": None,
                "message": "folders.json ya coincide con las carpetas de los años.",
            }

        _current, original_bytes = self._read_current_data()
        backup_path = (
            self._create_backup(original_bytes)
            if original_bytes is not None
            else None
        )
        self._write_atomic(preview["folders_data"])
        return {
            **preview,
            "written": True,
            "backup_path": str(backup_path) if backup_path else None,
            "message": "folders.json se sincronizó con la estructura de los años.",
        }
