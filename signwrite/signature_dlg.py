import os
import json
import traceback
from .const import (
    CONTACTS_DB_PATH, DEFAULT_CONTACTS_DB,
    CLASSIFICATIONS_DB_PATH, 
    default_clasifications_dict
)

from PyQt6.QtWidgets import (
    QVBoxLayout, QPushButton, QLabel,
    QComboBox, QHBoxLayout, QLineEdit, QMessageBox,
    QInputDialog, QFormLayout, QDialog, QListWidget, 
    QListWidgetItem, QDialogButtonBox, QAbstractItemView
)
from PyQt6.QtCore import pyqtSignal

    
DEFAULT_CLASSIFICATIONS_DB = [
    {"label": label, "code": code, "subfolder": ""} for label, code in default_clasifications_dict
]

def load_classifications_db() -> list:
    """Carga classifications_db.json, creándolo con los valores por defecto si no existe o está corrupto."""
    if not os.path.exists(CLASSIFICATIONS_DB_PATH):
        save_classifications_db(DEFAULT_CLASSIFICATIONS_DB)
        return json.loads(json.dumps(DEFAULT_CLASSIFICATIONS_DB))
    try:
        with open(CLASSIFICATIONS_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("Formato inválido en classifications_db.json")
        cleaned = []
        for item in data:
            label = str(item.get("label", "")).strip()
            code = str(item.get("code", "")).strip()
            subfolder = str(item.get("subfolder", "")).strip()
            if label and code:
                cleaned.append({"label": label, "code": code, "subfolder": subfolder})
        return cleaned if cleaned else json.loads(json.dumps(DEFAULT_CLASSIFICATIONS_DB))
    except Exception:
        traceback.print_exc()
        return json.loads(json.dumps(DEFAULT_CLASSIFICATIONS_DB))

def save_classifications_db(data: list):
    with open(CLASSIFICATIONS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_contacts_db() -> dict:
    """Carga contacts_db.json, creándolo con estructura por defecto si no existe o está corrupto."""
    if not os.path.exists(CONTACTS_DB_PATH):
        save_contacts_db(DEFAULT_CONTACTS_DB)
        return json.loads(json.dumps(DEFAULT_CONTACTS_DB))
    try:
        with open(CONTACTS_DB_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for key in DEFAULT_CONTACTS_DB:
            if key not in data or not isinstance(data[key], list):
                data[key] = []
        return data
    except Exception:
        traceback.print_exc()
        return json.loads(json.dumps(DEFAULT_CONTACTS_DB))


def save_contacts_db(data: dict):
    with open(CONTACTS_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ContactsManagerDialog(QDialog):
    """
    Diálogo para agregar, editar y eliminar Autores/Organismos, Destinatarios/Contactos
    y Supervisores. Cada cambio se persiste de inmediato en contacts_db.json y se
    notifica al padre mediante la señal contacts_updated para refrescar los combos.
    """
    contacts_updated = pyqtSignal()

    CATEGORY_LABELS = [
        ("autores", "Autores / Organismos"),
        ("destinatarios", "Destinatarios / Contactos"),
        ("supervisores", "Supervisores"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestionar Contactos")
        self.setMinimumSize(400, 420)
        self.data = load_contacts_db()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        row_cat = QHBoxLayout()
        row_cat.addWidget(QLabel("Categoría:"))
        self.category_combo = QComboBox()
        for key, label in self.CATEGORY_LABELS:
            self.category_combo.addItem(label, key)
        self.category_combo.currentIndexChanged.connect(self.refresh_list)
        row_cat.addWidget(self.category_combo)
        row_cat.addStretch()
        layout.addLayout(row_cat)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(self.edit_item)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Agregar")
        add_btn.clicked.connect(self.add_item)
        edit_btn = QPushButton("Editar")
        edit_btn.clicked.connect(self.edit_item)
        delete_btn = QPushButton("Eliminar")
        delete_btn.clicked.connect(self.delete_item)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)
        layout.addLayout(btn_row)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.close)
        button_box.accepted.connect(self.close)
        button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.close)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.refresh_list()

    def current_category_key(self) -> str:
        return self.category_combo.currentData()

    def refresh_list(self):
        self.list_widget.clear()
        key = self.current_category_key()
        for value in self.data.get(key, []):
            self.list_widget.addItem(QListWidgetItem(value))

    def persist_and_notify(self):
        save_contacts_db(self.data)
        self.contacts_updated.emit()

    def add_item(self):
        text, ok = QInputDialog.getText(self, "Agregar", "Nuevo valor:")
        text = text.strip()
        if not ok or not text:
            return
        key = self.current_category_key()
        if text in self.data.get(key, []):
            QMessageBox.information(self, "Duplicado", "Ese valor ya existe en la lista.")
            return
        self.data.setdefault(key, []).append(text)
        self.persist_and_notify()
        self.refresh_list()

    def edit_item(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Editar", "Selecciona un elemento primero.")
            return
        old_value = item.text()
        text, ok = QInputDialog.getText(self, "Editar", "Nuevo valor:", text=old_value)
        text = text.strip()
        if not ok or not text or text == old_value:
            return
        key = self.current_category_key()
        try:
            idx = self.data[key].index(old_value)
            self.data[key][idx] = text
            self.persist_and_notify()
            self.refresh_list()
        except ValueError:
            pass

    def delete_item(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Eliminar", "Selecciona un elemento primero.")
            return
        value = item.text()
        confirm = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Eliminar '{value}' de la lista?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        key = self.current_category_key()
        try:
            self.data[key].remove(value)
            self.persist_and_notify()
            self.refresh_list()
        except ValueError:
            pass


class ClassificationEditDialog(QDialog):
    """
    Diálogo simple para capturar/editar el nombre visible, el código interno
    y la subcarpeta de una clasificación.
    """

    def __init__(self, parent=None, label: str = "", code: str = "", subfolder: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Clasificación")
        self.setMinimumWidth(320)

        layout = QFormLayout()
        self.label_input = QLineEdit(label)
        self.label_input.setPlaceholderText("Ej: Análisis de episodios")
        self.code_input = QLineEdit(code)
        self.code_input.setPlaceholderText("Ej: analyze-ep")

        self.subfolder_combo = QComboBox()
        self.subfolder_combo.addItems(["_basic", "_local", "_ndomain", "_nglobal", "{character_selection}"])
        valid_subfolders = ["_basic", "_local", "_ndomain", "_nglobal", "{character_selection}"]
        if subfolder in valid_subfolders:
            self.subfolder_combo.setCurrentText(subfolder)
        else:
            self.subfolder_combo.setCurrentText("_basic")

        layout.addRow("Nombre visible:", self.label_input)
        layout.addRow("Código interno:", self.code_input)
        layout.addRow("Subcarpeta:", self.subfolder_combo)

        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.setLayout(layout)

    def get_values(self) -> tuple[str, str, str]:
        return (
            self.label_input.text().strip(),
            self.code_input.text().strip(),
            self.subfolder_combo.currentText().strip()
        )


class ClassificationsManagerDialog(QDialog):
    """
    Diálogo para agregar, editar y eliminar clasificaciones. Cada cambio se
    persiste de inmediato en classifications_db.json y se notifica al padre
    mediante la señal classifications_updated para refrescar el class_combo.
    """
    classifications_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Gestionar Clasificaciones")
        self.setMinimumSize(420, 420)
        self.data = load_classifications_db()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.list_widget.itemDoubleClicked.connect(self.edit_item)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Agregar")
        add_btn.clicked.connect(self.add_item)
        edit_btn = QPushButton("Editar")
        edit_btn.clicked.connect(self.edit_item)
        delete_btn = QPushButton("Eliminar")
        delete_btn.clicked.connect(self.delete_item)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(edit_btn)
        btn_row.addWidget(delete_btn)
        layout.addLayout(btn_row)

        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.rejected.connect(self.close)
        button_box.accepted.connect(self.close)
        button_box.button(QDialogButtonBox.StandardButton.Close).clicked.connect(self.close)
        layout.addWidget(button_box)

        self.setLayout(layout)
        self.refresh_list()

    def refresh_list(self):
        self.list_widget.clear()
        for entry in self.data:
            sf = entry.get("subfolder", "") or "_basic"
            item = QListWidgetItem(f'{entry["label"]}   [{entry["code"]}]   ({sf})')
            self.list_widget.addItem(item)

    def persist_and_notify(self):
        save_classifications_db(self.data)
        self.classifications_updated.emit()

    def code_exists(self, code: str, ignore_index: int = -1) -> bool:
        return any(
            i != ignore_index and entry["code"] == code
            for i, entry in enumerate(self.data)
        )

    def add_item(self):
        dialog = ClassificationEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        label, code, subfolder = dialog.get_values()
        if not label or not code:
            QMessageBox.warning(self, "Datos incompletos",
                                "Debes indicar el nombre visible y el código interno.")
            return
        if self.code_exists(code):
            QMessageBox.information(self, "Duplicado",
                                    "Ya existe una clasificación con ese código interno.")
            return
        self.data.append({"label": label, "code": code, "subfolder": subfolder})
        self.persist_and_notify()
        self.refresh_list()

    def edit_item(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Editar", "Selecciona una clasificación primero.")
            return
        row = self.list_widget.currentRow()
        entry = self.data[row]
        dialog = ClassificationEditDialog(
            self, 
            label=entry["label"], 
            code=entry["code"], 
            subfolder=entry.get("subfolder", "")
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        label, code, subfolder = dialog.get_values()
        if not label or not code:
            QMessageBox.warning(self, "Datos incompletos",
                                "Debes indicar el nombre visible y el código interno.")
            return
        if self.code_exists(code, ignore_index=row):
            QMessageBox.information(self, "Duplicado",
                                    "Ya existe una clasificación con ese código interno.")
            return
        self.data[row] = {"label": label, "code": code, "subfolder": subfolder}
        self.persist_and_notify()
        self.refresh_list()

    def delete_item(self):
        item = self.list_widget.currentItem()
        if item is None:
            QMessageBox.information(self, "Eliminar", "Selecciona una clasificación primero.")
            return
        row = self.list_widget.currentRow()
        entry = self.data[row]
        confirm = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Eliminar '{entry['label']}' de la lista?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        del self.data[row]
        self.persist_and_notify()
        self.refresh_list()

