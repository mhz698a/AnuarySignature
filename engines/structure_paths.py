"""Resolve AnuarySignature data files from the private Structure checkout.

The private repository is cloned locally so the application can read and write
its JSON files without making startup depend on a network connection.
"""

import os
from pathlib import Path


STRUCTURE_REPOSITORY_URL = (
    "https://github.com/mhz698a/AnuarySignature-Structure.git"
)

REQUIRED_STRUCTURE_FILES = (
    "about_it.json",
    "characters_cache.json",
    "classifications_db.json",
    "contacts_db.json",
    "container.json",
    "dicc_table.json",
    "domains.json",
    "folders.json",
    "infrastructure.json",
    "type_under_list.json",
    "verbose_architecture.json",
    "verbose_business.json",
)


def get_structure_repo_root(local_app_data: str | Path | None = None) -> Path:
    """Return the local checkout directory under the current user's AppData."""
    if local_app_data is not None:
        app_data = Path(local_app_data).expanduser()
    else:
        configured = os.environ.get("LOCALAPPDATA")
        app_data = (
            Path(configured).expanduser()
            if configured
            else Path.home() / "AppData" / "Local"
        )

    return app_data / "AnuarySignature" / "Structure"


def get_structure_dir(local_app_data: str | Path | None = None) -> Path:
    """Return the __structure__ directory inside the local private checkout."""
    return get_structure_repo_root(local_app_data) / "__structure__"


def get_structure_file(
    filename: str,
    local_app_data: str | Path | None = None,
) -> Path:
    """Resolve a single JSON file within __structure__, rejecting path traversal."""
    relative = Path(filename)
    if (
        relative.is_absolute()
        or len(relative.parts) != 1
        or relative.name in {"", ".", ".."}
    ):
        raise ValueError("El nombre del archivo Structure debe ser un nombre simple.")

    return get_structure_dir(local_app_data) / relative.name


def get_missing_structure_files(
    local_app_data: str | Path | None = None,
) -> list[str]:
    """Return required JSON files that are not present in the local checkout."""
    structure_dir = get_structure_dir(local_app_data)
    return [
        filename
        for filename in REQUIRED_STRUCTURE_FILES
        if not (structure_dir / filename).is_file()
    ]


def get_structure_clone_command(
    local_app_data: str | Path | None = None,
) -> str:
    """Build the Windows command needed for the first local checkout."""
    destination = get_structure_repo_root(local_app_data)
    return f'git clone {STRUCTURE_REPOSITORY_URL} "{destination}"'
