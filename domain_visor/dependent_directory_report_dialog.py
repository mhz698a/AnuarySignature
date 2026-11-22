"""Configurable background UI for the dependent-drive directory report."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
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
        excluded_directory_names: list[str],
        included_directory_names: list[str],
        report_format: str,
        parent=None,
    ):
        super().__init__(parent)
        self.base_path = Path(base_path)
        self.excluded_directory_names = list(excluded_directory_names)
        self.included_directory_names = list(included_directory_names)
        self.report_format = report_format

    def _report_progress(self, completed: int, total: int, message: str):
        self.progress.emit(completed, total, message)

    def run(self):
        try:
            service = DependentDirectoryReportService(
                self.base_path,
                get_structure_file(REPORT_FILENAME),
                get_structure_file(REPORT_SETTINGS_FILENAME),
                structure_definition_path=get_structure_file("folders.json"),
            )
            preferences = service.save_exclusion_preferences(
                self.excluded_directory_names,
                self.included_directory_names,
            )
            self.preferences_saved.emit(preferences)
            result = service.generate_or_update(
                progress_callback=self._report_progress,
                report_format=self.report_format,
            )
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class DependentDirectoryReportDialog(QDialog):
    """Choose global folder exclusions and generate JSON or a plain-text tree."""

    def __init__(self, base_path: str | Path, parent=None):
        super().__init__(parent)
        self.base_path = Path(base_path)
        self.worker = None
        self.report_result = None
        self.report_generated = False
        self.preferences_saved = False
        self._preferences = {}
        self._directory_options = {}
        self._load_error = None
        self.structure_is_consistent = False

        self.service = DependentDirectoryReportService(
            self.base_path,
            get_structure_file(REPORT_FILENAME),
            get_structure_file(REPORT_SETTINGS_FILENAME),
            structure_definition_path=get_structure_file("folders.json"),
        )
        try:
            self._preferences = self.service.load_exclusion_preferences()
            self._directory_options = self.service.list_directory_category_options(
                self._preferences
            )
            self.structure_is_consistent = bool(
                self._directory_options.get("structure_consistent", False)
            )
        except Exception as error:
            self._load_error = str(error)

        self.setWindowTitle("Reporte de unidad dependiente")
        self.setModal(True)
        self.setMinimumSize(760, 640)
        self.resize(820, 720)
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
                padding: 7px 12px;
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
        self._populate_directory_categories()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Inventario de directorios de la unidad dependiente")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        scope = QLabel(
            f"Unidad dependiente: {self.base_path}\n"
            "La lista muestra cada categoría una sola vez, sin el prefijo. "
            "El prefijo real se calcula como max(0, año - 2003) y se rellena a dos dígitos. "
            "Las exclusiones se aplican globalmente y omiten toda la subcarpeta."
        )
        scope.setWordWrap(True)
        layout.addWidget(scope)

        format_row = QHBoxLayout()
        format_row.addWidget(QLabel("Formato del reporte:"))
        self.format_combo = QComboBox(self)
        self.format_combo.addItem("JSON — datos estructurados", "json")
        self.format_combo.addItem("TXT — árbol de directorios", "txt")
        format_row.addWidget(self.format_combo, 1)
        layout.addLayout(format_row)

        self.directory_tree = QTreeWidget(self)
        self.directory_tree.setColumnCount(2)
        self.directory_tree.setHeaderLabels(
            ["Tipo de carpeta", "Excluir en todos los años"]
        )
        self.directory_tree.setColumnWidth(0, 460)
        self.directory_tree.setColumnWidth(1, 220)
        self.directory_tree.setUniformRowHeights(True)
        self.directory_tree.setAlternatingRowColors(True)
        layout.addWidget(self.directory_tree, 1)

        self.status_label = QLabel()
        self.status_label.setWordWrap(False)
        self.status_label.setFixedHeight(36)
        self.status_label.setToolTip("")
        self.status_label.setStyleSheet(
            "background-color: #252525; border: 1px solid #444444; "
            "border-radius: 4px; padding: 4px 8px;"
        )
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        footer = QHBoxLayout()
        footer.addStretch()

        self.save_preferences_button = QPushButton("Guardar exclusiones")
        self.save_preferences_button.clicked.connect(self._save_preferences)
        footer.addWidget(self.save_preferences_button)

        self.generate_button = QPushButton("Generar reporte")
        self.generate_button.clicked.connect(self._start_worker)
        footer.addWidget(self.generate_button)

        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

    def _set_status(self, text: str, details: str | None = None):
        """Keep the visible status compact; show full diagnostics in its tooltip."""
        self.status_label.setText(text)
        self.status_label.setToolTip(details or text)

    def _structure_problem_text(self) -> str:
        mismatches = self._directory_options.get("mismatches", [])
        source = self._directory_options.get("structure_source", "desconocida")
        template_year = self._directory_options.get("template_year")
        if template_year:
            source += f" (año plantilla {template_year})"
        lines = [
            "La estructura de los años no coincide con la definición que "
            f"AnuarySignature utiliza para crear años ({source})."
        ]
        for item in mismatches:
            details = [
                f"{item.get('year', '')}: "
                f"{item.get('actual_folder_count', 0)} carpetas "
                f"(se esperaban {item.get('expected_folder_count', 0)})"
            ]
            if item.get("missing"):
                details.append("faltan: " + ", ".join(item["missing"]))
            if item.get("extra"):
                details.append("sobran: " + ", ".join(item["extra"]))
            lines.append(" • ".join(details))
        return "\n".join(lines)

    def _populate_directory_categories(self):
        self.directory_tree.clear()

        if self._load_error is not None:
            self._set_status(
                "No se pudo cargar la estructura del reporte.",
                self._load_error,
            )
            self.generate_button.setEnabled(False)
            self.save_preferences_button.setEnabled(False)
            return

        categories = self._directory_options.get("categories", [])
        for category in categories:
            item = QTreeWidgetItem(
                [str(category.get("name", "")), "Excluir"]
            )
            item.setData(
                0,
                Qt.ItemDataRole.UserRole,
                str(category.get("key", "")),
            )
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
                | Qt.ItemFlag.ItemIsEnabled
            )
            item.setCheckState(
                1,
                (
                    Qt.CheckState.Checked
                    if category.get("excluded")
                    else Qt.CheckState.Unchecked
                ),
            )
            years_present = int(category.get("years_present", 0))
            total_years = int(self._directory_options.get("year_count", 0))
            item.setToolTip(
                0,
                f"Presente en {years_present} de {total_years} años; "
                f"{category.get('directory_count', 0)} carpetas detectadas.",
            )
            self.directory_tree.addTopLevelItem(item)

        year_count = int(self._directory_options.get("year_count", 0))
        reference_count = int(
            self._directory_options.get("reference_folder_count", 0)
        )
        if self.structure_is_consistent:
            source = self._directory_options.get(
                "structure_source",
                "desconocida",
            )
            template_year = self._directory_options.get("template_year")
            source_label = (
                f"{source} · plantilla {template_year}"
                if template_year
                else source
            )
            visible_status = (
                f"{year_count} años · {reference_count} carpetas/año · "
                f"{len(categories)} categorías · {source_label}"
            )
            details = (
                f"Unidad: {self.base_path}\n"
                f"Fuente de estructura: {source_label}\n"
                "El prefijo de cada año se calcula como max(0, año - 2003), con dos dígitos. "
                "Las categorías se muestran sin ese prefijo y las exclusiones "
                "se aplican globalmente."
            )
            self._set_status(visible_status, details)
        else:
            mismatch_count = len(
                self._directory_options.get("mismatches", [])
            )
            self._set_status(
                f"Estructura no uniforme: {mismatch_count} años con diferencias.",
                self._structure_problem_text()
                + "\n\nLa generación permanece deshabilitada hasta "
                "corregir las carpetas faltantes o adicionales.",
            )

        self.generate_button.setEnabled(self.structure_is_consistent)
        self.save_preferences_button.setEnabled(True)

    def _collect_exclusion_preferences(self) -> tuple[list[str], list[str]]:
        excluded = set(
            self._preferences.get("excluded_directory_names", [])
        )
        included = set(
            self._preferences.get("included_directory_names", [])
        )
        for index in range(self.directory_tree.topLevelItemCount()):
            item = self.directory_tree.topLevelItem(index)
            key = str(item.data(0, Qt.ItemDataRole.UserRole) or "")
            if not key:
                continue

            excluded.discard(key)
            included.discard(key)
            if item.checkState(1) == Qt.CheckState.Checked:
                excluded.add(key)
            elif self.service.is_default_excluded_directory_name(key):
                included.add(key)

        return sorted(excluded), sorted(included)

    def _save_preferences(self):
        if self.worker is not None and self.worker.isRunning():
            return
        try:
            excluded, included = self._collect_exclusion_preferences()
            self._preferences = self.service.save_exclusion_preferences(
                excluded,
                included,
            )
            self.preferences_saved = True
            self._set_status(
                "Exclusiones globales guardadas en Structure."
            )
        except Exception as error:
            self._set_status(
                "No se pudieron guardar las exclusiones.",
                str(error),
            )

    def _start_worker(self):
        if self.worker is not None and self.worker.isRunning():
            return
        if self._load_error is not None or not self.structure_is_consistent:
            return

        excluded, included = self._collect_exclusion_preferences()
        report_format = str(self.format_combo.currentData() or "json")
        self.generate_button.setEnabled(False)
        self.save_preferences_button.setEnabled(False)
        self.close_button.setEnabled(False)
        self.directory_tree.setEnabled(False)
        self.format_combo.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self._set_status(
            "Guardando exclusiones e iniciando el recorrido de la unidad dependiente…"
        )

        worker = _DependentDirectoryReportWorker(
            self.base_path,
            excluded,
            included,
            report_format,
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
            self._set_status(message)
            return

        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(completed)
        self._set_status(f"{message} · {completed}/{total}")

    def _on_completed(self, result: dict):
        self.report_result = result
        self.report_generated = True
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        summary = (
            f"Reporte {result.get('report_format', '').upper()} generado · "
            f"{result.get('year_count', 0)} años · "
            f"{result.get('directory_count', 0)} directorios."
        )
        details = (
            "Reporte generado correctamente.\n"
            f"Formato: {result.get('report_format', '').upper()}\n"
            f"Años incluidos: {result.get('year_count', 0)}\n"
            f"Directorios registrados: {result.get('directory_count', 0)}\n"
            f"Carpetas excluidas: {result.get('excluded_directory_count', 0)}\n"
            f"Carpetas de personajes: {result.get('character_count', 0)}\n"
            f"Credenciales encontradas: {result.get('credential_found_count', 0)}\n"
            f"Sin credencial: {result.get('credential_missing_count', 0)}\n"
            f"Ubicación ambigua: {result.get('credential_ambiguous_count', 0)}\n"
            f"Con archivos adicionales: "
            f"{result.get('credential_additional_candidates_count', 0)}\n"
            f"Archivos de credencial detectados: "
            f"{result.get('credential_file_count', 0)}\n"
            f"Archivo: {result.get('report_path', '')}"
        )
        self._set_status(summary, details)
        self.directory_tree.setEnabled(True)
        self.format_combo.setEnabled(True)
        self.save_preferences_button.setEnabled(True)
        self.generate_button.setEnabled(self.structure_is_consistent)
        self.close_button.setEnabled(True)

    def _on_failed(self, message: str):
        self._set_status(
            "No se pudo generar el reporte. Se conserva el archivo anterior.",
            message,
        )
        self.directory_tree.setEnabled(True)
        self.format_combo.setEnabled(True)
        self.save_preferences_button.setEnabled(True)
        self.generate_button.setEnabled(self.structure_is_consistent)
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
