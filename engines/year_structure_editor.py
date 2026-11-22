"""Safe editing and propagation of the folders.json year template."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from engines.year_structure import is_real_directory


_YEAR_PATTERN = re.compile(r"^\d{4}$")
_INVALID_WINDOWS_NAME_CHARACTERS = set('<>:"/\\|?*')


class YearStructureEditorError(RuntimeError):
    """Raised when a year-template edit cannot be applied safely."""


class YearStructureEditorService:
    """Edit folders.json and synchronize managed directory names across years.

    Existing directories removed from the template are deliberately retained.
    New template directories are created empty. Renames never overwrite content.
    """

    def __init__(
        self,
        base_path: str | Path,
        folders_json_path: str | Path,
    ) -> None:
        self.base_path = Path(base_path).expanduser()
        self.folders_json_path = Path(folders_json_path).expanduser()

    @staticmethod
    def _validate_name(value: Any, context: str) -> str:
        if not isinstance(value, str) or not value:
            raise YearStructureEditorError(
                f"El nombre de {context} debe ser texto no vacío."
            )
        if value != value.strip() or value in {".", ".."}:
            raise YearStructureEditorError(
                f"El nombre de {context} no puede tener espacios exteriores ni ser '.' o '..'."
            )
        if value.endswith(".") or value.endswith(" "):
            raise YearStructureEditorError(
                f"El nombre de {context} no puede terminar en punto o espacio."
            )
        if any(character in _INVALID_WINDOWS_NAME_CHARACTERS for character in value):
            raise YearStructureEditorError(
                f"El nombre de {context} contiene caracteres no válidos: {value}"
            )
        if any(ord(character) < 32 for character in value):
            raise YearStructureEditorError(
                f"El nombre de {context} contiene caracteres de control."
            )
        return value

    @classmethod
    def validate_template(cls, payload: Any) -> dict[str, list[str]]:
        if not isinstance(payload, dict) or not payload:
            raise YearStructureEditorError(
                "folders.json debe contener un objeto JSON no vacío."
            )

        template: dict[str, list[str]] = {}
        seen_roots: set[str] = set()
        for raw_name, raw_subfolders in payload.items():
            name = cls._validate_name(raw_name, "la carpeta principal")
            folded_name = name.casefold()
            if folded_name in seen_roots:
                raise YearStructureEditorError(
                    f"Hay carpetas principales duplicadas: {name}"
                )
            seen_roots.add(folded_name)

            if not isinstance(raw_subfolders, list):
                raise YearStructureEditorError(
                    f"Las subcarpetas de '{name}' deben ser una lista."
                )

            subfolders: list[str] = []
            seen_subfolders: set[str] = set()
            for raw_subfolder in raw_subfolders:
                subfolder = cls._validate_name(
                    raw_subfolder,
                    f"la subcarpeta de '{name}'",
                )
                if subfolder == "___[]":
                    raise YearStructureEditorError(
                        "El marcador ___[] solo puede utilizarse como carpeta principal."
                    )
                folded_subfolder = subfolder.casefold()
                if folded_subfolder in seen_subfolders:
                    raise YearStructureEditorError(
                        f"Hay subcarpetas duplicadas en '{name}': {subfolder}"
                    )
                seen_subfolders.add(folded_subfolder)
                subfolders.append(subfolder)

            template[name] = subfolders

        return template

    def load_template(self) -> dict[str, list[str]]:
        path = self.folders_json_path
        if path.is_symlink():
            raise YearStructureEditorError(
                "folders.json no puede ser un enlace simbólico."
            )
        try:
            with path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
        except FileNotFoundError as error:
            raise YearStructureEditorError(
                f"No se encontró la plantilla: {path}"
            ) from error
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise YearStructureEditorError(
                f"No se pudo leer folders.json: {error}"
            ) from error
        return self.validate_template(payload)

    @classmethod
    def _build_rows_template(
        cls,
        rows: list[dict[str, Any]],
        original_template: dict[str, list[str]],
    ) -> dict[str, list[str]]:
        template: dict[str, list[str]] = {}
        seen_original_roots: set[str] = set()

        for row in rows:
            if not isinstance(row, dict):
                raise YearStructureEditorError("La estructura editada contiene una fila no válida.")

            old_name = row.get("old_name")
            if old_name is not None:
                if old_name not in original_template:
                    raise YearStructureEditorError(
                        f"La carpeta original ya no existe en folders.json: {old_name}"
                    )
                if old_name in seen_original_roots:
                    raise YearStructureEditorError(
                        f"La carpeta original aparece más de una vez: {old_name}"
                    )
                seen_original_roots.add(old_name)

            name = cls._validate_name(row.get("name"), "la carpeta principal")
            raw_children = row.get("subfolders", [])
            if not isinstance(raw_children, list):
                raise YearStructureEditorError(
                    f"Las subcarpetas de '{name}' no tienen una estructura válida."
                )

            children: list[str] = []
            seen_original_children: set[str] = set()
            for child in raw_children:
                if not isinstance(child, dict):
                    raise YearStructureEditorError(
                        f"Hay una subcarpeta no válida dentro de '{name}'."
                    )
                old_child = child.get("old_name")
                if old_child is not None:
                    if old_name is None or old_child not in original_template[old_name]:
                        raise YearStructureEditorError(
                            f"La subcarpeta original no corresponde a '{name}': {old_child}"
                        )
                    if old_child in seen_original_children:
                        raise YearStructureEditorError(
                            f"La subcarpeta original aparece más de una vez: {old_child}"
                        )
                    seen_original_children.add(old_child)

                child_name = cls._validate_name(
                    child.get("name"),
                    f"la subcarpeta de '{name}'",
                )
                if child_name == "___[]":
                    raise YearStructureEditorError(
                        "El marcador ___[] solo puede utilizarse como carpeta principal."
                    )
                children.append(child_name)

            if name in template:
                raise YearStructureEditorError(
                    f"Hay carpetas principales duplicadas: {name}"
                )
            template[name] = children

        if "___[]" in original_template:
            if "___[]" not in seen_original_roots or "___[]" not in template:
                raise YearStructureEditorError(
                    "La carpeta ___[] es un marcador reservado para el nombre de temporada "
                    "y no se puede eliminar ni renombrar."
                )
            marker_row = next(row for row in rows if row.get("old_name") == "___[]")
            if marker_row.get("name") != "___[]":
                raise YearStructureEditorError(
                    "La carpeta ___[] es un marcador reservado para el nombre de temporada "
                    "y no se puede renombrar."
                )

        return cls.validate_template(template)

    @staticmethod
    def _prefix(year: int) -> str:
        return f"{max(0, year - 2003):02d}"

    @staticmethod
    def _validate_season_name(value: Any, year: int) -> str:
        """Reject season metadata that could escape or corrupt a year path."""
        season_name = str(value or "").strip()
        invalid = (
            not season_name
            or season_name in {".", ".."}
            or any(
                character in _INVALID_WINDOWS_NAME_CHARACTERS
                or ord(character) < 32
                for character in season_name
            )
        )
        if invalid:
            raise YearStructureEditorError(
                f"El nombre de temporada del año {year} está vacío o contiene "
                "caracteres no válidos para una carpeta."
            )
        return season_name

    @staticmethod
    def _directory_exists(path: Path, description: str) -> bool:
        if path.is_symlink():
            raise YearStructureEditorError(
                f"No se modifican enlaces simbólicos: {path}"
            )
        if path.exists() and not is_real_directory(path):
            raise YearStructureEditorError(
                f"La ruta existe pero no es un directorio real: {path}"
            )
        return is_real_directory(path)

    def _season_name(self, year_path: Path, year: int, prefix: str) -> str:
        marker_pattern = re.compile(
            rf"^{re.escape(prefix)}\. ___\[(?P<season>.*)\]$"
        )
        matches = []
        try:
            for entry in year_path.iterdir():
                if is_real_directory(entry) and marker_pattern.fullmatch(entry.name):
                    matches.append(marker_pattern.fullmatch(entry.name).group("season"))
        except OSError as error:
            raise YearStructureEditorError(
                f"No se pudo leer el año {year}: {error}"
            ) from error

        if len(matches) > 1:
            raise YearStructureEditorError(
                f"El año {year} contiene más de una carpeta de temporada."
            )
        if matches:
            return self._validate_season_name(matches[0], year)

        identity_path = (
            year_path
            / f"{prefix}. identity"
            / f"The_ID_Year_{year}.json"
        )
        if identity_path.is_symlink():
            raise YearStructureEditorError(
                f"La credencial de año no puede ser un enlace simbólico: {identity_path}"
            )
        try:
            with identity_path.open("r", encoding="utf-8") as file:
                payload = json.load(file)
            year_data = payload.get("year_data", {}) if isinstance(payload, dict) else {}
            season_name = year_data.get("season_name", "") if isinstance(year_data, dict) else ""
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            season_name = ""

        return self._validate_season_name(season_name, year)

    def _year_folder_path(
        self,
        year_path: Path,
        year: int,
        prefix: str,
        category: str,
    ) -> Path:
        if category == "___[]":
            season_name = self._season_name(year_path, year, prefix)
            return year_path / f"{prefix}. ___[{season_name}]"
        return year_path / f"{prefix}. {category}"

    def _build_plan(
        self,
        rows: list[dict[str, Any]],
        original_template: dict[str, list[str]],
    ) -> dict[str, Any]:
        if not self.base_path.is_dir():
            raise YearStructureEditorError(
                f"La unidad dependiente no está disponible: {self.base_path}"
            )

        original = self.validate_template(original_template)
        current_on_disk = self.load_template()
        if current_on_disk != original:
            raise YearStructureEditorError(
                "folders.json cambió desde que se abrió el editor. "
                "Cierra el diálogo y vuelve a cargar la plantilla antes de editar."
            )

        new_template = self._build_rows_template(rows, original)
        root_renames: list[tuple[Path, Path]] = []
        child_renames: list[tuple[Path, str, str, str]] = []
        directories_to_create: set[Path] = set()
        years: list[tuple[int, Path]] = []

        try:
            year_paths = sorted(
                (
                    entry
                    for entry in self.base_path.iterdir()
                    if _YEAR_PATTERN.fullmatch(entry.name)
                    and is_real_directory(entry)
                ),
                key=lambda entry: entry.name,
            )
        except OSError as error:
            raise YearStructureEditorError(
                f"No se pudieron enumerar los años de la unidad dependiente: {error}"
            ) from error

        for year_path in year_paths:
            year = int(year_path.name)
            prefix = self._prefix(year)
            years.append((year, year_path))

            for row in rows:
                old_name = row.get("old_name")
                new_name = row["name"]

                old_path = (
                    self._year_folder_path(year_path, year, prefix, old_name)
                    if old_name is not None
                    else None
                )
                new_path = self._year_folder_path(
                    year_path,
                    year,
                    prefix,
                    new_name,
                )

                old_exists = (
                    self._directory_exists(old_path, "carpeta original")
                    if old_path is not None
                    else False
                )
                new_exists = self._directory_exists(new_path, "carpeta destino")

                if old_exists:
                    parent_before = old_path
                    parent_after = new_path
                    if old_path != new_path:
                        if new_exists:
                            raise YearStructureEditorError(
                                "No se puede renombrar porque ya existe la carpeta destino:\\n"
                                f"{new_path}"
                            )
                        root_renames.append((old_path, new_path))
                else:
                    parent_before = new_path
                    parent_after = new_path
                    if not new_exists:
                        directories_to_create.add(new_path)

                for child in row.get("subfolders", []):
                    old_child = child.get("old_name")
                    new_child = child["name"]
                    target_before = (
                        parent_before / f"{prefix}. {new_child}"
                    )

                    if old_child is None:
                        if not self._directory_exists(
                            target_before,
                            "nueva subcarpeta",
                        ):
                            directories_to_create.add(
                                parent_after / f"{prefix}. {new_child}"
                            )
                        continue

                    source_before = parent_before / f"{prefix}. {old_child}"
                    source_exists = self._directory_exists(
                        source_before,
                        "subcarpeta original",
                    )
                    target_exists = self._directory_exists(
                        target_before,
                        "subcarpeta destino",
                    )

                    if source_exists and old_child != new_child:
                        if target_exists and target_before != source_before:
                            raise YearStructureEditorError(
                                "No se puede renombrar porque ya existe la subcarpeta destino:\\n"
                                f"{target_before}"
                            )
                        child_renames.append(
                            (parent_after, prefix, old_child, new_child)
                        )
                    elif not source_exists and not target_exists:
                        directories_to_create.add(
                            parent_after / f"{prefix}. {new_child}"
                        )

        return {
            "template": new_template,
            "years": years,
            "root_renames": root_renames,
            "child_renames": child_renames,
            "directories_to_create": sorted(
                directories_to_create,
                key=lambda path: (len(path.parts), str(path).casefold()),
            ),
            "renamed_count": len(root_renames) + len(child_renames),
            "created_count": len(directories_to_create),
            "year_count": len(years),
            "changed": new_template != original,
        }

    def preview_template_rows(
        self,
        rows: list[dict[str, Any]],
        original_template: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Validate edits and return the number of planned directory operations."""
        plan = self._build_plan(rows, original_template)
        return {
            "changed": plan["changed"],
            "year_count": plan["year_count"],
            "renamed_count": plan["renamed_count"],
            "created_count": plan["created_count"],
            "root_renamed_count": len(plan["root_renames"]),
            "subfolder_renamed_count": len(plan["child_renames"]),
        }

    def _write_template_atomically(self, template: dict[str, list[str]]) -> None:
        path = self.folders_json_path
        if path.is_symlink():
            raise YearStructureEditorError(
                "folders.json no puede ser un enlace simbólico."
            )

        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                newline="\n",
                dir=str(path.parent),
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as file:
                temporary_path = Path(file.name)
                json.dump(template, file, indent=2, ensure_ascii=False)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, path)
        except OSError as error:
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass
            raise YearStructureEditorError(
                f"No se pudo guardar folders.json: {error}"
            ) from error

    def apply_template_rows(
        self,
        rows: list[dict[str, Any]],
        original_template: dict[str, list[str]],
    ) -> dict[str, Any]:
        """Apply directory operations transactionally, then replace folders.json."""
        plan = self._build_plan(rows, original_template)
        if not plan["changed"]:
            return {
                "changed": False,
                "year_count": plan["year_count"],
                "renamed_count": 0,
                "created_count": 0,
                "template": plan["template"],
            }

        applied_renames: list[tuple[Path, Path]] = []
        created_directories: list[Path] = []
        try:
            for source, target in plan["root_renames"]:
                if not self._directory_exists(source, "carpeta original"):
                    raise YearStructureEditorError(
                        f"La carpeta original cambió durante la operación: {source}"
                    )
                if target.exists():
                    raise YearStructureEditorError(
                        f"La carpeta destino apareció durante la operación: {target}"
                    )
                source.rename(target)
                applied_renames.append((source, target))

            for parent_after, prefix, old_child, new_child in plan["child_renames"]:
                source = parent_after / f"{prefix}. {old_child}"
                target = parent_after / f"{prefix}. {new_child}"
                if not self._directory_exists(source, "subcarpeta original"):
                    raise YearStructureEditorError(
                        f"La subcarpeta original cambió durante la operación: {source}"
                    )
                if target.exists():
                    raise YearStructureEditorError(
                        f"La subcarpeta destino apareció durante la operación: {target}"
                    )
                source.rename(target)
                applied_renames.append((source, target))

            for directory in plan["directories_to_create"]:
                if self._directory_exists(directory, "nueva carpeta"):
                    continue
                if not directory.parent.is_dir():
                    raise YearStructureEditorError(
                        f"No existe la carpeta principal para crear: {directory}"
                    )
                directory.mkdir()
                created_directories.append(directory)

            self._write_template_atomically(plan["template"])
        except Exception as error:
            for directory in sorted(
                created_directories,
                key=lambda path: len(path.parts),
                reverse=True,
            ):
                try:
                    directory.rmdir()
                except OSError:
                    pass

            for source, target in reversed(applied_renames):
                try:
                    if target.exists() and not source.exists():
                        target.rename(source)
                except OSError:
                    pass

            if isinstance(error, YearStructureEditorError):
                raise
            raise YearStructureEditorError(
                f"No se pudo completar la sincronización de la estructura: {error}"
            ) from error

        return {
            "changed": True,
            "year_count": plan["year_count"],
            "renamed_count": plan["renamed_count"],
            "created_count": plan["created_count"],
            "template": plan["template"],
        }
