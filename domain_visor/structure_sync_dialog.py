"""User interface for synchronizing and restoring private Structure data."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.structure_sync import StructureSyncService


class _StructureOperationWorker(QThread):
    completed = pyqtSignal(str, object)
    failed = pyqtSignal(str, str)

    def __init__(self, operation: str, callback, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.callback = callback

    def run(self):
        try:
            self.completed.emit(self.operation, self.callback())
        except Exception as error:
            self.failed.emit(self.operation, str(error))


class StructureSyncDialog(QDialog):
    """Manage checks, downloads, uploads and recoverable local Structure backups."""

    structure_updated = pyqtSignal()

    def __init__(self, parent=None, service=None):
        super().__init__(parent)
        self.service = service or StructureSyncService()
        self.worker = None
        self.current_status = None
        self.backups = []

        self.setWindowTitle("Sincronización de Structure")
        self.setModal(True)
        self.setMinimumSize(640, 430)
        self.resize(700, 470)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setStyleSheet(f"""
            QDialog, QWidget {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton, QComboBox {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 7px 10px;
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton:hover, QComboBox:hover {{
                background-color: #3e3e42;
                border-color: #85c1e9;
            }}
            QPushButton:disabled {{
                color: #777777;
                border-color: #383838;
            }}
            QComboBox QAbstractItemView {{
                background-color: #2d2d2d;
                color: {Theme.TEXT_WHITE};
                selection-background-color: #3e3e42;
            }}
        """)

        self._build_ui()
        self._refresh_backup_list()
        self._run_operation("check")

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Repositorio privado AnuarySignature-Structure")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        self.status_label = QLabel("Comprobando conexión y versiones…")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background-color: #252525; border: 1px solid #444444; "
            "border-radius: 4px; padding: 10px; font-weight: bold;"
        )
        layout.addWidget(self.status_label)

        self.details_label = QLabel(
            "La comprobación se ejecuta en segundo plano. "
            "Los archivos locales no se reemplazan automáticamente."
        )
        self.details_label.setWordWrap(True)
        self.details_label.setStyleSheet("color: #bdbdbd;")
        layout.addWidget(self.details_label)

        sync_title = QLabel("Sincronización")
        sync_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(sync_title)

        sync_row = QHBoxLayout()
        self.check_button = QPushButton("Comprobar cambios")
        self.check_button.clicked.connect(
            lambda: self._run_operation("check")
        )
        self.download_button = QPushButton("Descargar cambios")
        self.download_button.clicked.connect(self._confirm_download)
        self.upload_button = QPushButton("Subir cambios")
        self.upload_button.clicked.connect(self._confirm_upload)
        sync_row.addWidget(self.check_button)
        sync_row.addWidget(self.download_button)
        sync_row.addWidget(self.upload_button)
        layout.addLayout(sync_row)

        backup_title = QLabel("Respaldos locales")
        backup_title.setStyleSheet("font-weight: bold;")
        layout.addWidget(backup_title)

        self.backup_combo = QComboBox()
        self.backup_combo.setMinimumHeight(34)
        layout.addWidget(self.backup_combo)

        backup_row = QHBoxLayout()
        self.create_backup_button = QPushButton("Crear respaldo")
        self.create_backup_button.clicked.connect(
            lambda: self._run_operation("backup")
        )
        self.restore_backup_button = QPushButton("Restaurar seleccionado")
        self.restore_backup_button.clicked.connect(self._confirm_restore)
        backup_row.addWidget(self.create_backup_button)
        backup_row.addWidget(self.restore_backup_button)
        layout.addLayout(backup_row)

        self.operation_label = QLabel("")
        self.operation_label.setWordWrap(True)
        self.operation_label.setStyleSheet("color: #bdbdbd;")
        layout.addWidget(self.operation_label)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        self._set_busy(False)

    def _set_busy(self, busy: bool):
        if busy:
            self.check_button.setEnabled(False)
            self.download_button.setEnabled(False)
            self.upload_button.setEnabled(False)
            self.create_backup_button.setEnabled(False)
            self.restore_backup_button.setEnabled(False)
            self.backup_combo.setEnabled(False)
            self.close_button.setEnabled(False)
            return

        self.check_button.setEnabled(True)
        self.create_backup_button.setEnabled(True)
        self.backup_combo.setEnabled(True)
        self.close_button.setEnabled(True)
        self._apply_sync_button_states()

    def _apply_sync_button_states(self):
        status = self.current_status or {}
        ahead = int(status.get("ahead", 0))
        behind = int(status.get("behind", 0))
        local_changes = int(status.get("local_change_count", 0))
        conflicts = status.get("conflicts", [])

        self.download_button.setEnabled(
            behind > 0 and ahead == 0 and local_changes == 0 and not conflicts
        )
        self.upload_button.setEnabled(
            behind == 0 and (ahead > 0 or local_changes > 0) and not conflicts
        )
        self.restore_backup_button.setEnabled(self.backup_combo.count() > 0)

    def _run_operation(self, operation: str, argument=None):
        if self.worker is not None and self.worker.isRunning():
            return

        callbacks = {
            "check": self.service.check_for_updates,
            "upload": self.service.upload_changes,
            "download": self.service.download_updates,
            "backup": self.service.create_manual_backup,
        }
        if operation == "restore":
            callback = lambda: self.service.restore_backup(argument)
        else:
            callback = callbacks[operation]

        self.operation_label.setText("Ejecutando operación…")
        self._set_busy(True)
        worker = _StructureOperationWorker(operation, callback, self)
        worker.completed.connect(self._on_operation_completed)
        worker.failed.connect(self._on_operation_failed)
        worker.finished.connect(self._on_worker_finished)
        self.worker = worker
        worker.start()

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        self.worker = None
        self._set_busy(False)

    def _on_operation_completed(self, operation: str, result):
        if operation == "check":
            self.current_status = result
            self._display_status(result)
            self.operation_label.setText("Comprobación terminada.")
        elif operation in {"upload", "download"}:
            status = result.get("status")
            if status:
                self.current_status = status
                self._display_status(status)
            self.operation_label.setText(result.get("message", "Operación terminada."))
            if operation == "download" and result.get("updated"):
                backup_path = result.get("backup_path")
                if backup_path:
                    self.operation_label.setText(
                        f"{self.operation_label.text()} Respaldo previo: "
                        f"{Path(backup_path).name}."
                    )
                self.structure_updated.emit()
            self._refresh_backup_list()
        elif operation == "backup":
            backup_path = result.get("backup_path")
            self.operation_label.setText(
                f"Respaldo creado: {Path(backup_path).name}"
                if backup_path else result.get("message", "Respaldo creado.")
            )
            self._refresh_backup_list()
        elif operation == "restore":
            self.operation_label.setText(result.get("message", "Respaldo restaurado."))
            self.structure_updated.emit()
            self._refresh_backup_list()
            self.current_status = None
            self.status_label.setText(
                "Respaldo restaurado: los archivos recuperados están pendientes de subir."
            )
            self.details_label.setText(
                f"Cambios locales detectados: {result.get('local_change_count', 0)}. "
                "La restauración no modifica el historial remoto."
            )

    def _on_operation_failed(self, operation: str, message: str):
        self.operation_label.setText(f"No se pudo completar la operación: {message}")
        if operation == "check":
            self.status_label.setText("No se pudo comprobar el estado remoto.")
            self.details_label.setText(
                "Comprueba Git, la conexión a Internet y los permisos sobre el repositorio privado."
            )
        QMessageBox.warning(
            self,
            "Sincronización de Structure",
            message,
        )

    def _display_status(self, status: dict):
        ahead = int(status.get("ahead", 0))
        behind = int(status.get("behind", 0))
        local_changes = int(status.get("local_change_count", 0))
        conflicts = status.get("conflicts", [])

        if conflicts:
            headline = "Hay conflictos locales sin resolver."
        elif local_changes and behind:
            headline = "Hay cambios locales y remotos pendientes."
        elif local_changes:
            headline = "Hay cambios locales pendientes de subir."
        elif behind:
            headline = f"Hay {behind} commit(s) remoto(s) para descargar."
        elif ahead:
            headline = f"Hay {ahead} commit(s) local(es) pendientes de subir."
        else:
            headline = "Structure está sincronizado con GitHub."

        self.status_label.setText(headline)
        self.details_label.setText(
            f"Rama: {status.get('branch', 'desconocida')}    "
            f"Commits locales pendientes: {ahead}    "
            f"Commits remotos pendientes: {behind}\n"
            f"Archivos locales modificados: {local_changes}    "
            f"Conflictos: {len(conflicts)}"
        )

        self._apply_sync_button_states()

    def _refresh_backup_list(self):
        selected_path = self.backup_combo.currentData()
        try:
            self.backups = self.service.list_backups()
        except Exception:
            self.backups = []

        self.backup_combo.blockSignals(True)
        self.backup_combo.clear()
        for backup in self.backups:
            created = backup.get("created_at", "")
            operation = backup.get("operation", "manual")
            files = backup.get("file_count", 0)
            label = f"{created} · {operation} · {files} archivos"
            self.backup_combo.addItem(label, backup["path"])

        if selected_path:
            for index in range(self.backup_combo.count()):
                if self.backup_combo.itemData(index) == selected_path:
                    self.backup_combo.setCurrentIndex(index)
                    break
        self.backup_combo.blockSignals(False)
        if self.worker is None or not self.worker.isRunning():
            self.restore_backup_button.setEnabled(self.backup_combo.count() > 0)

    def _confirm_download(self):
        if QMessageBox.question(
            self,
            "Descargar cambios",
            "Se creará un respaldo local antes de descargar. "
            "Solo se permite una actualización fast-forward y no se sobrescribirán "
            "cambios locales pendientes. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._run_operation("download")

    def _confirm_upload(self):
        if QMessageBox.question(
            self,
            "Subir cambios",
            "Los cambios locales se agruparán en un commit y se enviarán a la rama main "
            "del repositorio privado. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._run_operation("upload")

    def _confirm_restore(self):
        backup_path = self.backup_combo.currentData()
        if not backup_path:
            return

        if QMessageBox.question(
            self,
            "Restaurar respaldo",
            "La restauración reemplazará los archivos actuales por la instantánea "
            "seleccionada. Antes se creará automáticamente otro respaldo del estado "
            "actual. Los archivos restaurados quedarán como cambios locales. ¿Continuar?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes:
            self._run_operation("restore", backup_path)

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
