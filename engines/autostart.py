"""Windows logon-start integration for Domain Viewer."""

import os
import subprocess
import sys
from pathlib import Path

if os.name == "nt":
    import winreg


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE_NAME = "DomainViewer"


def _startup_command(entry_script):
    if getattr(sys, "frozen", False):
        command_parts = [sys.executable]
    else:
        command_parts = [
            sys.executable,
            str(Path(entry_script or sys.argv[0]).expanduser().resolve()),
        ]
    return subprocess.list2cmdline(command_parts)


def is_startup_enabled():
    """Return whether the current user's Windows Run value is configured."""
    if os.name != "nt":
        return False


    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            RUN_KEY,
            0,
            winreg.KEY_QUERY_VALUE,
        ) as key:
            command, _ = winreg.QueryValueEx(key, RUN_VALUE_NAME)
            return bool(str(command).strip())
    except FileNotFoundError:
        return False


def set_startup_enabled(enabled, entry_script=None):
    """Create or remove the current user's Windows logon-start registry value."""
    if os.name != "nt":
        raise OSError("El inicio automático está disponible únicamente en Windows.")


    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(
                key,
                RUN_VALUE_NAME,
                0,
                winreg.REG_SZ,
                _startup_command(entry_script),
            )
        else:
            try:
                winreg.DeleteValue(key, RUN_VALUE_NAME)
            except FileNotFoundError:
                pass
