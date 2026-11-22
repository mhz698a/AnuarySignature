"""Background status monitor for the private Structure Git repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from engines.structure_sync import StructureSyncService


class _StructureStatusWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, service: StructureSyncService, parent=None):
        super().__init__(parent)
        self.service = service

    def run(self):
        try:
            self.completed.emit(
                self.service.check_for_updates(
                    fetch_timeout=StructureStatusMonitor.FETCH_TIMEOUT_SECONDS
                )
            )
        except Exception as error:
            self.failed.emit(str(error))


class StructureStatusMonitor(QObject):
    """Poll remote Structure status without blocking the main application."""

    status_changed = pyqtSignal(str, str, str)
    idle = pyqtSignal()

    DEFAULT_INTERVAL_MS = 180_000
    FETCH_TIMEOUT_SECONDS = 15

    def __init__(
        self,
        service: StructureSyncService | None = None,
        interval_ms: int = DEFAULT_INTERVAL_MS,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.service = service or StructureSyncService()
        self.interval_ms = max(30_000, int(interval_ms))
        self._worker: _StructureStatusWorker | None = None
        self._paused = False
        self._refresh_pending = False
        self._last_successful_status: dict[str, Any] | None = None

        self.timer = QTimer(self)
        self.timer.setInterval(self.interval_ms)
        self.timer.timeout.connect(self.refresh_now)

    def start(self) -> None:
        self._paused = False
        self.timer.start()
        self.refresh_now()

    def pause(self) -> None:
        self._paused = True
        self.timer.stop()

    def resume(self, refresh_immediately: bool = True) -> None:
        self._paused = False
        self.timer.start()
        if refresh_immediately:
            self.refresh_now()

    def stop(self) -> None:
        self._paused = True
        self.timer.stop()
        if self._worker is not None and self._worker.isRunning():
            self._refresh_pending = False

    def is_busy(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def refresh_now(self) -> None:
        if self._paused:
            return
        if self.is_busy():
            self._refresh_pending = True
            return

        worker = _StructureStatusWorker(self.service, self)
        worker.completed.connect(self._on_status_received)
        worker.failed.connect(self._on_status_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self.status_changed.emit(
            "STRUCTURE · …",
            "Comprobando el estado local y remoto de Structure…",
            "#bdbdbd",
        )
        worker.start()

    def _on_status_received(self, status: dict[str, Any]) -> None:
        self._last_successful_status = status
        label, tooltip, color = self._format_status(status)
        self.status_changed.emit(label, tooltip, color)

    def _on_status_failed(self, message: str) -> None:
        if self._last_successful_status is None:
            self.status_changed.emit(
                "STRUCTURE · ERROR",
                f"No se pudo consultar GitHub.\n{message}",
                "#f48771",
            )
            return

        label, tooltip, _ = self._format_status(self._last_successful_status)
        self.status_changed.emit(
            label,
            f"{tooltip}\n\nÚltima comprobación fallida:\n{message}",
            "#e5a65e",
        )

    def _on_worker_finished(self) -> None:
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        self._worker = None
        self.idle.emit()

        if self._refresh_pending and not self._paused:
            self._refresh_pending = False
            QTimer.singleShot(0, self.refresh_now)

    @staticmethod
    def _format_status(status: dict[str, Any]) -> tuple[str, str, str]:
        ahead = int(status.get("ahead", 0))
        behind = int(status.get("behind", 0))
        local_changes = int(status.get("local_change_count", 0))
        conflicts = list(status.get("conflicts", []))
        branch = str(status.get("branch") or "desconocida")
        checked_at = str(status.get("checked_at") or "")

        if conflicts:
            label = f"CONFLICTS {len(conflicts)}"
            color = "#f48771"
        elif behind and (ahead or local_changes):
            label = (
                f"PULL {behind} · LOCAL {local_changes}"
                if local_changes and not ahead
                else f"PULL {behind} · PUSH {ahead}"
                + (f" · LOCAL {local_changes}" if local_changes else "")
            )
            color = "#e5a65e"
        elif behind:
            label = f"PULL {behind}"
            color = "#85c1e9"
        elif ahead and local_changes:
            label = f"PUSH {ahead} · LOCAL {local_changes}"
            color = "#e5a65e"
        elif ahead:
            label = f"PUSH {ahead}"
            color = "#e5a65e"
        elif local_changes:
            label = f"PUSH * ({local_changes})"
            color = "#e5a65e"
        else:
            label = "STRUCTURE · SYNC"
            color = "#8ccf9b"

        detail_lines = [
            f"Rama: {branch}",
            f"Commits locales pendientes de subir: {ahead}",
            f"Commits remotos pendientes de descargar: {behind}",
            f"Archivos locales modificados: {local_changes}",
            f"Conflictos: {len(conflicts)}",
        ]
        if conflicts:
            detail_lines.append("Rutas con conflicto:")
            detail_lines.extend(conflicts[:20])
        if checked_at:
            try:
                checked = datetime.fromisoformat(checked_at).astimezone()
                detail_lines.append(
                    "Última comprobación: "
                    + checked.strftime("%d/%m/%Y %H:%M:%S")
                )
            except ValueError:
                detail_lines.append(f"Última comprobación: {checked_at}")

        if behind and (ahead or local_changes):
            detail_lines.append(
                "Atención: hay cambios en ambos lados. La descarga y la subida "
                "automáticas están bloqueadas hasta resolver el estado remoto/local."
            )
        elif conflicts:
            detail_lines.append(
                "Resuelve los conflictos antes de descargar o subir cambios."
            )
        elif behind:
            detail_lines.append(
                "Hay cambios remotos disponibles para descargar desde la ventana "
                "de sincronización."
            )
        elif ahead or local_changes:
            detail_lines.append(
                "Hay cambios locales pendientes de publicar en el repositorio privado."
            )
        else:
            detail_lines.append("La copia local y GitHub están sincronizados.")

        return label, "\n".join(detail_lines), color
