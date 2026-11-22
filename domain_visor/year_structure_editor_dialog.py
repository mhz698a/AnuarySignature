"""Dialog to edit folders.json and synchronize existing year directories."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from domain_visor.theme import Theme
from engines.structure_paths import get_structure_file
from engines.year_structure_editor import (
    YearStructureEditorError,
    YearStructureEditorService,
)


_ORIGINAL_NAME_ROLE = int(Qt.ItemDataRole.UserRole) + 1
_KIND_ROLE = int(Qt.ItemDataRole.UserRole) + 2


class _YearStructureApplyWorker(QThread):
    completed = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(
        self,
        base_path: Path,
        folders_json_path: Path,
        rows: list[dict[str, Any]],
        original_template: dict[str, list[str]],
        parent=None,
    ):
        super().__init__(parent)
        self.base_path = Path(base_path)
        self.folders_json_path = Path(folders_json_path)
        self.rows = rows
        self.original_template = original_template

    def run(self):
        try:
            result = YearStructureEditorService(
                self.base_path,
                self.folders_json_path,
            ).apply_template_rows(self.rows, self.original_template)
            self.completed.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


class YearStructureEditorDialog(QDialog):
    """Edit the year template and safely propagate its directory names."""

    def __init__(self, base_path: str | Path, parent=None):
        super().__init__(parent)
        self.base_path = Path(base_path).expanduser()
        self.folders_json_path = get_structure_file("folders.json")
        self.service = YearStructureEditorService(
            self.base_path,
            self.folders_json_path,
        )
        self.original_template = self.service.load_template()
        self.worker = None
        self.applied = False

        self.setWindowTitle("Editar plantilla y Estructura de años")
        self.setModal(True)
        self.setMinimumSize(700, 560)
        self.resize(820, 680)
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
                alternate-background-color: #2b2b2b;
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
            }}
        """)

        self._build_ui()
        self._populate_tree()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Plantilla de carpetas para todos los años")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(title)

        description = QLabel(
            f"Archivo: {self.folders_json_path}\n"
            "Cada año utiliza el prefijo max(0, año - 2003), con dos dígitos. "
            "Las carpetas principales contienen sus subcarpetas definidas aquí."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        season_note = QLabel(
            "___[] es un marcador reservado: en cada año se conserva el nombre "
            "de temporada real entre corchetes (por ejemplo, ___[Season 2026]). "
            "No se renombra ni se elimina desde este editor."
        )
        season_note.setWordWrap(True)
        season_note.setStyleSheet("color: #bdbdbd;")
        layout.addWidget(season_note)

        self.folder_tree = QTreeWidget(self)
        self.folder_tree.setColumnCount(1)
        self.folder_tree.setHeaderLabels(["Carpetas principales y subcarpetas"])
        self.folder_tree.setAlternatingRowColors(True)
        self.folder_tree.setUniformRowHeights(True)
        layout.addWidget(self.folder_tree, 1)

        actions = QHBoxLayout()
        self.add_folder_button = QPushButton("Agregar carpeta")
        self.add_folder_button.clicked.connect(self._add_folder)
        actions.addWidget(self.add_folder_button)

        self.add_subfolder_button = QPushButton("Agregar subcarpeta")
        self.add_subfolder_button.clicked.connect(self._add_subfolder)
        actions.addWidget(self.add_subfolder_button)

        self.rename_button = QPushButton("Renombrar")
        self.rename_button.clicked.connect(self._rename_selected)
        actions.addWidget(self.rename_button)

        self.remove_button = QPushButton("Quitar de plantilla")
        self.remove_button.clicked.connect(self._remove_selected)
        actions.addWidget(self.remove_button)
        layout.addLayout(actions)

        self.status_label = QLabel(
            "Las carpetas retiradas de la plantilla no se borran de los años."
        )
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(
            "background-color: #252525; border: 1px solid #444444; "
            "border-radius: 4px; padding: 6px 8px;"
        )
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        footer = QHBoxLayout()
        footer.addStretch()
        self.apply_button = QPushButton("Guardar plantilla y actualizar años")
        self.apply_button.clicked.connect(self._start_apply)
        footer.addWidget(self.apply_button)

        self.close_button = QPushButton("Cerrar")
        self.close_button.clicked.connect(self.accept)
        footer.addWidget(self.close_button)
        layout.addLayout(footer)

    def _new_item(
        self,
        name: str,
        kind: str,
        original_name: str | None,
    ) -> QTreeWidgetItem:
        item = QTreeWidgetItem([name])
        item.setData(0, _KIND_ROLE, kind)
        item.setData(0, _ORIGINAL_NAME_ROLE, original_name)
        item.setToolTip(
            0,
            "Carpeta principal" if kind == "folder" else "Subcarpeta",
        )
        return item

    def _populate_tree(self):
        self.folder_tree.clear()
        for folder_name, subfolders in self.original_template.items():
            root = self._new_item(folder_name, "folder", folder_name)
            if folder_name == "___[]":
                root.setToolTip(
                    0,
                    "Marcador reservado. El nombre real se obtiene de la temporada de cada año.",
                )
            self.folder_tree.addTopLevelItem(root)
            for subfolder in subfolders:
                root.addChild(
                    self._new_item(subfolder, "subfolder", subfolder)
                )
            root.setExpanded(True)

    def _selected_folder(self) -> QTreeWidgetItem | None:
        item = self.folder_tree.currentItem()
        if item is None:
            return None
        return item if item.parent() is None else item.parent()

    def _add_folder(self):
        name, accepted = QInputDialog.getText(
            self,
            "Agregar carpeta",
            "Nombre de la nueva carpeta principal:",
        )
        if not accepted or not name:
            return
        item = self._new_item(name.strip(), "folder", None)
        self.folder_tree.addTopLevelItem(item)
        self.folder_tree.setCurrentItem(item)
        item.setExpanded(True)

    def _add_subfolder(self):
        parent = self._selected_folder()
        if parent is None:
            QMessageBox.information(
                self,
                "Agregar subcarpeta",
                "Selecciona primero una carpeta principal.",
            )
            return

        name, accepted = QInputDialog.getText(
            self,
            "Agregar subcarpeta",
            f"Nombre de la subcarpeta de '{parent.text(0)}':",
        )
        if not accepted or not name:
            return
        item = self._new_item(name.strip(), "subfolder", None)
        parent.addChild(item)
        parent.setExpanded(True)
        self.folder_tree.setCurrentItem(item)

    def _rename_selected(self):
        item = self.folder_tree.currentItem()
        if item is None:
            return
        if (
            item.parent() is None
            and item.data(0, _ORIGINAL_NAME_ROLE) == "___[]"
        ):
            QMessageBox.information(
                self,
                "Marcador de temporada",
                "___[] es un marcador reservado. El nombre entre corchetes "
                "se conserva de forma independiente para cada año.",
            )
            return

        old_name = item.text(0)
        name, accepted = QInputDialog.getText(
            self,
            "Renombrar carpeta",
            "Nuevo nombre:",
            text=old_name,
        )
        if not accepted or not name:
            return

        name = name.strip()
        if not name or name == old_name:
            return

        original_name = item.data(0, _ORIGINAL_NAME_ROLE)
        if original_name is None:
            item.setData(0, _ORIGINAL_NAME_ROLE, None)
        else:
            item.setData(0, _ORIGINAL_NAME_ROLE, original_name)
        item.setText(0, name)

    def _remove_selected(self):
        item = self.folder_tree.currentItem()
        if item is None:
            return
        if (
            item.parent() is None
            and item.data(0, _ORIGINAL_NAME_ROLE) == "___[]"
        ):
            QMessageBox.information(
                self,
                "Marcador de temporada",
                "___[] es un marcador reservado y no se puede quitar.",
            )
            return

        kind = "carpeta principal" if item.parent() is None else "subcarpeta"
        reply = QMessageBox.question(
            self,
            "Quitar de plantilla",
            f"¿Quitar esta {kind} de folders.json?\n\n"
            "La carpeta que ya exista en los años no se eliminará ni perderá su contenido.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        if item.parent() is None:
            index = self.folder_tree.indexOfTopLevelItem(item)
            self.folder_tree.takeTopLevelItem(index)
        else:
            parent = item.parent()
            parent.removeChild(item)

    def _collect_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for index in range(self.folder_tree.topLevelItemCount()):
            root = self.folder_tree.topLevelItem(index)
            row = {
                "old_name": root.data(0, _ORIGINAL_NAME_ROLE),
                "name": root.text(0),
                "subfolders": [],
            }
            for child_index in range(root.childCount()):
                child = root.child(child_index)
                row["subfolders"].append(
                    {
                        "old_name": child.data(0, _ORIGINAL_NAME_ROLE),
                        "name": child.text(0),
                    }
                )
            rows.append(row)
        return rows

    def _start_apply(self):
        if self.worker is not None and self.worker.isRunning():
            return

        rows = self._collect_rows()
        try:
            preview = self.service.preview_template_rows(
                rows,
                self.original_template,
            )
        except YearStructureEditorError as error:
            QMessageBox.warning(self, "Plantilla de años", str(error))
            return

        if not preview["changed"]:
            self.status_label.setText("No hay cambios en la plantilla.")
            return

        summary = (
            f"Años revisados: {preview['year_count']}\n"
            f"Directorios que se renombrarán: {preview['renamed_count']}\n"
            f"Directorios nuevos que se crearán: {preview['created_count']}\n\n"
            "Las carpetas retiradas de folders.json se conservarán en disco. "
            "Ninguna carpeta existente se elimina ni se sobrescribe."
        )
        reply = QMessageBox.question(
            self,
            "Confirmar actualización de años",
            summary + "\n\n¿Aplicar los cambios?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self._set_busy(True)
        worker = _YearStructureApplyWorker(
            self.base_path,
            self.folders_json_path,
            rows,
            self.original_template,
            self,
        )
        worker.completed.connect(self._on_completed)
        worker.failed.connect(self._on_failed)
        self.worker = worker
        worker.start()

    def _set_busy(self, busy: bool):
        for button in (
            self.add_folder_button,
            self.add_subfolder_button,
            self.rename_button,
            self.remove_button,
            self.apply_button,
            self.close_button,
        ):
            button.setEnabled(not busy)
        self.folder_tree.setEnabled(not busy)
        self.progress_bar.setVisible(busy)

    def _on_completed(self, result: dict):
        self.applied = bool(result.get("changed"))
        renamed = int(result.get("renamed_count", 0))
        created = int(result.get("created_count", 0))
        self.status_label.setText(
            f"Plantilla guardada. {renamed} directorios renombrados y "
            f"{created} directorios nuevos creados en "
            f"{result.get('year_count', 0)} años."
        )
        self.apply_button.setEnabled(False)
        self.close_button.setEnabled(True)
        self.folder_tree.setEnabled(True)
        self.progress_bar.setVisible(False)
        QMessageBox.information(
            self,
            "Estructura actualizada",
            "folders.json se guardó correctamente y los años fueron sincronizados.\n\n"
            "Los cambios permanecen locales en el repositorio Structure; "
            "publícalos con Ajustes → Sincronizar Structure con GitHub.",
        )

    def _on_failed(self, message: str):
        self._set_busy(False)
        QMessageBox.critical(
            self,
            "No se pudo actualizar la estructura",
            message,
        )

    def closeEvent(self, event):
        if self.worker is not None and self.worker.isRunning():
            event.ignore()
            self.status_label.setText(
                "La actualización está en curso. Espera a que termine antes de cerrar."
            )
            return
        super().closeEvent(event)
