# domain_visor/character_dialog.py

import os
import json
import traceback
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QComboBox, QPushButton, QMessageBox, QFileDialog, QScrollArea, QWidget,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from domain_visor.theme import Theme
from character_visor.raw_json_editor import RawJSONEditorDialog
from character_visor.type_underwear_editor import load_global_type_underwear, TypeUnderwearEditorDialog

class CharacterEditDialog(QDialog):
    """
    Diálogo modal para editar los datos de un personaje en su archivo JSON.
    """

    galleryanuary_requested = pyqtSignal(str)
    FORM_CREDENTIAL_KEYS = frozenset({
        "year",
        "name",
        "alterego",
        "icon_path",
        "background_path",
        "type_underwear",
        "short_masked_alterego",
        "character_json_path",
        "color_group",
        "secondary_color",
        "profession_group",
        "time_of_year",
    })

    def __init__(self, char_data, parent=None):
        super().__init__(parent)
        self.char_data = char_data.copy()  # Trabajar con una copia
        self.original_char_data = char_data
        self.saved = False
        self._raw_data_staged = False

        self.setWindowTitle("Modificar Personaje")
        self.setModal(True)
        self.setMinimumWidth(900)
        self.resize(1000, 650)

        # Quitar botón de ayuda
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Aplicar estilos acordes con Theme
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
            QLineEdit, QDateEdit {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                color: {Theme.TEXT_WHITE};
            }}
            QLineEdit:focus, QDateEdit:focus {{
                border-color: #85c1e9;
            }}
            QLineEdit[readOnly="true"] {{
                background-color: #1e1e1e;
                color: #888888;
                border-color: #333333;
            }}
            QComboBox {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                color: {Theme.TEXT_WHITE};
            }}
            QComboBox:focus {{
                border-color: #85c1e9;
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

        # La ubicación de la credencial determina la carpeta del personaje.
        json_path_str = self.char_data.get("character_json_path", "")
        if json_path_str:
            self.initial_character_json_path = Path(json_path_str)
        else:
            # Compatibilidad con JSON/cachés anteriores que aún contienen character_path.
            legacy_dir = Path(self.char_data.get("character_path", ""))
            expected_json = legacy_dir / f"__{self.char_data.get('name', '')}__.json"
            if expected_json.is_file():
                self.initial_character_json_path = expected_json
            else:
                legacy_jsons = sorted(legacy_dir.glob("__*.json")) if legacy_dir.is_dir() else []
                self.initial_character_json_path = legacy_jsons[0] if legacy_jsons else expected_json

        self.initial_character_path = self.initial_character_json_path.parent
        # Los nombres de carpeta contienen metadatos históricos y nunca se recalculan
        # ni se renombran desde este diálogo.
        self.current_character_path = self.initial_character_path

        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        # Scroll area para los campos por si la ventana se hace pequeña
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        scroll_content = QWidget()
        scroll_layout = QGridLayout(scroll_content)
        scroll_layout.setContentsMargins(5, 5, 5, 5)
        scroll_layout.setSpacing(10)

        # 1. Year (Readonly)
        scroll_layout.addWidget(QLabel("Año (Year):"), 0, 0)
        self.txt_year = QLineEdit(str(self.char_data.get("year", "")))
        self.txt_year.setReadOnly(True)
        scroll_layout.addWidget(self.txt_year, 0, 1, 1, 2)

        # 2. Name
        scroll_layout.addWidget(QLabel("Nombre (Name):"), 1, 0)
        self.txt_name = QLineEdit(self.char_data.get("name", ""))
        self.txt_name.setReadOnly(True)
        scroll_layout.addWidget(self.txt_name, 1, 1, 1, 2)

        # 3. Alterego
        scroll_layout.addWidget(QLabel("Alterego:"), 2, 0)
        self.txt_alterego = QLineEdit(self.char_data.get("alterego", ""))
        self.txt_alterego.setReadOnly(True)
        scroll_layout.addWidget(self.txt_alterego, 2, 1, 1, 2)

        # 4. Icon Path (QLineEdit + Establecer + Abrir)
        scroll_layout.addWidget(QLabel("Ruta Icono (Icon Path):"), 3, 0)
        self.txt_icon_path = QLineEdit(self.char_data.get("icon_path", ""))
        scroll_layout.addWidget(self.txt_icon_path, 3, 1)

        btn_icon_layout = QHBoxLayout()
        self.btn_set_icon = QPushButton("Establecer")
        self.btn_set_icon.clicked.connect(self.set_icon_file)
        self.btn_open_icon = QPushButton("Abrir")
        self.btn_open_icon.clicked.connect(self.open_icon_file)
        btn_icon_layout.addWidget(self.btn_set_icon)
        btn_icon_layout.addWidget(self.btn_open_icon)
        scroll_layout.addLayout(btn_icon_layout, 3, 2)

        # 5. Background Path (QLineEdit + Establecer + Abrir)
        scroll_layout.addWidget(QLabel("Ruta Fondo (Background Path):"), 4, 0)
        self.txt_bg_path = QLineEdit(self.char_data.get("background_path", ""))
        scroll_layout.addWidget(self.txt_bg_path, 4, 1)

        btn_bg_layout = QHBoxLayout()
        self.btn_set_bg = QPushButton("Establecer")
        self.btn_set_bg.clicked.connect(self.set_bg_file)
        self.btn_open_bg = QPushButton("Abrir")
        self.btn_open_bg.clicked.connect(self.open_bg_file)
        btn_bg_layout.addWidget(self.btn_set_bg)
        btn_bg_layout.addWidget(self.btn_open_bg)
        scroll_layout.addLayout(btn_bg_layout, 4, 2)

        # 6. Type Underwear (QListWidget with checkboxes & Editar lista button)
        scroll_layout.addWidget(QLabel("Ropa Interior (Type Underwear):"), 5, 0)

        underwear_container = QWidget()
        underwear_layout = QVBoxLayout(underwear_container)
        underwear_layout.setContentsMargins(0, 0, 0, 0)
        underwear_layout.setSpacing(5)

        self.list_underwear = QListWidget()
        self.list_underwear.setMaximumHeight(120)
        self.list_underwear.setStyleSheet("""
            QListWidget {
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                color: #ffffff;
            }
            QListWidget::item {
                padding: 4px;
                color: #ffffff;
            }
            QListWidget::item:hover {
                background-color: #3e3e42;
            }
            QListWidget::item:selected {
                background-color: #2d2d2d;
                color: #ffffff;
            }
        """)

        self.btn_edit_underwear_list = QPushButton("Editar lista")
        self.btn_edit_underwear_list.clicked.connect(self.open_underwear_list_editor)

        underwear_layout.addWidget(self.list_underwear)
        underwear_layout.addWidget(self.btn_edit_underwear_list, 0, Qt.AlignmentFlag.AlignLeft)

        scroll_layout.addWidget(underwear_container, 5, 1, 1, 2)

        # Parse current_underwear backward-compatibly
        current_underwear = self.char_data.get("type_underwear", [])
        if isinstance(current_underwear, str):
            self.selected_underwear = [current_underwear] if current_underwear else []
        elif isinstance(current_underwear, list):
            self.selected_underwear = list(current_underwear)
        else:
            self.selected_underwear = []

        self.populate_underwear_list()
        self.list_underwear.itemChanged.connect(self.on_underwear_item_changed)

        # 7. Short Masked Alterego
        scroll_layout.addWidget(QLabel("Short Masked Alterego:"), 6, 0)
        self.txt_short_masked = QLineEdit(self.char_data.get("short_masked_alterego", ""))
        scroll_layout.addWidget(self.txt_short_masked, 6, 1, 1, 2)

        # 8. Color Group
        self.color_options = [
            "", "rojo", "azul", "verde", "amarillo", "naranja", "morado",
            "rosa", "blanco", "negro", "gris", "marrón", "turquesa", "cian",
            "magenta", "arcoiris"
        ]
        scroll_layout.addWidget(QLabel("Grupo Color (Color Group):"), 7, 0)
        self.cb_color_group = QComboBox()
        self.cb_color_group.addItems(self.color_options)
        current_color = self.char_data.get("color_group", "")
        self.cb_color_group.setCurrentText(current_color if current_color in self.color_options else "")
        scroll_layout.addWidget(self.cb_color_group, 7, 1, 1, 2)

        # 9. Secondary Color: comparte las opciones del grupo de color principal.
        scroll_layout.addWidget(QLabel("Color Secundario (Secondary Color):"), 8, 0)
        self.cb_secondary_color = QComboBox()
        self.cb_secondary_color.addItems(self.color_options)
        current_secondary_color = self.char_data.get("secondary_color", "")
        self.cb_secondary_color.setCurrentText(
            current_secondary_color if current_secondary_color in self.color_options else ""
        )
        scroll_layout.addWidget(self.cb_secondary_color, 8, 1, 1, 2)

        # 10. Profession Group
        scroll_layout.addWidget(QLabel("Grupo Profesión (Profession):"), 9, 0)
        self.txt_profession = QLineEdit(self.char_data.get("profession_group", ""))
        scroll_layout.addWidget(self.txt_profession, 9, 1, 1, 2)

        # 11. Time of Year
        scroll_layout.addWidget(QLabel("Tiempo de Año (Time of Year):"), 10, 0)
        self.cb_time_of_year = QComboBox()
        time_options = ["", "invierno", "primavera", "verano", "otoño"]
        self.cb_time_of_year.addItems(time_options)
        current_time = self.char_data.get("time_of_year", "")
        if current_time in time_options:
            self.cb_time_of_year.setCurrentText(current_time)
        else:
            self.cb_time_of_year.setCurrentIndex(0)
        scroll_layout.addWidget(self.cb_time_of_year, 10, 1, 1, 2)

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Los metadatos que definen la carpeta se conservan exclusivamente desde su
        # ubicación real; editar una credencial no cambia el nombre de esa carpeta.

        # Footer Buttons
        footer_layout = QHBoxLayout()

        self.btn_open_credential_location = QPushButton("Abrir ubicacion de credencial")
        self.btn_open_credential_location.clicked.connect(self.open_credential_location)
        footer_layout.addWidget(self.btn_open_credential_location)

        self.btn_open_credential_galleryanuary = QPushButton(
            "Abrir ubicacion de credencial con GalleryAnuary"
        )
        self.btn_open_credential_galleryanuary.clicked.connect(
            self.open_credential_location_with_galleryanuary
        )
        footer_layout.addWidget(self.btn_open_credential_galleryanuary)

        footer_layout.addStretch()

        self.btn_edit_raw = QPushButton("Editar en Crudo")
        self.btn_edit_raw.clicked.connect(self.open_raw_json_editor)
        footer_layout.addWidget(self.btn_edit_raw)

        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self.save_data)
        self.btn_discard = QPushButton("Descartar")
        self.btn_discard.clicked.connect(self.reject)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_discard)
        main_layout.addLayout(footer_layout)

    def populate_underwear_list(self):
        self.list_underwear.blockSignals(True)
        self.list_underwear.clear()

        global_options = load_global_type_underwear()

        # 1. Agregar elementos de la lista global
        for option in global_options:
            item = QListWidgetItem(option)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if option in self.selected_underwear:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, False)  # No es descontinuado
            item.setData(Qt.ItemDataRole.UserRole + 1, option)  # Nombre real
            self.list_underwear.addItem(item)

        # 2. Agregar elementos del personaje que fueron descontinuados (ya no están en la lista global)
        for option in self.selected_underwear:
            if option not in global_options:
                disp_text = f"{option} (Descontinuado)"
                item = QListWidgetItem(disp_text)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked)
                item.setData(Qt.ItemDataRole.UserRole, True)  # Es descontinuado
                item.setData(Qt.ItemDataRole.UserRole + 1, option)  # Nombre real
                self.list_underwear.addItem(item)

        self.list_underwear.blockSignals(False)

    def open_underwear_list_editor(self):
        # Actualizar self.selected_underwear con las selecciones actuales
        self._update_currently_selected_underwear()
        dlg = TypeUnderwearEditorDialog(parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.populate_underwear_list()

    def _update_currently_selected_underwear(self):
        selected = []
        for i in range(self.list_underwear.count()):
            item = self.list_underwear.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                real_name = item.data(Qt.ItemDataRole.UserRole + 1)
                if real_name:
                    selected.append(real_name)
        self.selected_underwear = selected

    def on_underwear_item_changed(self, item):
        is_discontinued = item.data(Qt.ItemDataRole.UserRole)
        if is_discontinued and item.checkState() == Qt.CheckState.Unchecked:
            real_name = item.data(Qt.ItemDataRole.UserRole + 1)
            reply = QMessageBox.question(
                self,
                "Elemento descontinuado",
                f"El elemento '{real_name}' fue descontinuado. Si continúa, se eliminará del personaje.\n¿Desea eliminarlo?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                # Se elimina del personaje
                self.list_underwear.blockSignals(True)
                row = self.list_underwear.row(item)
                self.list_underwear.takeItem(row)
                self.list_underwear.blockSignals(False)
            else:
                # Se conserva el valor
                self.list_underwear.blockSignals(True)
                item.setCheckState(Qt.CheckState.Checked)
                self.list_underwear.blockSignals(False)

        self._update_currently_selected_underwear()

    def _replace_spaces_real_time(self, line_edit):
        text = line_edit.text()
        if " " in text:
            cursor_pos = line_edit.cursorPosition()
            new_text = text.replace(" ", "_")
            line_edit.blockSignals(True)
            line_edit.setText(new_text)
            line_edit.setCursorPosition(cursor_pos)
            line_edit.blockSignals(False)

    # Métodos de ayuda para los selectores y apertura de archivos

    def get_start_directory(self) -> str:
        for char_path in (Path(self.current_character_path), self.initial_character_path):
            if char_path.is_dir():
                return str(char_path)
        return str(Path.cwd())

    def set_icon_file(self):
        start_dir = self.get_start_directory()
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Elegir Icono", start_dir,
            "Imágenes (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;Todos los archivos (*)"
        )
        if filepath:
            selected_path = Path(filepath).resolve()
            relative_path = None
            for char_path in (self.initial_character_path, Path(self.current_character_path)):
                try:
                    relative_path = selected_path.relative_to(char_path.resolve())
                    break
                except ValueError:
                    continue

            if relative_path is not None:
                self.txt_icon_path.setText(relative_path.as_posix())
            else:
                # Los recursos externos se guardan como rutas absolutas.
                self.txt_icon_path.setText(str(selected_path))

    def _open_file_cross_platform(self, path):
        import sys
        import subprocess
        try:
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.call(["open", path])
            else:
                subprocess.call(["xdg-open", path])
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo abrir:\n{e}")

    def open_credential_location(self):
        """Abre la carpeta que contiene el JSON del personaje detectado."""
        credential_dir = self.initial_character_json_path.parent
        if credential_dir.is_dir():
            self._open_file_cross_platform(str(credential_dir.resolve()))
        else:
            QMessageBox.warning(
                self,
                "Advertencia",
                f"No se encontró la ubicación de la credencial:\n{credential_dir}"
            )

    def open_credential_location_with_galleryanuary(self):
        """Solicita abrir la carpeta de la credencial mediante la señal Qt."""
        credential_dir = self.initial_character_json_path.parent
        if not credential_dir.is_dir():
            QMessageBox.warning(
                self,
                "GalleryAnuary",
                f"No se encontró la carpeta de la credencial:\n{credential_dir}"
            )
            return

        self.galleryanuary_requested.emit(str(credential_dir.resolve()))

    def _apply_credential_data_to_form(self, credential_data):
        """Actualiza todos los controles del formulario con el JSON validado."""
        runtime_data = credential_data.copy()
        for metadata_key in ("position", "birthday", "age"):
            if metadata_key in self.original_char_data:
                runtime_data[metadata_key] = self.original_char_data[metadata_key]

        runtime_data["character_json_path"] = str(
            self.initial_character_json_path.resolve()
        )
        self.char_data = runtime_data
        self._raw_data_staged = True

        self.txt_year.setText(str(credential_data["year"]))
        self.txt_name.setText(credential_data["name"])
        self.txt_alterego.setText(credential_data["alterego"])
        self.txt_icon_path.setText(credential_data["icon_path"])
        self.txt_bg_path.setText(credential_data["background_path"])
        self.txt_short_masked.setText(credential_data["short_masked_alterego"])
        self.txt_profession.setText(credential_data["profession_group"])
        self.cb_color_group.setCurrentText(credential_data["color_group"])
        self.cb_secondary_color.setCurrentText(credential_data["secondary_color"])
        self.cb_time_of_year.setCurrentText(credential_data["time_of_year"])

        self.selected_underwear = list(credential_data["type_underwear"])
        self.populate_underwear_list()

    def open_raw_json_editor(self):
        """Edita el JSON y aplica sus valores al formulario sin cerrar el diálogo."""
        credential_file = self.initial_character_json_path

        try:
            if self._raw_data_staged:
                staged_data = {
                    key: value
                    for key, value in self.char_data.items()
                    if key not in {"position", "birthday", "age"}
                }
                initial_text = json.dumps(
                    {"character_data": staged_data},
                    indent=4,
                    ensure_ascii=False
                )
            elif credential_file.is_file():
                initial_text = credential_file.read_text(encoding="utf-8")
            else:
                initial_text = json.dumps(
                    {"character_data": self.char_data},
                    indent=4,
                    ensure_ascii=False
                )
        except OSError as exc:
            QMessageBox.critical(
                self, "Error", f"No se pudo leer la credencial:\n{exc}"
            )
            return

        string_fields = self.FORM_CREDENTIAL_KEYS - {"year", "type_underwear"}
        while True:
            editor = RawJSONEditorDialog(initial_text, parent=self)
            if editor.exec() != QDialog.DialogCode.Accepted:
                return

            raw_data = editor.json_data
            if not isinstance(raw_data, dict) or not isinstance(
                raw_data.get("character_data"), dict
            ):
                QMessageBox.warning(
                    self,
                    "JSON inválido para credenciales",
                    "La raíz debe contener un objeto 'character_data'. "
                    "El JSON se devolverá al editor para corregirlo."
                )
                initial_text = editor.editor.toPlainText()
                continue

            credential_data = raw_data["character_data"]
            # Estos valores pertenecen al nombre de la carpeta, no a la credencial.
            for deprecated_field in ("position", "birthday", "age", "character_path"):
                credential_data.pop(deprecated_field, None)

            missing_keys = self.FORM_CREDENTIAL_KEYS - set(credential_data)
            unknown_keys = set(credential_data) - self.FORM_CREDENTIAL_KEYS
            extra_root_keys = set(raw_data) - {"character_data"}

            if missing_keys or unknown_keys or extra_root_keys:
                details = []
                if missing_keys:
                    details.append(
                        "Llaves faltantes: " + ", ".join(sorted(missing_keys))
                    )
                if unknown_keys:
                    details.append(
                        "Llaves que no corresponden al formulario: "
                        + ", ".join(sorted(unknown_keys))
                    )
                if extra_root_keys:
                    details.append(
                        "Llaves adicionales en la raíz: "
                        + ", ".join(sorted(extra_root_keys))
                    )
                QMessageBox.warning(
                    self,
                    "Credencial incompleta o incompatible",
                    "\n".join(details)
                    + "\n\nEl documento se devolverá al editor. "
                    "Corrige las llaves para que coincidan con el formulario."
                )
                initial_text = json.dumps(
                    raw_data,
                    indent=4,
                    ensure_ascii=False
                )
                continue

            invalid_fields = []
            for field in string_fields:
                if not isinstance(credential_data[field], str):
                    invalid_fields.append(field)

            try:
                credential_data["year"] = int(credential_data["year"])
            except (TypeError, ValueError):
                invalid_fields.append("year")

            underwear = credential_data["type_underwear"]
            if not isinstance(underwear, list) or any(
                not isinstance(item, str) for item in underwear
            ):
                invalid_fields.append("type_underwear")

            if credential_data["color_group"] not in self.color_options:
                invalid_fields.append("color_group")
            if credential_data["secondary_color"] not in self.color_options:
                invalid_fields.append("secondary_color")
            if credential_data["time_of_year"] not in (
                "", "invierno", "primavera", "verano", "otoño"
            ):
                invalid_fields.append("time_of_year")

            if invalid_fields:
                QMessageBox.warning(
                    self,
                    "Tipos de datos incompatibles",
                    "Corrige estos campos en el JSON: "
                    + ", ".join(sorted(set(invalid_fields)))
                )
                initial_text = json.dumps(
                    raw_data,
                    indent=4,
                    ensure_ascii=False
                )
                continue

            # La ruta pertenece al archivo real y no puede modificarse desde el JSON.
            credential_data["character_json_path"] = str(credential_file.resolve())
            self._apply_credential_data_to_form(credential_data)
            return

    def _resolve_asset_path(self, raw_path):
        asset_path = Path(raw_path).expanduser()
        if asset_path.is_absolute():
            return asset_path

        current_candidate = Path(self.current_character_path) / asset_path
        if current_candidate.exists():
            return current_candidate

        # Antes de guardar, los recursos relativos siguen físicamente en la
        # carpeta original, incluso cuando el nombre nuevo aún no existe.
        return self.initial_character_path / asset_path

    def _serialize_asset_path(self, raw_path):
        """Mantiene relativa la ruta de recursos dentro de la carpeta original."""
        raw_path = str(raw_path).strip()
        if not raw_path:
            return ""

        asset_path = Path(raw_path).expanduser()
        if not asset_path.is_absolute():
            return raw_path

        try:
            return asset_path.resolve().relative_to(self.initial_character_path.resolve()).as_posix()
        except ValueError:
            # Los recursos externos deben conservar su ruta absoluta.
            return str(asset_path.resolve())

    def open_icon_file(self):
        icon_path = self.txt_icon_path.text().strip()
        full_path = self._resolve_asset_path(icon_path) if icon_path else Path()
        if full_path.is_file():
            self._open_file_cross_platform(str(full_path.resolve()))
        else:
            QMessageBox.warning(self, "Advertencia", f"El archivo no existe:\n{full_path}")

    def set_bg_file(self):
        start_dir = self.get_start_directory()
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Elegir Fondo", start_dir,
            "Imágenes (*.png *.jpg *.jpeg *.webp *.gif *.bmp);;Todos los archivos (*)"
        )
        if filepath:
            selected_path = Path(filepath).resolve()
            relative_path = None
            for char_path in (self.initial_character_path, Path(self.current_character_path)):
                try:
                    relative_path = selected_path.relative_to(char_path.resolve())
                    break
                except ValueError:
                    continue

            if relative_path is not None:
                self.txt_bg_path.setText(relative_path.as_posix())
            else:
                self.txt_bg_path.setText(str(selected_path))

    def open_bg_file(self):
        bg_path = self.txt_bg_path.text().strip()
        full_path = self._resolve_asset_path(bg_path) if bg_path else Path()
        if full_path.is_file():
            self._open_file_cross_platform(str(full_path.resolve()))
        else:
            QMessageBox.warning(self, "Advertencia", f"El archivo no existe:\n{full_path}")

    def open_char_dir(self):
        char_path = Path(self.current_character_path)
        if char_path.is_dir():
            self._open_file_cross_platform(str(char_path.resolve()))
        else:
            QMessageBox.warning(self, "Advertencia", "La carpeta de personaje no existe o está vacía.")

    def save_data(self):
        try:
            new_name = self.txt_name.text().strip()
            if not new_name:
                QMessageBox.warning(self, "Validación", "El campo Nombre (Name) es obligatorio.")
                return

            original_json_path_str = self.original_char_data.get("character_json_path", "")
            original_json_file = (
                Path(original_json_path_str)
                if original_json_path_str
                else self.initial_character_json_path
            )
            original_char_path = original_json_file.parent

            if not original_char_path.is_dir() or not original_json_file.is_file():
                QMessageBox.warning(
                    self,
                    "Validación",
                    f"No se encontró la credencial original:\n{original_json_file}"
                )
                return

            new_json_file = original_char_path / f"__{new_name}__.json"
            if new_json_file.exists() and new_json_file.resolve() != original_json_file.resolve():
                QMessageBox.warning(self, "Validación", f"La credencial destino ya existe:\n{new_json_file}")
                return

            # Recolectar ropa interior seleccionada.
            self._update_currently_selected_underwear()

            # Los tres metadatos de carpeta no pertenecen al JSON de credenciales.
            # La ubicación de la carpeta original se conserva aunque cambie el nombre visible.
            credential_data = {
                "year": int(self.txt_year.text().strip()),
                "name": new_name,
                "alterego": self.txt_alterego.text().strip(),
                "icon_path": self._serialize_asset_path(self.txt_icon_path.text()),
                "background_path": self._serialize_asset_path(self.txt_bg_path.text()),
                "type_underwear": self.selected_underwear,
                "short_masked_alterego": self.txt_short_masked.text().strip(),
                "character_json_path": str(new_json_file.resolve()),
                "color_group": self.cb_color_group.currentText(),
                "secondary_color": self.cb_secondary_color.currentText(),
                "profession_group": self.txt_profession.text().strip(),
                "time_of_year": self.cb_time_of_year.currentText()
            }

            # Conservar datos estructurales solo en memoria para orden y representación.
            runtime_data = credential_data.copy()
            for metadata_key in ("position", "birthday", "age"):
                if metadata_key in self.original_char_data:
                    runtime_data[metadata_key] = self.original_char_data[metadata_key]

            with new_json_file.open("w", encoding="utf-8") as json_file:
                json.dump({"character_data": credential_data}, json_file, indent=4, ensure_ascii=False)
                json_file.write("\n")

            # Si cambió el nombre, sustituir solamente el nombre del archivo JSON.
            # La carpeta del personaje nunca se renombra.
            if original_json_file.resolve() != new_json_file.resolve():
                try:
                    original_json_file.unlink()
                except OSError as exc:
                    print(f"Advertencia eliminando JSON anterior: {exc}")

            self.char_data = runtime_data
            self.saved = True
            self.accept()

        except Exception as exc:
            tb = traceback.format_exc()
            QMessageBox.critical(
                self,
                "Error al Guardar",
                f"Ocurrió un error guardando el personaje:\n{exc}\n\nDetalles:\n{tb}"
            )
