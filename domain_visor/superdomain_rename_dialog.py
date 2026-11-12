"""Superdomain manager with its aggregated per-year Knowledge references."""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from character_visor.knowledge_wardrobe import (
    KnowledgeWardrobeWidget,
    resolve_marker_knowledge_directories,
)
from domain_visor.theme import Theme


class SuperDomainManagementDialog(QDialog):
    """Rename a superdomain and browse all of its _nglobal Knowledge folders."""

    def __init__(
        self,
        superdomain_id: int,
        current_name: str,
        infrastructure_path,
        base_path,
        years: list[int] | tuple[int, ...],
        parent=None,
    ):
        super().__init__(parent)
        self.superdomain_id = superdomain_id
        self.current_name = str(current_name)
        self.infrastructure_path = (
            Path(infrastructure_path) if infrastructure_path else None
        )
        self.base_path = Path(base_path).expanduser()
        self.years = sorted({int(year) for year in years})
        self.saved = False

        self.setWindowTitle("Gestionar Superdominio")
        self.setModal(True)
        self.setMinimumSize(980, 680)
        self.resize(1120, 760)
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
            QLabel, QGroupBox {{
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
            QGroupBox {{
                border: 1px solid #555555;
                border-radius: 5px;
                margin-top: 10px;
                padding: 8px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }}
            QTabWidget::pane {{
                border: 1px solid #555555;
                border-radius: 4px;
            }}
            QTabBar::tab {{
                background-color: #252525;
                color: {Theme.TEXT_WHITE};
                border: 1px solid #444444;
                padding: 7px 14px;
            }}
            QTabBar::tab:selected {{
                background-color: #3e3e42;
                border-bottom-color: #85c1e9;
            }}
        """)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        rename_row = QHBoxLayout()
        rename_row.setSpacing(8)
        rename_row.addWidget(QLabel("Nombre del superdominio:"))

        self.txt_name = QLineEdit(self._normalize_name(self.current_name))
        self.txt_name.textChanged.connect(self._normalize_text_in_place)
        rename_row.addWidget(self.txt_name, 1)

        self.btn_rename = QPushButton("Renombrar")
        self.btn_rename.clicked.connect(self.rename_superdomain)
        rename_row.addWidget(self.btn_rename)

        self.btn_revert = QPushButton("Revertir")
        self.btn_revert.clicked.connect(self.revert_name)
        rename_row.addWidget(self.btn_revert)
        layout.addLayout(rename_row)

        self.knowledge_group = QGroupBox(
            "Armario y Referencias (Knowledge)",
            self,
        )
        group_layout = QVBoxLayout(self.knowledge_group)
        group_layout.setContentsMargins(8, 12, 8, 8)

        self.year_tabs = QTabWidget(self.knowledge_group)
        group_layout.addWidget(self.year_tabs, 1)
        self._populate_year_tabs()
        layout.addWidget(self.knowledge_group, 1)

        close_row = QHBoxLayout()
        close_row.addStretch()
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        close_row.addWidget(self.btn_close)
        layout.addLayout(close_row)

    @staticmethod
    def _normalize_name(value: str) -> str:
        return str(value).replace(" ", "_").lower()

    def _normalize_text_in_place(self, value: str):
        normalized = self._normalize_name(value)
        if normalized == value:
            return
        cursor_position = self.txt_name.cursorPosition()
        self.txt_name.blockSignals(True)
        self.txt_name.setText(normalized)
        self.txt_name.setCursorPosition(min(cursor_position, len(normalized)))
        self.txt_name.blockSignals(False)

    def revert_name(self):
        """Restore the most recently persisted superdomain name."""
        self.txt_name.setText(self._normalize_name(self.current_name))

    def _populate_year_tabs(self):
        if not self.years:
            empty = QLabel("El superdominio no contiene años configurados.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.year_tabs.addTab(empty, "Sin años")
            return

        for year in self.years:
            knowledge_root, matching_directories = (
                resolve_marker_knowledge_directories(
                    self.base_path,
                    year,
                    "_nglobal",
                )
            )
            prefix = f"{max(0, year - 2003):02d}"
            destination = (
                matching_directories[0]
                if matching_directories
                else knowledge_root / f"{prefix}. _nglobal"
            )
            widget = KnowledgeWardrobeWidget(
                destination,
                parent=self,
                source_directories=(
                    matching_directories
                    if matching_directories
                    else [destination]
                ),
                destination_directory=destination,
                missing_folder_label=(
                    f"carpeta de Knowledge que contiene '_nglobal' para {year}"
                ),
            )
            self.year_tabs.addTab(widget, str(year))

    def rename_superdomain(self):
        """Persist a normalized name without closing the Knowledge manager."""
        new_name = self._normalize_name(self.txt_name.text().strip())
        if not new_name:
            QMessageBox.warning(
                self,
                "Validación",
                "El nombre del superdominio no puede estar vacío.",
            )
            return

        if new_name == self.current_name:
            self.revert_name()
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

            self.current_name = new_name
            self.txt_name.setText(new_name)
            self.saved = True
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            QMessageBox.critical(
                self,
                "Error al renombrar",
                f"No se pudo actualizar infrastructure.json:\n{error}",
            )


# Keep the former class name available for any external imports.
SuperDomainRenameDialog = SuperDomainManagementDialog
