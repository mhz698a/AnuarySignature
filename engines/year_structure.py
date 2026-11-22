"""Shared source of truth for the structure used when creating year folders.

This module deliberately has no Qt dependency so the report service and the
year-creation UI can resolve the same folders.json/fallback template.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_NUMBER_PREFIX = re.compile(r"^\s*\d+\.\s*(?P<name>.+?)\s*$")
_SEASON_CATEGORY = re.compile(r"^___\[.*\]$", re.IGNORECASE)
MINIMAL_FALLBACK_CATEGORIES = ("___[]", "album", "identity")


def load_folders_json(path: str | Path | None) -> dict[str, Any] | None:
    """Mirror the year creator's folders.json selection rules."""
    if path is None:
        return None
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception:
        return None
    return payload if isinstance(payload, dict) and payload else None


def find_fallback_template_year(
    base_path: str | Path,
    current_year: int,
) -> int | None:
    """Use the same template priority as year creation."""
    root = Path(base_path)
    if (root / str(current_year)).exists():
        return current_year
    if (root / str(current_year - 1)).exists():
        return current_year - 1

    existing_years = []
    if root.exists():
        for item in root.iterdir():
            if item.is_dir() and item.name.isdigit():
                existing_years.append(int(item.name))
    return max(existing_years) if existing_years else None


def strip_numeric_directory_prefix(folder_name: str) -> str:
    """Remove the year-specific numeric prefix from a directory name."""
    normalized = str(folder_name or "").strip()
    match = _NUMBER_PREFIX.fullmatch(normalized)
    return match.group("name").strip() if match else normalized


def normalize_directory_category(folder_name: str) -> str:
    """Return a stable category key, including dynamic season directory names."""
    normalized = strip_numeric_directory_prefix(folder_name)
    if _SEASON_CATEGORY.fullmatch(normalized):
        return "___[]"
    return re.sub(r"\s+", " ", normalized).strip().casefold()


def clean_fallback_template_folder_name(
    folder_name: str,
    season_name: str,
) -> str:
    """Apply the same renaming transformation used by fallback year creation."""
    clean_name = strip_numeric_directory_prefix(folder_name)
    if "___" in clean_name:
        return f"___[{season_name}]"
    return clean_name


def resolve_year_structure(
    base_path: str | Path,
    folders_json_path: str | Path | None,
    current_year: int,
) -> dict[str, Any]:
    """Resolve expected top-level categories using the year creator's rules."""
    folders_data = load_folders_json(folders_json_path)
    if folders_data is not None:
        if not all(isinstance(name, str) and name.strip() for name in folders_data):
            raise ValueError("folders.json contiene nombres de carpeta no válidos.")
        return {
            "source": "folders.json",
            "template_year": None,
            "categories": list(folders_data),
        }

    template_year = find_fallback_template_year(base_path, current_year)
    if template_year is not None:
        template_dir = Path(base_path) / str(template_year)
        try:
            categories = [
                clean_fallback_template_folder_name(item.name, "[]")
                for item in template_dir.iterdir()
                if item.is_dir()
            ]
        except OSError as error:
            raise ValueError(
                f"No se pudo leer el año plantilla {template_year}: {error}"
            ) from error
        return {
            "source": "fallback_template",
            "template_year": str(template_year),
            "categories": categories,
        }

    return {
        "source": "minimal_fallback",
        "template_year": None,
        "categories": list(MINIMAL_FALLBACK_CATEGORIES),
    }
