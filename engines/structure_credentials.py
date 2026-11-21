"""Secure GitHub token storage for the private Structure repository.

The token itself is stored in Windows Credential Manager. A small JSON sidecar
contains only the GitHub login and the expiration date entered by the user.
"""

from __future__ import annotations

import base64
import ctypes
import json
import os
import urllib.error
import urllib.request
from ctypes import wintypes
from datetime import date
from pathlib import Path
from typing import Any

from engines.structure_paths import get_structure_repo_root


CREDENTIAL_TARGET = "AnuarySignature/Structure/GitHub"
STRUCTURE_REPOSITORY_API = (
    "https://api.github.com/repos/mhz698a/AnuarySignature-Structure"
)
GITHUB_API_VERSION = "2026-03-10"
_CRED_TYPE_GENERIC = 1
_CRED_PERSIST_LOCAL_MACHINE = 2
_ERROR_NOT_FOUND = 1168


class StructureCredentialError(RuntimeError):
    """Raised when Structure GitHub credentials cannot be read or validated."""


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", _FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.c_void_p),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


class _WindowsCredentialBackend:
    """Small wrapper around the Windows Credential Manager generic API."""

    @staticmethod
    def _api():
        if os.name != "nt":
            raise StructureCredentialError(
                "El almacenamiento de tokens de Structure requiere Windows."
            )

        advapi32 = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
        advapi32.CredWriteW.argtypes = [
            ctypes.POINTER(_CREDENTIALW),
            wintypes.DWORD,
        ]
        advapi32.CredWriteW.restype = wintypes.BOOL
        advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
        ]
        advapi32.CredReadW.restype = wintypes.BOOL
        advapi32.CredDeleteW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        advapi32.CredDeleteW.restype = wintypes.BOOL
        advapi32.CredFree.argtypes = [ctypes.c_void_p]
        advapi32.CredFree.restype = None
        return advapi32

    @staticmethod
    def _raise_last_error(action: str) -> None:
        error_code = ctypes.get_last_error()
        raise StructureCredentialError(
            f"No se pudo {action} la credencial de Windows "
            f"(error {error_code})."
        )

    def write(self, username: str, token: str) -> None:
        api = self._api()
        token_bytes = token.encode("utf-16-le")
        token_buffer = ctypes.create_string_buffer(token_bytes)

        credential = _CREDENTIALW()
        credential.Flags = 0
        credential.Type = _CRED_TYPE_GENERIC
        credential.TargetName = CREDENTIAL_TARGET
        credential.Comment = "AnuarySignature private Structure repository"
        credential.CredentialBlobSize = len(token_bytes)
        credential.CredentialBlob = ctypes.cast(
            token_buffer, ctypes.c_void_p
        )
        credential.Persist = _CRED_PERSIST_LOCAL_MACHINE
        credential.AttributeCount = 0
        credential.Attributes = None
        credential.TargetAlias = None
        credential.UserName = username

        if not api.CredWriteW(ctypes.byref(credential), 0):
            self._raise_last_error("guardar")

    def read(self) -> tuple[str, str] | None:
        if os.name != "nt":
            return None

        api = self._api()
        credential_pointer = ctypes.POINTER(_CREDENTIALW)()
        if not api.CredReadW(
            CREDENTIAL_TARGET,
            _CRED_TYPE_GENERIC,
            0,
            ctypes.byref(credential_pointer),
        ):
            error_code = ctypes.get_last_error()
            if error_code == _ERROR_NOT_FOUND:
                return None
            raise StructureCredentialError(
                "No se pudo leer el token del Administrador de credenciales "
                f"de Windows (error {error_code})."
            )

        try:
            credential = credential_pointer.contents
            token = ctypes.string_at(
                credential.CredentialBlob,
                credential.CredentialBlobSize,
            ).decode("utf-16-le")
            return credential.UserName or "", token
        finally:
            api.CredFree(ctypes.cast(credential_pointer, ctypes.c_void_p))

    def delete(self) -> None:
        if os.name != "nt":
            return

        api = self._api()
        if not api.CredDeleteW(CREDENTIAL_TARGET, _CRED_TYPE_GENERIC, 0):
            error_code = ctypes.get_last_error()
            if error_code != _ERROR_NOT_FOUND:
                raise StructureCredentialError(
                    "No se pudo eliminar el token del Administrador de "
                    f"credenciales de Windows (error {error_code})."
                )


class StructureGitHubCredentialStore:
    """Store a PAT securely and expose it to Git without command-line arguments."""

    def __init__(
        self,
        metadata_path: str | Path | None = None,
        credential_backend: Any | None = None,
    ) -> None:
        self.metadata_path = (
            Path(metadata_path)
            if metadata_path is not None
            else get_structure_repo_root().parent
            / "structure_github_credentials.json"
        )
        self.backend = credential_backend or _WindowsCredentialBackend()

    @staticmethod
    def validate_token(token: str) -> str:
        """Validate the GitHub identity and access to the private repository."""
        clean_token = token.strip()
        if not clean_token:
            raise StructureCredentialError("El token está vacío.")

        def get_json(url: str) -> dict[str, Any]:
            request = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "Authorization": f"Bearer {clean_token}",
                    "User-Agent": "AnuarySignature-Structure-Sync",
                    "X-GitHub-Api-Version": GITHUB_API_VERSION,
                },
                method="GET",
            )
            try:
                with urllib.request.urlopen(request, timeout=15) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as error:
                if error.code == 401:
                    raise StructureCredentialError(
                        "GitHub rechazó el token. Comprueba que esté copiado "
                        "completo y que no haya expirado."
                    ) from error
                if error.code in {403, 404}:
                    raise StructureCredentialError(
                        "La cuenta o el token no tiene acceso al repositorio "
                        "privado AnuarySignature-Structure. Revisa el propietario, "
                        "la selección del repositorio y sus permisos."
                    ) from error
                raise StructureCredentialError(
                    f"GitHub respondió con HTTP {error.code} al validar el token."
                ) from error
            except urllib.error.URLError as error:
                raise StructureCredentialError(
                    f"No se pudo conectar con GitHub: {error.reason}"
                ) from error
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise StructureCredentialError(
                    "GitHub devolvió una respuesta no válida al validar el token."
                ) from error

        user = get_json("https://api.github.com/user")
        username = str(user.get("login", "")).strip()
        if not username:
            raise StructureCredentialError(
                "GitHub no devolvió el nombre de la cuenta autenticada."
            )

        get_json(STRUCTURE_REPOSITORY_API)
        return username

    def get_credentials(self) -> tuple[str, str] | None:
        return self.backend.read()

    def get_metadata(self) -> dict[str, Any]:
        if not self.metadata_path.is_file():
            return {}
        try:
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StructureCredentialError(
                "No se pudo leer la información de vencimiento del token."
            ) from error
        return payload if isinstance(payload, dict) else {}

    def save_token(
        self,
        token: str,
        username: str,
        expiration_date: str | None,
    ) -> None:
        clean_token = token.strip()
        clean_username = username.strip()
        if not clean_token or not clean_username:
            raise ValueError("El token y la cuenta de GitHub son obligatorios.")

        if expiration_date:
            parsed_expiration = date.fromisoformat(expiration_date)
            if parsed_expiration < date.today():
                raise ValueError("La fecha de expiración debe ser hoy o posterior.")

        previous_credentials = self.backend.read()
        self.backend.write(clean_username, clean_token)
        metadata = {
            "username": clean_username,
            "expires_on": expiration_date,
        }
        try:
            self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.metadata_path.with_name(
                self.metadata_path.name + ".tmp"
            )
            temporary_path.write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.metadata_path)
        except OSError as error:
            if previous_credentials:
                self.backend.write(*previous_credentials)
            else:
                self.backend.delete()
            raise StructureCredentialError(
                "No se pudo guardar la fecha de expiración. Se restauró la "
                "credencial anterior y no se aplicó el cambio."
            ) from error

    def delete_token(self) -> None:
        self.backend.delete()
        try:
            self.metadata_path.unlink(missing_ok=True)
        except OSError as error:
            raise StructureCredentialError(
                "Se eliminó el token, pero no se pudo borrar su información auxiliar."
            ) from error

    def apply_git_authentication(self, environment: dict[str, str]) -> dict[str, str]:
        """Pass the token to Git through process environment config, not argv."""
        credentials = self.get_credentials()
        if not credentials:
            return environment

        username, token = credentials
        basic_auth = base64.b64encode(
            f"{username}:{token}".encode("utf-8")
        ).decode("ascii")

        try:
            first_index = int(environment.get("GIT_CONFIG_COUNT", "0") or "0")
        except ValueError as error:
            raise StructureCredentialError(
                "La variable GIT_CONFIG_COUNT del entorno no es válida."
            ) from error

        environment["GIT_CONFIG_COUNT"] = str(first_index + 2)
        environment[f"GIT_CONFIG_KEY_{first_index}"] = (
            "http.https://github.com/.extraheader"
        )
        environment[f"GIT_CONFIG_VALUE_{first_index}"] = (
            f"AUTHORIZATION: basic {basic_auth}"
        )
        environment[f"GIT_CONFIG_KEY_{first_index + 1}"] = "credential.helper"
        environment[f"GIT_CONFIG_VALUE_{first_index + 1}"] = ""
        return environment
