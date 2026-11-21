"""Git-based synchronization for the private AnuarySignature Structure repository."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engines.structure_paths import (
    STRUCTURE_REPOSITORY_URL,
    get_structure_dir,
    get_structure_repo_root,
)
from engines.structure_backups import StructureBackupManager
from engines.structure_credentials import StructureGitHubCredentialStore


def _background_process_options(platform_name: str | None = None) -> dict[str, Any]:
    """Prevent Git and its child processes from flashing a console on Windows."""
    if (platform_name or os.name) != "nt":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = 0
    return {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }


class StructureSyncError(RuntimeError):
    """Raised when a safe Structure synchronization operation cannot proceed."""


class StructureSyncService:
    """Synchronize the local Structure checkout without discarding local edits."""

    REMOTE_NAME = "origin"

    def __init__(
        self,
        repo_root: str | Path | None = None,
        backup_manager: StructureBackupManager | None = None,
        git_executable: str = "git",
        credentials_store: StructureGitHubCredentialStore | None = None,
    ) -> None:
        self.repo_root = Path(repo_root) if repo_root else get_structure_repo_root()
        self.backups = backup_manager or StructureBackupManager(self.repo_root)
        self.git_executable = git_executable
        self.credentials = credentials_store or StructureGitHubCredentialStore()

    def _run_git(
        self,
        *arguments: str,
        timeout: int = 90,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment = self.credentials.apply_git_authentication(environment)

        process_options = _background_process_options()

        try:
            result = subprocess.run(
                [self.git_executable, "-C", str(self.repo_root), *arguments],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=environment,
                check=False,
                **process_options,
            )
        except FileNotFoundError as error:
            raise StructureSyncError(
                "Git no está instalado o no está disponible en PATH."
            ) from error
        except subprocess.TimeoutExpired as error:
            raise StructureSyncError(
                f"La operación de Git excedió el límite de {timeout} segundos."
            ) from error
        except OSError as error:
            raise StructureSyncError(f"No se pudo ejecutar Git: {error}") from error

        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            lowered = detail.casefold()
            if (
                "authentication failed" in lowered
                or "could not read username" in lowered
                or "invalid username or token" in lowered
                or "terminal prompts disabled" in lowered
            ):
                if self.credentials.get_credentials():
                    guidance = (
                        "GitHub rechazó el token guardado. Vuelve a configurarlo y "
                        "comprueba que siga vigente y tenga Contents: Read and write."
                    )
                else:
                    guidance = (
                        "GitHub rechazó la autenticación. Configura un token desde "
                        "Administrar token o inicia sesión mediante Git Credential Manager."
                    )
                detail = guidance + (f"\n{detail}" if detail else "")
            elif (
                "repository not found" in lowered
                or "access denied" in lowered
            ):
                detail = (
                    "No se pudo acceder al repositorio privado. Comprueba que la cuenta "
                    "tenga permiso sobre AnuarySignature-Structure."
                    + (f"\n{detail}" if detail else "")
                )
            elif (
                "write access to repository not granted" in lowered
                or ("permission to " in lowered and " denied" in lowered)
            ):
                detail = (
                    "El token no tiene permiso para subir cambios. En GitHub revisa "
                    "Repository permissions → Contents → Read and write."
                    + (f"\n{detail}" if detail else "")
                )
            raise StructureSyncError(detail or "Git devolvió un error.")
        return result

    def _ensure_repository(self) -> None:
        if not self.repo_root.is_dir():
            raise StructureSyncError(
                f"No existe el checkout local de Structure:\n{self.repo_root}"
            )
        result = self._run_git("rev-parse", "--show-toplevel")
        actual_root = Path(result.stdout.strip()).resolve()
        if actual_root != self.repo_root.resolve():
            raise StructureSyncError(
                "La carpeta configurada no es la raíz del repositorio Structure."
            )

    def _ensure_expected_remote(self) -> str:
        remote = self._run_git("remote", "get-url", self.REMOTE_NAME).stdout.strip()
        normalized = remote.removesuffix(".git").casefold()
        expected = STRUCTURE_REPOSITORY_URL.removesuffix(".git").casefold()
        accepted = {
            expected,
            "git@github.com:mhz698a/anuarysignature-structure",
            "ssh://git@github.com/mhz698a/anuarysignature-structure",
        }
        if normalized not in accepted:
            raise StructureSyncError(
                "El remoto origin no corresponde al repositorio privado esperado.\n"
                f"Remoto detectado: {remote}\n"
                f"Remoto esperado: {STRUCTURE_REPOSITORY_URL}"
            )
        return remote

    def _current_branch(self) -> str:
        """Return the checked-out branch and reject detached or invalid refs."""
        branch = self._run_git("branch", "--show-current").stdout.strip()
        if not branch:
            raise StructureSyncError(
                "El checkout está en detached HEAD. Cambia a una rama antes de sincronizar."
            )
        checked = self._run_git("check-ref-format", "--branch", branch, check=False)
        if checked.returncode != 0:
            raise StructureSyncError("Git devolvió un nombre de rama local no válido.")
        return branch

    def list_remote_branches(self) -> dict[str, Any]:
        """List branches available on origin; PR source branches in this repo are included."""
        self._ensure_repository()
        self._ensure_expected_remote()
        self._fetch()
        output = self._run_git(
            "for-each-ref",
            "--format=%(refname:strip=3)",
            f"refs/remotes/{self.REMOTE_NAME}",
        ).stdout
        branches = sorted({
            line.strip() for line in output.splitlines()
            if line.strip() and line.strip() != "HEAD"
        }, key=str.casefold)
        return {"branches": branches, "current_branch": self._current_branch()}

    def switch_branch(self, branch: str) -> dict[str, Any]:
        """Switch to an origin branch without stashing or discarding local edits."""
        self._ensure_repository()
        self._ensure_expected_remote()
        self._ensure_no_pending_character_cache_snapshot()
        branch = str(branch or "").strip()
        if not branch:
            raise StructureSyncError("Selecciona una rama remota.")
        checked = self._run_git("check-ref-format", "--branch", branch, check=False)
        if checked.returncode != 0:
            raise StructureSyncError("El nombre de la rama seleccionada no es válido.")

        self._fetch()
        remote_ref = f"refs/remotes/{self.REMOTE_NAME}/{branch}"
        if self._run_git("rev-parse", "--verify", remote_ref, check=False).returncode != 0:
            raise StructureSyncError(
                f"La rama '{branch}' no existe en el remoto {self.REMOTE_NAME}."
            )

        changes = self._working_tree_changes()
        if changes:
            raise StructureSyncError(
                "No se puede cambiar de rama porque el checkout tiene cambios locales. "
                "Primero súbelos o respáldalos y resuélvelos; no se guardarán en stash."
            )

        branch_changed = self._current_branch() != branch
        if branch_changed:
            local_ref = self._run_git(
                "show-ref", "--verify", "--quiet", f"refs/heads/{branch}",
                check=False,
            )
            if local_ref.returncode == 0:
                self._run_git("switch", branch)
            else:
                self._run_git(
                    "switch", "--track", "--create", branch,
                    f"{self.REMOTE_NAME}/{branch}",
                )

        self._fetch()
        status = self._inspect_after_fetch()
        if branch_changed:
            status["character_cache_snapshot"] = self._capture_character_cache_snapshot()
        return status

    def _fetch(self, timeout: int = 120) -> None:
        self._run_git("fetch", "--prune", self.REMOTE_NAME, timeout=timeout)

    @staticmethod
    def _pending_character_cache_snapshot_path() -> Path:
        return (
            get_structure_repo_root().parent
            / "CharacterCacheSync"
            / "pending_characters_cache.json"
        )

    def _ensure_no_pending_character_cache_snapshot(self) -> None:
        pending_path = self._pending_character_cache_snapshot_path()
        if pending_path.is_file():
            raise StructureSyncError(
                "Hay una copia pendiente de aplicar de characters_cache.json en "
                "AppData. Antes de cambiar de rama, descargar otra versión o restaurar "
                "un respaldo, aplica sus cambios desde Herramientas → Aplicar cambios "
                "de caché a credenciales locales, o descarta explícitamente esa copia. "
                f"Archivo protegido: {pending_path}"
            )

    def _capture_character_cache_snapshot(self) -> dict[str, str] | None:
        """Preserve a checked-out cache before later scans or branch changes can rewrite it."""
        cache_path = get_structure_dir() / "characters_cache.json"
        if not cache_path.is_file():
            return None
        pending_path = self._pending_character_cache_snapshot_path()
        content = cache_path.read_bytes()
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        if pending_path.exists():
            existing = pending_path.read_bytes()
            if existing == content:
                return {"snapshot_path": str(pending_path), "status": "already_preserved"}
            raise StructureSyncError(
                "Ya existe otra versión pendiente de characters_cache.json. "
                "Se conservó intacta y no se sobrescribió."
            )
        temporary_path: Path | None = None
        try:
            import tempfile

            with tempfile.NamedTemporaryFile(
                mode="wb",
                prefix=".characters_cache.",
                suffix=".tmp",
                dir=pending_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
            os.replace(temporary_path, pending_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink(missing_ok=True)
        return {"snapshot_path": str(pending_path), "status": "captured"}

    def _working_tree_changes(self) -> list[str]:
        output = self._run_git(
            "status", "--porcelain=v1", "--untracked-files=all"
        ).stdout
        return [line for line in output.splitlines() if line.strip()]

    def _conflicts(self, changes: list[str]) -> list[str]:
        conflicts = []
        for line in changes:
            status = line[:2]
            if "U" in status or status in {"AA", "DD"}:
                conflicts.append(line)
        return conflicts

    def _revision_counts(self, branch: str | None = None) -> tuple[int, int]:
        target_branch = branch or self._current_branch()
        result = self._run_git(
            "rev-list",
            "--left-right",
            "--count",
            f"HEAD...{self.REMOTE_NAME}/{target_branch}",
        )
        values = result.stdout.strip().split()
        if len(values) != 2:
            raise StructureSyncError(
                "Git no pudo calcular la diferencia entre la copia local y GitHub."
            )
        return int(values[0]), int(values[1])

    def _inspect_after_fetch(self) -> dict[str, Any]:
        branch = self._current_branch()
        remote_ref = f"refs/remotes/{self.REMOTE_NAME}/{branch}"
        if self._run_git("rev-parse", "--verify", remote_ref, check=False).returncode != 0:
            raise StructureSyncError(
                f"La rama local '{branch}' no tiene una rama equivalente en "
                f"{self.REMOTE_NAME}. Selecciona una rama remota desde el diálogo."
            )
        changes = self._working_tree_changes()
        conflicts = self._conflicts(changes)
        ahead, behind = self._revision_counts(branch)
        head = self._run_git("rev-parse", "HEAD").stdout.strip()
        remote_head = self._run_git("rev-parse", remote_ref).stdout.strip()
        return {
            "branch": branch,
            "head": head,
            "remote_head": remote_head,
            "ahead": ahead,
            "behind": behind,
            "local_changes": changes,
            "local_change_count": len(changes),
            "conflicts": conflicts,
            "is_clean": not changes,
            "is_synchronized": not changes and ahead == 0 and behind == 0,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    def check_for_updates(self, fetch_timeout: int = 120) -> dict[str, Any]:
        """Fetch remote metadata and report local edits and ahead/behind counts."""
        self._ensure_repository()
        self._ensure_expected_remote()
        self._fetch(timeout=max(5, int(fetch_timeout)))
        return self._inspect_after_fetch()

    def upload_changes(self) -> dict[str, Any]:
        """Commit local changes and push them only when the remote has not advanced."""
        self._ensure_repository()
        self._ensure_expected_remote()
        self._current_branch()
        self._fetch()
        status = self._inspect_after_fetch()

        if status["conflicts"]:
            raise StructureSyncError(
                "El repositorio contiene conflictos sin resolver. No se subió ningún cambio."
            )
        if status["behind"] > 0:
            raise StructureSyncError(
                f"GitHub tiene {status['behind']} commit(s) que esta copia no tiene. "
                "Descarga primero los cambios remotos; los cambios locales se conservarán."
            )

        if status["local_changes"]:
            self._run_git("add", "--all", "--", ".")
            staged = self._run_git("diff", "--cached", "--quiet", check=False)
            if staged.returncode != 0:
                timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
                self._run_git(
                    "commit",
                    "-m",
                    f"Update Structure data - {timestamp}",
                    timeout=120,
                )

        ahead, behind = self._revision_counts()
        if behind > 0:
            raise StructureSyncError(
                "GitHub recibió cambios durante la operación. El commit local se conservó; "
                "vuelve a comprobar la sincronización antes de subir."
            )
        if ahead == 0:
            return {
                "updated": False,
                "message": "No hay cambios locales pendientes de subir.",
                "status": self._inspect_after_fetch(),
            }

        self._run_git(
            "push", self.REMOTE_NAME,
            f"HEAD:refs/heads/{status['branch']}", timeout=180,
        )
        self._fetch()
        return {
            "updated": True,
            "message": "Los cambios locales se subieron correctamente a GitHub.",
            "status": self._inspect_after_fetch(),
        }

    def download_updates(self) -> dict[str, Any]:
        """Fast-forward from GitHub after a verified local backup."""
        self._ensure_repository()
        self._ensure_expected_remote()
        self._current_branch()
        self._ensure_no_pending_character_cache_snapshot()
        self._fetch()
        status = self._inspect_after_fetch()

        if status["conflicts"]:
            raise StructureSyncError(
                "El repositorio contiene conflictos sin resolver. No se descargaron cambios."
            )
        if status["local_changes"]:
            raise StructureSyncError(
                "Hay cambios locales sin commit. Súbelos o crea un respaldo y resuélvelos "
                "antes de descargar; no se sobrescribió ningún archivo."
            )
        if status["ahead"] > 0:
            raise StructureSyncError(
                "Hay commits locales que todavía no están en GitHub. Súbelos primero."
            )
        if status["behind"] == 0:
            return {
                "updated": False,
                "message": "La copia local ya está actualizada.",
                "backup_path": None,
                "status": status,
            }

        backup_path = self.backups.create_backup(
            operation="before_download",
            source_commit=status["head"],
        )
        self._run_git(
            "merge",
            "--ff-only",
            f"{self.REMOTE_NAME}/{status['branch']}",
            timeout=120,
        )
        updated_status = self._inspect_after_fetch()
        updated_status["character_cache_snapshot"] = (
            self._capture_character_cache_snapshot()
        )
        return {
            "updated": True,
            "message": "Los cambios remotos se descargaron correctamente.",
            "backup_path": str(backup_path),
            "status": updated_status,
        }

    def create_manual_backup(self) -> dict[str, Any]:
        """Create a local point-in-time backup of the working tree."""
        self._ensure_repository()
        head = self._run_git("rev-parse", "HEAD").stdout.strip()
        path = self.backups.create_backup(
            operation="manual",
            source_commit=head,
        )
        return {"backup_path": str(path), "message": "Respaldo local creado."}

    def list_backups(self) -> list[dict[str, Any]]:
        return self.backups.list_backups()

    def restore_backup(self, backup_path: str | Path) -> dict[str, Any]:
        """Restore a selected snapshot, first preserving the current working tree."""
        self._ensure_repository()
        self._ensure_expected_remote()
        self._current_branch()
        self._ensure_no_pending_character_cache_snapshot()
        current_head = self._run_git("rev-parse", "HEAD").stdout.strip()
        restore_result = self.backups.restore_backup(
            backup_path,
            create_pre_restore_backup=True,
            source_commit=current_head,
        )
        cache_snapshot = self._capture_character_cache_snapshot()
        status = self._working_tree_changes()
        return {
            "restored": True,
            "message": (
                "Respaldo restaurado localmente. Los archivos restaurados quedan como "
                "cambios locales y deberán subirse mediante la acción Subir cambios."
            ),
            "pre_restore_backup": str(restore_result["pre_restore_backup"]),
            "restored_backup": str(restore_result["restored_backup"]),
            "local_change_count": len(status),
            "character_cache_snapshot": cache_snapshot,
        }
