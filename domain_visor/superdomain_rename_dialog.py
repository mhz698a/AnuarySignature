"""Rename a superdomain in infrastructure.json."""

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from domain_visor.theme import Theme


class SuperDomainRenameDialog(QDialog):
    def __init__(
        self,
        superdomain_id: int,
        current_name: str,
        infrastructure_path,
        parent=None,
    ):
        super().__init__(parent)
        self.superdomain_id = superdomain_id
        self.current_name = str(current_name)
        self.infrastructure_path = (
            Path(infrastructure_path) if infrastructure_path else None
        )
        self.saved = False

        self.setWindowTitle("Renombrar Superdominio")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.resize(620, 180)
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
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: {Theme.TEXT_WHITE};
            }}
            QLineEdit:focus {{
                border-color: #85c1e9;
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 14px;
                color: {Theme.TEXT_WHITE};
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: #3e3e42;
                border-color: #85c1e9;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)
        layout.addWidget(QLabel("Nombre del superdominio:"))

        self.txt_name = QLineEdit(self._normalize(self.current_name), self)
        self.txt_name.textChanged.connect(self._normalize_text_in_place)
        layout.addWidget(self.txt_name)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self.save_data)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(self.btn_save)
        buttons.addWidget(self.btn_cancel)
        layout.addLayout(buttons)

    @staticmethod
    def _normalize(value: str) -> str:
        return str(value).replace(" ", "_").lower()

    def _normalize_text_in_place(self, value: str):
        normalized = self._normalize(value)
        if normalized == value:
            return
        cursor_position = self.txt_name.cursorPosition()
        self.txt_name.blockSignals(True)
        self.txt_name.setText(normalized)
        self.txt_name.setCursorPosition(min(cursor_position, len(normalized)))
        self.txt_name.blockSignals(False)

    def save_data(self):
        new_name = self.txt_name.text().strip()
        if not new_name:
            QMessageBox.warning(
                self,
                "Validación",
                "El nombre del superdominio no puede estar vacío.",
            )
            return

        if not self.infrastructure_path or not self.infrastructure_path.is_file():
            QMessageBox.critical(
                self,
                "Error",
                "No se encontró la ruta del archivo de infraestructura.",
            )
            return

        try:
            with self.infrastructure_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            if not isinstance(data, list):
                raise ValueError("La raíz de infrastructure.json debe ser una lista.")

            target = None
            for superdomain in data:
                matches = (
                    superdomain.get("super_id") == self.superdomain_id
                    if self.superdomain_id
                    else superdomain.get("superdomain") == self.current_name
                )
                if matches:
                    target = superdomain
                    break

            if target is None:
                QMessageBox.warning(
                    self,
                    "Superdominio no encontrado",
                    f"No se encontró '{self.current_name}' en infrastructure.json.",
                )
                return

            target["superdomain"] = new_name
            with self.infrastructure_path.open("w", encoding="utf-8") as file:
                json.dump(data, file, indent=2, ensure_ascii=False)
                file.write("\n")

            self.saved = True
            self.accept()
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            QMessageBox.critical(
                self,
                "Error al guardar",
                f"No se pudo actualizar infrastructure.json:\n{error}",
            )
