# domain_visor/type_underwear_editor.py

import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLabel, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt
from domain_visor.theme import Theme

DEFAULT_TYPE_UNDERWEAR_LIST = [
    "Boybrief", "Girlbrief Clasic Mid Low rise", "boyshort boxer",
    "Thong", "Bikini", "Hipster", "Tanga Brief", "French Cut",
    "Brief Slip", "Brief Mid high rise", "Pantaloons"
]

DEFAULT_TYPE_UNDERWEAR_PATH = Path("__structure__/type_under_list.json")

def load_global_type_underwear(filepath=None) -> list[str]:
    """
    Carga la lista global de ropa interior desde `__structure__/type_under_list.json`.
    Si el archivo no existe, lo crea automáticamente con la lista por defecto.
    Estructura JSON: {"type_underwear": [...]}
    """
    path = Path(filepath) if filepath else DEFAULT_TYPE_UNDERWEAR_PATH
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        save_global_type_underwear(DEFAULT_TYPE_UNDERWEAR_LIST, path)
        return list(DEFAULT_TYPE_UNDERWEAR_LIST)

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "type_underwear" in data and isinstance(data["type_underwear"], list):
                return data["type_underwear"]
            elif isinstance(data, list):
                # Fallback por si acaso fue guardado como lista plana anteriormente
                return data
    except Exception as e:
        print(f"Error cargando {path}: {e}")

    return list(DEFAULT_TYPE_UNDERWEAR_LIST)

def save_global_type_underwear(items: list[str], filepath=None):
    """
    Guarda la lista global de ropa interior en `__structure__/type_under_list.json`.
    """
    path = Path(filepath) if filepath else DEFAULT_TYPE_UNDERWEAR_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"type_underwear": items}, f, indent=4, ensure_ascii=False)


class TypeUnderwearEditorDialog(QDialog):
    """
    Modal para gestionar (Añadir, Editar, Eliminar) el catálogo global de `type_underwear`.
    """
    def __init__(self, filepath=None, parent=None):
        super().__init__(parent)
        self.filepath = Path(filepath) if filepath else DEFAULT_TYPE_UNDERWEAR_PATH
        self.setWindowTitle("Editar catálogo de ropa interior")
        self.setModal(True)
        self.resize(400, 350)

        # Quitar botón de ayuda
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QWidget {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 11px;
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
                font-weight: bold;
            }}
            QListWidget {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                color: #ffffff;
            }}
            QListWidget::item {{
                padding: 4px;
            }}
            QListWidget::item:hover {{
                background-color: #3e3e42;
            }}
            QListWidget::item:selected {{
                background-color: #007acc;
                color: #ffffff;
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                color: {Theme.TEXT_WHITE};
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

        self.init_ui()
        self.load_items()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(10)

        main_layout.addWidget(QLabel("Lista Global (type_underwear):"))

        content_layout = QHBoxLayout()
        self.list_widget = QListWidget()
        content_layout.addWidget(self.list_widget, 1)

        btn_layout = QVBoxLayout()

        self.btn_add = QPushButton("Añadir")
        self.btn_add.clicked.connect(self.add_item)

        self.btn_edit = QPushButton("Editar")
        self.btn_edit.clicked.connect(self.edit_item)

        self.btn_delete = QPushButton("Eliminar")
        self.btn_delete.clicked.connect(self.delete_item)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addStretch()

        content_layout.addLayout(btn_layout)
        main_layout.addLayout(content_layout)

        # Footer
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self.save_and_close)

        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(footer_layout)

    def load_items(self):
        self.list_widget.clear()
        items = load_global_type_underwear(self.filepath)
        for item in items:
            self.list_widget.addItem(item)

    def add_item(self):
        text, ok = QInputDialog.getText(self, "Añadir Elemento", "Nombre del tipo de ropa interior:")
        if ok and text.strip():
            new_val = text.strip()
            # Verificar si ya existe
            existing = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
            if new_val in existing:
                QMessageBox.warning(self, "Advertencia", "El elemento ya existe en la lista.")
                return
            self.list_widget.addItem(new_val)

    def edit_item(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "Información", "Por favor selecciona un elemento para editar.")
            return

        text, ok = QInputDialog.getText(self, "Editar Elemento", "Modificar nombre:", text=current_item.text())
        if ok and text.strip():
            new_val = text.strip()
            existing = [self.list_widget.item(i).text() for i in range(self.list_widget.count()) if self.list_widget.item(i) != current_item]
            if new_val in existing:
                QMessageBox.warning(self, "Advertencia", "Ya existe otro elemento con ese nombre.")
                return
            current_item.setText(new_val)

    def delete_item(self):
        current_item = self.list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "Información", "Por favor selecciona un elemento para eliminar.")
            return

        row = self.list_widget.row(current_item)
        self.list_widget.takeItem(row)

    def save_and_close(self):
        items = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        save_global_type_underwear(items, self.filepath)
        self.accept()
