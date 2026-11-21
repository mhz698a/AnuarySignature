"""Background UI for manually generating the dependent-drive directory report."""

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
from engines.dependent_directory_report import (
    DependentDirectoryReportService,
    REPORT_FILENAME,
)
from engines.structure_paths import get_structure_file


class _DependentDirectoryReportWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, base_path: Path, parent=None):
        super().__init__(parent)
        self.base_path = Path(base_path)

    def run(self):
        try:
            result = DependentDirectoryReportService(
                self.base_path,
                get_structure_file(REPORT_FILENAME),
            ).generate_or_update()
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class DependentDirectoryReportDialog(QDialog):
    """Generate the report without blocking the AnuarySignature main window."""

    def __init__(self, base_path: str | Path, parent=None):
        super().__init__(parent)
        self.base_path = Path(base_path)
        self.worker = None
        self.report_result = None
        self.report_generated = False

        self.setWindowTitle("Reporte de unidad dependiente")
        self.setModal(True)
        self.setMinimumWidth(590)
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

        self._build_ui()
        self._start_worker()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Inventario de directorios de la unidad dependiente")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        scope = QLabel(
            f"Unidad dependiente:\n{self.base_path}\n\n"
            "Solo se leerán directorios de años de cuatro dígitos y hasta dos "
            "niveles de subcarpetas después de cada año. No se abrirán, leerán "
            "ni registrarán archivos."
        )
        scope.setWordWrap(True)
        layout.addWidget(scope)

        self.status_label = QLabel("Generando el reporte…")
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

    def _start_worker(self):
        worker = _DependentDirectoryReportWorker(self.base_path, self)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self.worker = worker
        worker.start()

    def _on_completed(self, result: dict):
        self.report_result = result
        self.report_generated = True
        self.status_label.setText(
            "Reporte generado/actualizado correctamente.\n\n"
            f"Años incluidos: {result.get('year_count', 0)}\n"
            f"Directorios registrados: {result.get('directory_count', 0)}\n"
            "Profundidad máxima después del año: "
            f"{result.get('max_subfolder_levels_after_year', 2)} niveles\n\n"
            f"Archivo: {result.get('report_path', '')}"
        )
        self.close_button.setEnabled(True)

    def _on_failed(self, message: str):
        self.status_label.setText(
            "No se pudo generar el reporte. El reporte anterior, si existía, "
            f"se conserva.\n\n{message}"
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
