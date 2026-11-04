"""Shared runtime paths and QSettings access for Domain Viewer."""

from pathlib import Path

from PyQt6.QtCore import QSettings


SETTINGS_ORGANIZATION = "etudetools"
SETTINGS_APPLICATION = "year_struct_vasculum"
DEPENDENT_PATH_KEY = "dependent_container_path"
DEFAULT_DEPENDENT_PATH = "E:/_Internal"


def application_settings():
    return QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)


def get_dependent_path(settings=None):
    """Return the configured dependent-folder path, using the Windows default."""
    settings = settings or application_settings()
    configured = settings.value(DEPENDENT_PATH_KEY, DEFAULT_DEPENDENT_PATH)
    configured = str(configured or DEFAULT_DEPENDENT_PATH).strip()
    return Path(configured).expanduser()
