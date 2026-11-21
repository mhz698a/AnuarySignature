"""Configurable background UI for the dependent-drive directory report."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.dependent_directory_report import (
    DEFAULT_EXCLUDED_DIRECTORY_NAMES,
    DependentDirectoryReportService,
    REPORT_FILENAME,
    REPORT_SETTINGS_FILENAME,
)
from engines.structure_paths import get_structure_file


class _DependentDirectoryReportWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, str)
    preferences_saved = pyqtSignal(object)

    def __init__(
        self,
        base_path: Path,
        excluded_directories: list[str],
        included_directories: list[str],
        parent=None,
    ):
        super().__init__(parent)
        self.base_path = Path(base_path)
        self.excluded_directories = list(excluded_directories)
        self.included_directories = list(included_directories)

    def _report_progress(self, completed: int, total: int, message: str):
        self.progress.emit(completed, total, message)

    def run(self):
        try:
            service = DependentDirectoryReportService(
                self.base_path,
                get_structure_file(REPORT_FILENAME),
                get_structure_file(REPORT_SETTINGS_FILENAME),
            )
            preferences = service.save_exclusion_preferences(
                self.excluded_directories,
                self.included_directories,
            )
            self.preferences_saved.emit(preferences)
            result = service.generate_or_update(
                progress_callback=self._report_progress,
            )
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class DependentDirectoryReportDialog(QDialog):
    """Choose year-level folders and generate the report on explicit request."""

    def __init__(self, base_path: str | Path, parent=None):
        super().__init__(parent)
        self.base_path = Path(base_path)
        self.worker = None
        self.report_result = None
        self.report_generated = False
        self.preferences_saved = False
        self._preferences = {}
        self._directory_options = []
        self._load_error = None

        self.service = DependentDirectoryReportService(
            self.base_path,
            get_structure_file(REPORT_FILENAME),
            get_structure_file(REPORT_SETTINGS_FILENAME),
        )
        try:
            self._preferences = self.service.load_exclusion_preferences()
            self._directory_options = self.service.list_year_directory_options(
                self._preferences
            )
        except Exception as error:
            self._load_error = str(error)

        self.setWindowTitle("Reporte de unidad dependiente")
        self.setModal(True)
        self.setMinimumSize(760, 680)
        self.resize(820, 760)
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
            QTreeWidget {{
                background-color: #252525;
                border: 1px solid #444444;
                color: {Theme.TEXT_WHITE};
                selection-background-color: #3e3e42;
            }}
            QHeaderView::section {{
                background-color: #303030;
                color: {Theme.TEXT_WHITE};
                border: 1px solid #444444;
                padding: 5px;
            }}
            QProgressBar {{
                background-color: #252525;
                border: 1px solid #444444;
                border-radius: 4px;
                text-align: center;
                color: {Theme.TEXT_WHITE};
                height: 18px;
            }}
            QProgressBar::chunk {{
                background-color: {Theme.ROLE_EXODOMAIN_BG};
                width: 8px;
            }}
        """)

        self._build_ui()
        self._populate_directory_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Inventario de directorios de la unidad dependiente")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        scope = QLabel(
            f"Unidad dependiente:\n{self.base_path}\n\n"
            "Cada año muestra sus carpetas directas. Marca la columna "
            "'Excluir del reporte' para omitir una carpeta y todo su contenido. "
            "resources.local.personal está excluida inicialmente en todos los años. "
            "Las credenciales localizadas dentro de carpetas excluidas tampoco "
            "aparecerán en el reporte. El contenido de los JSON no se lee ni se copia."
        )
        scope.setWordWrap(True)
        layout.addWidget(scope)

        self.directory_tree = QTreeWidget(self)
        self.directory_tree.setColumnCount(2)
        self.directory_tree.setHeaderLabels(
            ["Año / carpeta", "Excluir del reporte"]
        )
        self.directory_tree.setColumnWidth(0, 500)
        self.directory_tree.setColumnWidth(1, 170)
        self.directory_tree.setUniformRowHeights(True)
        self.directory_tree.setAlternatingRowColors(True)
        layout.addWidget(self.directory_tree, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.status_label.setMinimumHeight(54)
        self.status_label.setStyleSheet(
            "background-color: #252525; border: 1px solid #444444; "
            "border-radius: 4px; padding: 10px;"
        )
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        footer = QHBoxLayout()
        footer.addStretch()

        self.generate_button = QPushButton("Generar reporte")
        self.generate_button.clicked.connect(self._start_worker)
        footer.addWidget(self.generate_button)

        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

    def _populate_directory_tree(self):
        self.directory_tree.clear()

        if self._load_error is not None:
            self.status_label.setText(
                "No se pudo leer la estructura de años y carpetas. "
                "No se iniciará la generación del reporte.\n\n"
                + self._load_error
            )
            self.generate_button.setEnabled(False)
            return

        folder_count = 0
        for year_data in self._directory_options:
            folders = year_data.get("folders", [])
            year_item = QTreeWidgetItem(
                [str(year_data.get("year", "")), f"{len(folders)} carpetas"]
            )
            year_item.setFlags(
                year_item.flags() & ~Qt.ItemFlag.ItemIsSelectable
            )
            self.directory_tree.addTopLevelItem(year_item)
            year_item.setExpanded(True)

            for folder_data in folders:
                folder_name = str(folder_data.get("name", ""))
                relative_path = str(folder_data.get("relative_path", ""))
                folder_item = QTreeWidgetItem(
                    [folder_name, "Excluir"]
                )
                folder_item.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    relative_path,
                )
                folder_item.setFlags(
                    folder_item.flags()
                    | Qt.ItemFlag.ItemIsUserCheckable
                    | Qt.ItemFlag.ItemIsEnabled
                )
                folder_item.setCheckState(
                    1,
                    (
                        Qt.CheckState.Checked
                        if folder_data.get("excluded")
                        else Qt.CheckState.Unchecked
                    ),
                )
                folder_item.setToolTip(0, relative_path)
                year_item.addChild(folder_item)
                folder_count += 1

        self.status_label.setText(
            f"Años detectados: {len(self._directory_options)}. "
            f"Carpetas configurables: {folder_count}.\n"
            "Selecciona las carpetas que deben excluirse. El reporte no se "
            "genera al abrir esta ventana; se generará al pulsar 'Generar reporte'."
        )
        self.generate_button.setEnabled(True)

    def _collect_exclusion_preferences(self) -> tuple[list[str], list[str]]:
        excluded = set(self._preferences.get("excluded_directories", []))
        included = set(self._preferences.get("included_directories", []))
        default_names = {
            name.casefold() for name in DEFAULT_EXCLUDED_DIRECTORY_NAMES
        }

        for year_index in range(self.directory_tree.topLevelItemCount()):
            year_item = self.directory_tree.topLevelItem(year_index)
            for folder_index in range(year_item.childCount()):
                folder_item = year_item.child(folder_index)
                relative_path = str(
                    folder_item.data(0, Qt.ItemDataRole.UserRole) or ""
                )
                if not relative_path:
                    continue

                key = relative_path.replace("\\", "/").casefold()
                folder_name = folder_item.text(0).casefold()
                excluded.discard(key)
                included.discard(key)

                if folder_item.checkState(1) == Qt.CheckState.Checked:
                    excluded.add(key)
                elif folder_name in default_names:
                    # Explicitly allow this one year-level folder despite the default.
                    included.add(key)

        # Keep preferences for directories that are temporarily absent from the drive.
        return sorted(excluded), sorted(included)

    def _start_worker(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self._load_error is not None:
            return

        excluded, included = self._collect_exclusion_preferences()
        self.generate_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.directory_tree.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.status_label.setText(
            "Guardando exclusiones e iniciando el recorrido de la unidad dependiente…"
        )

        worker = _DependentDirectoryReportWorker(
            self.base_path,
            excluded,
            included,
            self,
        )
        worker.progress.connect(self._on_progress)
        worker.preferences_saved.connect(self._on_preferences_saved)
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self.worker = worker
        worker.start()

    def _on_preferences_saved(self, preferences: dict):
        self._preferences = preferences
        self.preferences_saved = True

    def _on_progress(self, completed: int, total: int, message: str):
        if total <= 0:
            self.progress_bar.setRange(0, 0)
            self.status_label.setText(message)
            return

        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(completed)
        self.status_label.setText(
            f"{message}\nProgreso: {completed} de {total} carpetas y años."
        )

    def _on_completed(self, result: dict):
        self.report_result = result
        self.report_generated = True
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            "Reporte generado/actualizado correctamente.\n\n"
            f"Años incluidos: {result.get('year_count', 0)}\n"
            f"Directorios registrados: {result.get('directory_count', 0)}\n"
            f"Carpetas excluidas: {result.get('excluded_directory_count', 0)}\n"
            f"Carpetas de personajes: {result.get('character_count', 0)}\n"
            f"Credenciales encontradas: {result.get('credential_found_count', 0)}\n"
            f"Sin credencial: {result.get('credential_missing_count', 0)}\n"
            f"Ubicación ambigua: {result.get('credential_ambiguous_count', 0)}\n"
            f"Con archivos adicionales: "
            f"{result.get('credential_additional_candidates_count', 0)}\n"
            f"Archivos de credencial detectados: {result.get('credential_file_count', 0)}\n"
            "Profundidad máxima después del año: "
            f"{result.get('max_subfolder_levels_after_year', 2)} niveles\n\n"
            f"Archivo: {result.get('report_path', '')}"
        )
        self.directory_tree.setEnabled(True)
        self.generate_button.setEnabled(True)
        self.close_button.setEnabled(True)

    def _on_failed(self, message: str):
        self.status_label.setText(
            "No se pudo generar el reporte. El reporte anterior, si existía, "
            "se conserva. Las preferencias de exclusión se guardaron si la "
            f"configuración pudo escribirse.\n\n{message}"
        )
        self.directory_tree.setEnabled(True)
        self.generate_button.setEnabled(True)
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
