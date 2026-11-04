"""Editable table for architecture and business verbose resolutions."""

import json
import os
import tempfile
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from domain_visor.theme import Theme


class VerboseResolveDialog(QDialog):
    """Edit the two verbose-resolve JSON maps through a single Raw-key table."""

    saved = pyqtSignal()

    def __init__(self, architecture_path, business_path, parent=None):
        super().__init__(parent)
        self.architecture_path = Path(architecture_path)
        self.business_path = Path(business_path)

        self.setWindowTitle("Verbose Resolve Table")
        self.setMinimumSize(860, 560)
        self.resize(1020, 680)
        self.setModal(True)

        self._architecture_data = self._load_mapping(self.architecture_path)
        self._business_data = self._load_mapping(self.business_path)
        self._architecture_keys = set(self._architecture_data)
        self._business_keys = set(self._business_data)

        self._build_ui()
        self._populate_table()

    @staticmethod
    def _load_mapping(path):
        """Load and validate one Raw-to-verbose JSON object."""
        if not path.is_file():
            raise FileNotFoundError(f"No existe el archivo: {path}")

        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError(
                f"El archivo debe contener un objeto JSON: {path}"
            )

        for raw_key, resolved_value in data.items():
            if not isinstance(raw_key, str) or not isinstance(resolved_value, str):
                raise ValueError(
                    "Todas las claves Raw y sus resoluciones deben ser cadenas "
                    f"de texto. Archivo: {path}"
                )
        return data

    def _build_ui(self):
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QWidget {{
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
            }}
            QTableWidget {{
                background-color: #252526;
                alternate-background-color: #2d2d30;
                color: {Theme.TEXT_WHITE};
                gridline-color: #444444;
                border: 1px solid #444444;
                selection-background-color: #264f78;
                selection-color: #ffffff;
            }}
            QHeaderView::section {{
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #444444;
                padding: 7px;
                font-weight: bold;
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 7px 16px;
                color: #ffffff;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3e3e42;
                border-color: #85c1e9;
            }}
            QPushButton:pressed {{
                background-color: #1e1e1e;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(14, 14, 14, 14)
        main_layout.setSpacing(12)

        self.table = QTableWidget(self)
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(
            ["Raw", "Architecture", "Business"]
        )
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(False)
        self.table.verticalHeader().setVisible(False)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)

        main_layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)

        self.save_button = QPushButton("Guardar Cambios", self)
        self.cancel_button = QPushButton("Cancelar y Cerrar", self)
        self.save_button.clicked.connect(self.save_changes)
        self.cancel_button.clicked.connect(self.reject)

        footer.addWidget(self.save_button)
        footer.addWidget(self.cancel_button)
        main_layout.addLayout(footer)

    def _populate_table(self):
        """Display the union of Raw keys while retaining each file's own keys."""
        raw_keys = list(dict.fromkeys(
            list(self._architecture_data.keys())
            + list(self._business_data.keys())
        ))
        self.table.setRowCount(len(raw_keys))

        for row, raw_key in enumerate(raw_keys):
            raw_item = QTableWidgetItem(raw_key)
            raw_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
            )
            raw_item.setToolTip("Clave original; solo lectura.")
            self.table.setItem(row, 0, raw_item)

            architecture_item = QTableWidgetItem(
                self._architecture_data.get(raw_key, "")
            )
            architecture_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(row, 1, architecture_item)

            business_item = QTableWidgetItem(
                self._business_data.get(raw_key, "")
            )
            business_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEditable
            )
            self.table.setItem(row, 2, business_item)

    def _collect_mapping(self, column, original_keys):
        mapping = {}
        for row in range(self.table.rowCount()):
            raw_item = self.table.item(row, 0)
            value_item = self.table.item(row, column)
            if raw_item is None or value_item is None:
                continue

            raw_key = raw_item.text()
            value = value_item.text()

            # Keep keys that already belonged to this file, including values
            # intentionally cleared. Add absent keys only when given a value.
            if raw_key in original_keys or value != "":
                mapping[raw_key] = value
        return mapping

    def save_changes(self):
        """Persist both edited maps; keep the dialog open if either write fails."""
        architecture_data = self._collect_mapping(
            1, self._architecture_keys
        )
        business_data = self._collect_mapping(
            2, self._business_keys
        )

        # Stage both outputs first so serialization or disk-space errors happen
        # before either destination is replaced.
        staged = []
        try:
            for path, mapping in (
                (self.architecture_path, architecture_data),
                (self.business_path, business_data),
            ):
                path.parent.mkdir(parents=True, exist_ok=True)
                descriptor, temporary_name = tempfile.mkstemp(
                    prefix=f".{path.name}.",
                    suffix=".tmp",
                    dir=str(path.parent),
                    text=True,
                )
                staged.append((Path(temporary_name), path))
                with os.fdopen(
                    descriptor, "w", encoding="utf-8", newline="\n"
                ) as file:
                    json.dump(mapping, file, indent=4, ensure_ascii=False)
                    file.write("\n")
                    file.flush()
                    os.fsync(file.fileno())

            for temporary_path, destination in staged:
                os.replace(temporary_path, destination)

        except (OSError, TypeError, ValueError) as error:
            for temporary_path, _ in staged:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

            QMessageBox.critical(
                self,
                "Verbose Resolve Table",
                f"No se pudieron guardar los cambios:\n{error}",
            )
            return

        self.saved.emit()
        self.accept()
