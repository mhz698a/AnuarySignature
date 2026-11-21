"""Background bulk backup dialog for character credentials and selected images."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.character_credential_backup import CharacterCredentialBackupService


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


class CharacterCredentialBackupDialog(QDialog):
    """Back up all cached character credentials and their selected images."""

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
        self.result = None
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
            "Los archivos se copiarán al checkout local de Structure. Después "
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
        self.result = result
        self.completed_successfully = True
        self.status_label.setText(
            "Proceso de respaldo terminado.\n\n"
            f"Personajes en caché: {result.get('total', 0)}\n"
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
