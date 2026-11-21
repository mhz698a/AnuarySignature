"""Background bulk backup dialog for character credentials and selected images."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QObject, QThread, Qt, pyqtSignal, pyqtSlot
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.character_credential_backup import CharacterCredentialBackupService
from engines.dependent_directory_report import (
    DependentDirectoryReportService,
    REPORT_FILENAME,
)
from engines.structure_paths import get_structure_file


class _CharacterBackupWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        dependent_path: Path,
        characters_by_year: dict,
        parent=None,
    ):
        super().__init__(parent)
        self.dependent_path = Path(dependent_path)
        self.characters_by_year = {
            str(year): [dict(item) for item in items]
            for year, items in characters_by_year.items()
        }

    def run(self):
        try:
            service = CharacterCredentialBackupService(self.dependent_path)
            self.completed.emit(service.backup_all(self.characters_by_year))
        except Exception as error:
            self.failed.emit(str(error))


class SingleCharacterBackupWorker(QThread):
    """Back up one edited character without blocking the main GUI thread."""

    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        dependent_path: str | Path,
        character: dict,
        parent=None,
    ):
        super().__init__(parent)
        self.dependent_path = Path(dependent_path)
        self.character = dict(character)

    def run(self):
        backup_result = None
        backup_error = None
        try:
            service = CharacterCredentialBackupService(self.dependent_path)
            backup_result = service.backup_character(self.character)
        except Exception as error:
            backup_error = str(error)

        report_error = None
        try:
            DependentDirectoryReportService(
                self.dependent_path,
                get_structure_file(REPORT_FILENAME),
            ).generate_or_update()
        except Exception as error:
            report_error = str(error)

        if backup_error is not None:
            message = backup_error
            if report_error is None:
                message += "\nEl reporte de la unidad dependiente sí fue actualizado."
            else:
                message += (
                    "\nTampoco se pudo actualizar el reporte de la unidad dependiente: "
                    + report_error
                )
            self.failed.emit(message)
            return

        backup_result["dependent_report_updated"] = report_error is None
        backup_result["dependent_report_error"] = report_error
        self.completed.emit(backup_result)


class SingleCharacterBackupUiBridge(QObject):
    """Marshal one-character backup results back to the main Qt thread."""

    def __init__(self, main_window, worker, parent=None):
        super().__init__(parent or main_window)
        self.main_window = main_window
        self.worker = worker

    @pyqtSlot(object)
    def on_completed(self, result):
        show_status = getattr(self.main_window, "show_status_message", None)
        if not callable(show_status):
            return

        warnings = result.get("warnings", [])
        report_error = str(result.get("dependent_report_error") or "")
        if warnings or report_error:
            details = []
            if warnings:
                details.append("Advertencias de respaldo: " + "; ".join(warnings))
            if report_error:
                details.append(
                    "El reporte de la unidad dependiente no se actualizó: "
                    + report_error
                )
            elif result.get("dependent_report_updated"):
                details.append("El reporte de la unidad dependiente fue actualizado.")
            show_status(
                "Respaldo Structure parcial. "
                + " ".join(details)
                + " Revisa antes de subirlo.",
                12000,
            )
        else:
            show_status(
                "Credencial e imágenes seleccionadas respaldadas en Structure. "
                "El reporte de la unidad dependiente también fue actualizado. "
                "Pulsa Subir cambios para publicarlos.",
                9000,
            )

    @pyqtSlot(str)
    def on_failed(self, message):
        show_status = getattr(self.main_window, "show_status_message", None)
        if callable(show_status):
            show_status(
                "Credencial guardada localmente, pero falló el "
                f"respaldo en Structure: {message}",
                10000,
            )

    @pyqtSlot()
    def on_finished(self):
        workers = getattr(
            self.main_window,
            "_character_backup_workers",
            set(),
        )
        workers.discard(self.worker)

        bridges = getattr(
            self.main_window,
            "_character_backup_bridges",
            set(),
        )
        bridges.discard(self)

        if (
            not workers
            and not getattr(self.main_window, "_closing_application", False)
        ):
            monitor = getattr(
                self.main_window,
                "structure_status_monitor",
                None,
            )
            if monitor is not None:
                monitor.resume(refresh_immediately=True)

        self.worker.deleteLater()
        self.deleteLater()


class CharacterCredentialBackupDialog(QDialog):
    """Back up every discoverable on-disk character credential and its selected images."""

    def __init__(
        self,
        dependent_path: str | Path,
        character_cache: dict,
        parent=None,
    ):
        super().__init__(parent)
        self.dependent_path = Path(dependent_path)
        self.character_cache = character_cache
        self.worker = None
        self.backup_result = None
        self.completed_successfully = False

        self.setWindowTitle("Respaldar credenciales de personajes")
        self.setModal(True)
        self.setMinimumWidth(620)
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
            QLabel {{ color: {Theme.TEXT_WHITE}; }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 7px 12px;
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton:hover {{
                background-color: #3e3e42;
                border-color: #85c1e9;
            }}
            QPushButton:disabled {{
                color: #777777;
                border-color: #383838;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Respaldo de credenciales y recursos seleccionados")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            f"Unidad dependiente:\n{self.dependent_path}\n\n"
            "Se respaldarán los JSON individuales de cada personaje y las "
            "imágenes seleccionadas en Icon Path y Background Path. Cada "
            "personaje tendrá una sola copia vigente de cada recurso en el "
            "repositorio privado Structure. Si cambia una imagen, se reemplaza "
            "solo su copia dentro del respaldo; el original de la unidad "
            "dependiente no se modifica.\n\n"
            "Solo se copiarán la credencial y sus imágenes seleccionadas; no se copiarán las demás imágenes de la carpeta. Los archivos se copiarán al checkout local de Structure. Después "
            "de revisar el resultado, utiliza Subir cambios para publicarlos "
            "en GitHub."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self.status_label = QLabel("Preparando respaldo…")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background-color: #252525; border: 1px solid #444444; "
            "border-radius: 4px; padding: 10px;"
        )
        layout.addWidget(self.status_label)

        footer = QHBoxLayout()
        footer.addStretch()
        self.close_button = QPushButton("Cerrar")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

        self._start_backup()

    def _start_backup(self):
        self.worker = _CharacterBackupWorker(
            self.dependent_path,
            self.character_cache,
            self,
        )
        self.worker.completed.connect(self._on_completed)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _on_completed(self, result: dict):
        self.backup_result = result
        self.completed_successfully = True
        self.status_label.setText(
            "Proceso de respaldo terminado.\n\n"
            f"Personajes encontrados: {result.get('discovered', 0)}\n"
            f"Respaldados: {result.get('backed_up', 0)}\n"
            f"Con error: {result.get('failed', 0)}\n"
            "Advertencias de imágenes: "
            f"{result.get('asset_warning_count', 0)}\n\n"
            "Los archivos están en el checkout local de Structure. "
            "El indicador de la statusbar mostrará PUSH cuando haya cambios "
            "locales pendientes de publicar."
        )
        self.close_button.setEnabled(True)

    def _on_failed(self, message: str):
        self.status_label.setText(
            "No se pudo completar el respaldo.\n\n" + message
        )
        self.close_button.setEnabled(True)

    def _on_worker_finished(self):
        worker = self.sender()
        if worker is not None:
            worker.deleteLater()
        self.worker = None

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            return
        super().closeEvent(event)
