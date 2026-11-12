import os
import datetime
import traceback
from pathlib import Path

from .const import (
    APP_NAME, DEST_BASIC, BASE_DIR, PROJECT_ROOT, ICON_PATH,
    DEST_FOLDER, FORMATS, OTHER_OPTION,
    CONTACT_FIELDS
)

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QTextEdit, QPushButton, QLabel,
    QComboBox, QHBoxLayout, QRadioButton, QLineEdit, QMessageBox, 
    QButtonGroup, QStyle, QCheckBox, 
    QFormLayout, QSizePolicy, QGroupBox
)
from PyQt6.QtGui import QIcon, QKeySequence, QFont
from PyQt6.QtCore import Qt, QSettings, QSize

from .utils import safe_filename, formatted_timestamp_for_filename, ensure_dir, formatted_timestamp_for_filecontent
from .years_selector import YearsTableWidget
from .signature_dlg import load_contacts_db, ContactsManagerDialog, load_classifications_db, ClassificationsManagerDialog

try:
    from docx import Document
except Exception as e:
    Document = None


class KnowledgeEtudeWindow(QWidget):
    def __init__(self, settings: QSettings, tray, base_dir=None):
        super().__init__()
        self.settings = settings
        self.tray = tray
        self.base_dir = os.fspath(base_dir if base_dir is not None else BASE_DIR)
        self.setWindowIcon(QIcon(ICON_PATH))
        self.setWindowTitle(f"Escribe una nota")
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowMinimizeButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )
        self.setMinimumSize(720, 700)
        self.setMaximumSize(950, 850)
        self.setup_ui()
        self.load_settings()

    def _create_icon_button(self, theme_name: str, fallback, tooltip: str, callback):
        icon = QIcon.fromTheme(theme_name)
        if icon.isNull():
            icon = self.style().standardIcon(fallback)

        button = QPushButton()
        button.setIcon(icon)
        button.setIconSize(QSize(18, 18))
        button.setFixedSize(32, 30)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.clicked.connect(callback)
        return button

    def _update_metadata_toggle_button(self, visible: bool):
        pixmap = (
            QStyle.StandardPixmap.SP_ArrowUp
            if visible else QStyle.StandardPixmap.SP_ArrowDown
        )
        self.toggle_meta_btn.setIcon(self.style().standardIcon(pixmap))
        self.toggle_meta_btn.setToolTip(
            "Ocultar campos de autor" if visible else "Mostrar campos de autor"
        )

    def setup_ui(self):
        main_layout = QVBoxLayout()

        # --- Acciones superiores: controles compactos con icono y tooltip.
        header_layout = QHBoxLayout()

        paste_btn = self._create_icon_button(
            "edit-paste",
            QStyle.StandardPixmap.SP_FileIcon,
            "Pegar (Ctrl+V)",
            self.on_paste,
        )
        paste_btn.setShortcut(QKeySequence("Ctrl+V"))
        header_layout.addWidget(paste_btn)
        header_layout.addStretch()

        clear_author_fields_btn = QPushButton("Limpiar campos de autor")
        clear_author_fields_btn.setFixedHeight(30)
        clear_author_fields_btn.clicked.connect(self.clear_author_fields)
        header_layout.addWidget(clear_author_fields_btn)

        manage_contacts_btn = self._create_icon_button(
            "preferences-system-contacts",
            QStyle.StandardPixmap.SP_FileDialogDetailedView,
            "Gestionar Contactos",
            self.open_contacts_manager,
        )
        header_layout.addWidget(manage_contacts_btn)

        self.toggle_meta_btn = QPushButton()
        self.toggle_meta_btn.setFixedSize(32, 30)
        self.toggle_meta_btn.setIconSize(QSize(18, 18))
        self.toggle_meta_btn.clicked.connect(self.toggle_metadata)
        self._update_metadata_toggle_button(False)
        header_layout.addWidget(self.toggle_meta_btn)

        main_layout.addLayout(header_layout)

        # --- Contenedor único para el formulario y el cuerpo del mensaje.
        content_layout = QHBoxLayout()
        
         # --- Selector de años en cuadrícula, situado a la derecha.
        year_layout = QVBoxLayout()
        year_layout.setContentsMargins(0, 0, 0, 0)
        year_layout.addWidget(QLabel("Año"), 0, Qt.AlignmentFlag.AlignHCenter)

        current_year = datetime.datetime.now().year
        years = list(range(current_year, 2003, -1))[::-1]
        self.year_selector = YearsTableWidget(
            years, selected_year=current_year, parent=self
        )
        self.year_selector.setFixedWidth(100)
        year_rows = (len(years) + 1) // 2
        self.year_selector.setFixedHeight(year_rows * 28 + 6)
        year_layout.addWidget(self.year_selector, 0, Qt.AlignmentFlag.AlignTop)
        year_layout.addStretch()
        content_layout.addLayout(year_layout)
        
        # --- Contenedor de la nota (movido a la derecha con estiramiento).
        self.note_container = QGroupBox("Contenido de la nota")
        note_layout = QVBoxLayout(self.note_container)
        note_layout.setContentsMargins(10, 12, 10, 10)
        note_layout.setSpacing(8)

        # --- Metadatos del autor (sección plegable).
        self.metadata_fields = {}
        self.contacts_db = load_contacts_db()

        metadata_form = QFormLayout()
        metadata_form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        metadata_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        self.from_input = QLineEdit()
        self.from_input.setPlaceholderText("Nombre de quien escribe")
        metadata_form.addRow("Escrito por (De):", self.from_input)

        for key, label, list_key in CONTACT_FIELDS:
            container = self.create_contact_row(key, list_key)
            metadata_form.addRow(label, container)

        self.subject_input = QLineEdit()
        self.subject_input.setPlaceholderText("Asunto de la nota")
        metadata_form.addRow("Asunto:", self.subject_input)

        self.metadata_container = QWidget()
        self.metadata_container.setLayout(metadata_form)
        self.metadata_container.setVisible(False)
        note_layout.addWidget(self.metadata_container)
        

        # --- Formulario principal: clasificación, formato, nombre y nombre final.
        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)

        self.class_combo = QComboBox()
        self.class_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        classification_row = QWidget()
        classification_layout = QHBoxLayout(classification_row)
        classification_layout.setContentsMargins(0, 0, 0, 0)
        classification_layout.setSpacing(6)
        classification_layout.addWidget(self.class_combo, 1)

        manage_class_btn = self._create_icon_button(
            "view-list-details",
            QStyle.StandardPixmap.SP_FileDialogListView,
            "Gestionar Clasificaciones",
            self.open_classifications_manager,
        )
        classification_layout.addWidget(manage_class_btn)
        form_layout.addRow("Clasificación:", classification_row)
        
        
        # --- Selector de personajes (condicional para {character_selection}) ---
        self.character_combo = QComboBox()
        self.character_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.character_combo.setEnabled(False)

        self.character_row_widget = QWidget()
        char_layout = QHBoxLayout(self.character_row_widget)
        char_layout.setContentsMargins(0, 0, 0, 0)
        char_layout.setSpacing(6)
        char_layout.addWidget(self.character_combo, 1)

        form_layout.addRow("Personaje:", self.character_row_widget)
        self.character_row_widget.setVisible(False)
        
        self.class_combo.currentIndexChanged.connect(self.check_character_mode)
        self.year_selector.yearChanged.connect(lambda *_: self.check_character_mode())
        
        
        # --- Selector de formato ---
        self.type_group = QButtonGroup(self)
        format_row = QWidget()
        format_layout = QHBoxLayout(format_row)
        format_layout.setContentsMargins(0, 0, 0, 0)
        format_layout.setSpacing(8)

        for fmt in FORMATS:
            label = "Otro" if fmt == "other" else fmt
            radio = QRadioButton(label)
            radio.setProperty("format_code", fmt)
            self.type_group.addButton(radio)
            format_layout.addWidget(radio)
            if fmt == "txt":
                radio.setChecked(True)

        self.other_ext_input = QLineEdit()
        self.other_ext_input.setPlaceholderText("Extensión (ej. rtf)")
        self.other_ext_input.setMaximumWidth(120)
        self.other_ext_input.setVisible(False)
        format_layout.addWidget(self.other_ext_input)
        format_layout.addStretch()
        
        form_layout.addRow("Formato:", format_row)

        for button in self.type_group.buttons():
            button.toggled.connect(self.on_type_toggled)

        self.name_input = QLineEdit()
        self.name_input.setMaxLength(50)
        self.name_input.setPlaceholderText("nombre-personalizado")
        
        self.ext_label = QLabel(".md")
        self.ext_label.setStyleSheet("color: #aaaaaa; font-weight: bold;")
        
        name_row_widget = QWidget()
        name_layout = QHBoxLayout(name_row_widget)
        name_layout.setContentsMargins(0, 0, 0, 0)
        name_layout.setSpacing(4)
        name_layout.addWidget(self.name_input, 1)
        name_layout.addWidget(self.ext_label, 0)
        
        form_layout.addRow("Nombre del archivo:", name_row_widget)

        self.preview_label = QLabel("-")
        self.preview_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        form_layout.addRow("Nombre final:", self.preview_label)

        note_layout.addLayout(form_layout)

        # --- Cuerpo del mensaje: permanece dentro del mismo contenedor.
        self.text_edit = QTextEdit()
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setPlaceholderText("Escribe aquí el cuerpo del mensaje...")
        font = QFont()
        font.setPointSize(13)
        self.text_edit.setFont(font)
        note_layout.addWidget(self.text_edit, 1)

        content_layout.addWidget(self.note_container, 1)

        main_layout.addLayout(content_layout, 1)

        # --- Controles inferiores.
        row_bottom = QHBoxLayout()
        self.always_on_top_cb = QCheckBox("Siempre Visible")
        self.always_on_top_cb.setChecked(True)
        self.always_on_top_cb.toggled.connect(self.on_always_on_top_toggled)
        row_bottom.addWidget(self.always_on_top_cb)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        row_bottom.addStretch()

        save_btn = QPushButton("Guardar (Ctrl+S)")
        save_btn.setFixedHeight(30)
        save_btn.setFixedWidth(110)
        save_btn.clicked.connect(self.on_save)
        save_btn.setShortcut(QKeySequence("Ctrl+S"))
        row_bottom.addWidget(save_btn)

        main_layout.addLayout(row_bottom)

        # --- Conexiones para actualizar el nombre final.
        self.name_input.textChanged.connect(self.update_preview)
        self.class_combo.currentIndexChanged.connect(self.update_preview)
        self.type_group.buttonToggled.connect(lambda *_: self.update_preview())
        self.other_ext_input.textChanged.connect(self.update_preview)
        self.year_selector.yearChanged.connect(lambda *_: self.update_preview())

        self.setLayout(main_layout)
        self.setMinimumSize(720, 700)
        self.populate_contact_combos(preserve_selection=False)
        self.populate_class_combo(preserve_selection=False)
        self.update_preview()

    def clear_author_fields(self):
        """Limpia los campos de metadatos/autor sin modificar el contenido de la nota."""
        self.from_input.clear()
        self.subject_input.clear()

        for field in self.metadata_fields.values():
            field["combo"].setCurrentIndex(0)
            field["line"].clear()
            field["line"].setVisible(False)

        self.update_preview()
        self.metadata_container.setVisible(True)
        self._update_metadata_toggle_button(True)

    def toggle_metadata(self):
        is_visible = self.metadata_container.isVisible()
        self.metadata_container.setVisible(not is_visible)
        
        self._update_metadata_toggle_button(not is_visible)

    def create_contact_row(self, key: str, list_key: str) -> QWidget:
        """
        Crea el contenedor horizontal (QComboBox + QLineEdit oculto) para un campo de
        contacto. El QLineEdit solo se muestra cuando se selecciona 'Otro...', y el
        contenedor se reajusta de forma fluida al cambiar su visibilidad.
        """
        combo = QComboBox()
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumWidth(100)
        line = QLineEdit()
        line.setPlaceholderText("Escribe aquí...")
        line.setVisible(False)

        container = QWidget()
        hbox = QHBoxLayout(container)
        hbox.setContentsMargins(0, 0, 0, 0)
        
        line.setMinimumWidth(300)
        hbox.addWidget(combo, 2)
        hbox.addWidget(line, 1)

        combo.currentTextChanged.connect(
            lambda text, l=line: self.on_contact_combo_changed(text, l)
        )

        self.metadata_fields[key] = {
            "combo": combo, "line": line, "container": container, "list_key": list_key
        }
        return container

    def on_contact_combo_changed(self, text: str, line_edit: QLineEdit):
        line_edit.setVisible(text == OTHER_OPTION)
        if text != OTHER_OPTION:
            line_edit.clear()
        self.update_preview()

    def populate_contact_combos(self, preserve_selection: bool = True):
        """Repuebla todos los combos de contacto desde self.contacts_db."""
        self.contacts_db = load_contacts_db()
        for key, field in self.metadata_fields.items():
            combo = field["combo"]
            previous_text = combo.currentText() if preserve_selection else ""
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("")  # opción vacía / sin selección
            combo.addItems(self.contacts_db.get(field["list_key"], []))
            combo.addItem(OTHER_OPTION)
            idx = combo.findText(previous_text)
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
            field["line"].setVisible(combo.currentText() == OTHER_OPTION)

    def open_contacts_manager(self):
        dialog = ContactsManagerDialog(self)
        dialog.contacts_updated.connect(lambda: self.populate_contact_combos(preserve_selection=True))
        dialog.exec()
        # Por si el diálogo se cerró sin disparar la última señal, refrescamos igual.
        self.populate_contact_combos(preserve_selection=True)

    def populate_class_combo(self, preserve_selection: bool = True):
        """Repuebla self.class_combo desde classifications_db.json."""
        previous_code = self.class_combo.currentData() if preserve_selection else None
        self.classifications_db = load_classifications_db()
        self.class_combo.blockSignals(True)
        self.class_combo.clear()
        for entry in self.classifications_db:
            self.class_combo.addItem(entry["label"], entry["code"])
        if previous_code is not None:
            idx = self.class_combo.findData(previous_code)
            if idx >= 0:
                self.class_combo.setCurrentIndex(idx)
        self.class_combo.blockSignals(False)
        self.update_preview()

    def open_classifications_manager(self):
        dialog = ClassificationsManagerDialog(self)
        dialog.classifications_updated.connect(lambda: self.populate_class_combo(preserve_selection=True))
        dialog.exec()
        # Por si el diálogo se cerró sin disparar la última señal, refrescamos igual.
        self.populate_class_combo(preserve_selection=True)

    def get_contact_field_value(self, key: str) -> str:
        field = self.metadata_fields[key]
        combo_text = field["combo"].currentText()
        if combo_text == OTHER_OPTION:
            return field["line"].text().strip()
        return combo_text.strip()

    def on_type_toggled(self):
        # Show other extension input if 'otro' is selected
        selected = self.get_selected_format()
        self.other_ext_input.setVisible(selected == "other")
        self.update_preview()
        
    def populate_character_combo(self):
        """Llena el combo con las carpetas de personajes que cumplan con el patrón ';' para el año seleccionado."""
        self.character_combo.blockSignals(True)
        self.character_combo.clear()

        year = str(self.year_selector.current_year())
        px = f"{int(year)-2003:02d}"
        knowledge_dir = os.path.join(self.base_dir, year, f"{px}. {DEST_FOLDER}")

        characters = []
        if os.path.exists(knowledge_dir) and os.path.isdir(knowledge_dir):
            try:
                for entry in os.listdir(knowledge_dir):
                    full_path = os.path.join(knowledge_dir, entry)
                    if os.path.isdir(full_path) and ";" in entry:
                        characters.append(entry)
            except Exception:
                traceback.print_exc()

        characters.sort()

        if characters:
            for char_folder in characters:
                self.character_combo.addItem(char_folder, char_folder)
            self.character_combo.setEnabled(True)
        else:
            self.character_combo.addItem("(Vacío - No hay carpetas de personajes)")
            self.character_combo.setEnabled(False)

        self.character_combo.blockSignals(False)
        self.update_preview()

    def check_character_mode(self):
        """Mantiene visible el selector de personajes; lo habilita y carga carpetas solo si usa {character_selection}."""
        cls_code = self.class_combo.currentData()
        subfolder = "_basic"
        for entry in getattr(self, "classifications_db", []):
            if entry.get("code") == cls_code:
                subfolder = entry.get("subfolder", "").strip()
                break

        is_character_mode = (subfolder == "{character_selection}")
        
        # El widget siempre está visible
        self.character_row_widget.setVisible(True)

        if is_character_mode:
            self.populate_character_combo()
        else:
            self.character_combo.blockSignals(True)
            self.character_combo.clear()
            self.character_combo.addItem("(No aplica para esta clasificación)")
            self.character_combo.setEnabled(False)
            self.character_combo.blockSignals(False)

        self.update_preview()

    def get_selected_format(self) -> str:
        checked = [b for b in self.type_group.buttons() if b.isChecked()]
        if not checked:
            return "txt"
        return str(checked[0].property("format_code") or checked[0].text())

    def update_preview(self):
        cls_code = self.class_combo.currentData()
        fmt = self.get_selected_format()
        name = safe_filename(self.name_input.text() or "untitled")
        timestamp = formatted_timestamp_for_filename(datetime.datetime.now())
        if fmt == "other":
            ext = self.other_ext_input.text().strip().lstrip(".") or "txt"
        else:
            ext = fmt
        self.ext_label.setText(f".{ext}")
        preview = f"{cls_code}_{timestamp}_{name}.{ext}"
        self.preview_label.setText(preview)

    def on_paste(self):
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        if text:
            self.text_edit.setPlainText(text)
        else:
            QMessageBox.information(self, "Pegar", "El portapapeles no contiene texto.")

    def on_always_on_top_toggled(self, checked: bool):
        # Cambia la bandera de la ventana para mantenerse arriba
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, checked)
        # aplicar cambio
        self.show()

    def load_settings(self):
        geometry = self.settings.value("window_geometry")
        if geometry:
            self.restoreGeometry(geometry)
        if self.settings.value("is_maximized", False, type=bool):
            self.showMaximized()

        last_year = self.settings.value("last_year", "")
        if last_year:
            self.year_selector.set_current_year(last_year)
        last_class = self.settings.value("last_class", "")
        if last_class:
            for i in range(self.class_combo.count()):
                if self.class_combo.itemData(i) == last_class:
                    self.class_combo.setCurrentIndex(i)
                    break
        last_format = self.settings.value("last_format", "txt")
        for btn in self.type_group.buttons():
            if (
                btn.property("format_code") == last_format
                or btn.text() == last_format
            ):
                btn.setChecked(True)
        last_name = self.settings.value("last_name", "")
        if last_name:
            self.name_input.setText(last_name)
        last_other_ext = self.settings.value("last_other_ext", "")
        if last_other_ext:
            self.other_ext_input.setText(last_other_ext)

        last_from = self.settings.value("last_from", "")
        if last_from:
            self.from_input.setText(last_from)

        last_subject = self.settings.value("last_subject", "")
        if last_subject:
            self.subject_input.setText(last_subject)

        for key, field in self.metadata_fields.items():
            combo = field["combo"]
            line = field["line"]
            saved_combo_text = self.settings.value(f"last_{key}_combo", "")
            saved_line_text = self.settings.value(f"last_{key}_line", "")
            if saved_combo_text:
                idx = combo.findText(saved_combo_text)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                    if saved_combo_text == OTHER_OPTION and saved_line_text:
                        line.setText(saved_line_text)

        self.check_character_mode()
        self.update_preview()

    def save_settings(self):
        self.settings.setValue("window_geometry", self.saveGeometry())
        self.settings.setValue("is_maximized", self.isMaximized())

        self.settings.setValue("last_year", str(self.year_selector.current_year()))
        self.settings.setValue("last_class", self.class_combo.currentData())
        self.settings.setValue("last_format", self.get_selected_format())
        self.settings.setValue("last_name", self.name_input.text())
        self.settings.setValue("last_other_ext", self.other_ext_input.text())

        self.settings.setValue("last_from", self.from_input.text())
        self.settings.setValue("last_subject", self.subject_input.text())
        for key, field in self.metadata_fields.items():
            self.settings.setValue(f"last_{key}_combo", field["combo"].currentText())
            self.settings.setValue(f"last_{key}_line", field["line"].text())

    def validate_before_save(self, text: str, name: str) -> tuple[bool, str]:
        if not text.strip():
            return False, "La nota está vacía. No se puede guardar."
        safe_name = safe_filename(name)
        if not safe_name:
            return False, "Debes proporcionar un nombre válido para el archivo."
        return True, safe_name

    def build_metadata_header(self, now: datetime.datetime) -> str:
        """
        Construye el encabezado estructurado con fecha/hora de creación y todos los
        campos de metadatos, omitiendo los que estén vacíos.
        """
        lines = [f"Fecha y hora de creación: {formatted_timestamp_for_filecontent(now)}"]

        from_val = self.from_input.text().strip()
        if from_val:
            lines.append(f"Escrito por (De): {from_val}")

        for key, label, _list_key in CONTACT_FIELDS:
            value = self.get_contact_field_value(key)
            if value:
                lines.append(f"{label.rstrip(':')}: {value}")

        subject_val = self.subject_input.text().strip()
        if subject_val:
            lines.append(f"Asunto: {subject_val}")

        return "\n".join(lines)

    def on_save(self):
        try:
            text = self.text_edit.toPlainText()
            name_input = self.name_input.text()
            ok, safe_name_or_msg = self.validate_before_save(text, name_input)
            if not ok:
                QMessageBox.warning(self, "Error al guardar", safe_name_or_msg)
                return
            safe_name = safe_name_or_msg
            year = str(self.year_selector.current_year())
            cls_code = self.class_combo.currentData()
            
            # Obtener subfolder de la clasificación seleccionada
            subfolder = "_basic"
            for entry in getattr(self, "classifications_db", []):
                if entry.get("code") == cls_code:
                    sf = entry.get("subfolder", "").strip()
                    if sf:
                        subfolder = sf
                    break

            fmt = self.get_selected_format()
            ext = fmt
            if fmt == "other":
                ext = self.other_ext_input.text().strip().lstrip(".") or "txt"
            
            # Timestamp for filename and file content
            now = datetime.datetime.now()
            filename_ts = formatted_timestamp_for_filename(now)
            filename = f"{cls_code}_{filename_ts}_{safe_name}.{ext}"
            
            px = f"{int(year)-2003:02d}"
            
            # Directorio de destino según subcarpeta o personaje
            if subfolder == "{character_selection}":
                char_name = self.character_combo.currentData() or self.character_combo.currentText()
                if not char_name or "Vacío" in char_name or not self.character_combo.isEnabled():
                    QMessageBox.warning(
                        self, "Personaje requerido",
                        "Debes seleccionar una carpeta de personaje válida para guardar esta nota."
                    )
                    return
                dest_dir = os.path.join(self.base_dir, year, f"{px}. {DEST_FOLDER}", char_name)
            else:
                dest_dir = os.path.join(self.base_dir, year, f"{px}. {DEST_FOLDER}", f"{px}. {subfolder}")

            ensure_dir(dest_dir)
            dest_path = os.path.join(dest_dir, filename)

            if os.path.exists(dest_path):
                QMessageBox.warning(
                    self, "Archivo existente",
                    "Un archivo con ese nombre ya existe. Cambia el nombre personalizado."
                )
                return

            # Encabezado estructurado con metadatos + línea divisoria
            header = self.build_metadata_header(now)
            divider = "-" * 40

            # Save according to extension
            if ext.lower() == "docx":
                if Document is None:
                    QMessageBox.critical(self, "Dependencia faltante",
                                         "python-docx no está instalado. Instálalo con: pip install python-docx")
                    return
                template_path = PROJECT_ROOT / "assets" / "template.docx"
                doc = Document(str(template_path)) if template_path.is_file() else Document()
                header_lines = header.split("\n")
                p = doc.paragraphs[0]
                p.clear()
                p.text = header_lines[0]
                for line in header_lines[1:]:
                    doc.add_paragraph(line)
                doc.add_paragraph(divider)
                doc.add_paragraph(text)
                doc.save(dest_path)
            else:
                with open(dest_path, "w", encoding="utf-8") as f:
                    f.write(header + "\n" + divider + "\n\n")
                    f.write(text)

            # Guardar settings
            self.settings.setValue("last_saved_path", dest_path)
            self.save_settings()

            self.hide()
            self.text_edit.clear()

            self.tray.show_message("Nota guardada", f"{os.path.basename(dest_path)}\nGuardada en: {dest_dir}")
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Error al guardar: {e}")
            
    def showEvent(self, event):
        super().showEvent(event)
        # Forzar un refresh y recalculo del layout al mostrar la ventana
        if self.layout():
            self.layout().activate()
        self.update()

    def closeEvent(self, event):
        """
        Al pulsar la X:
        - no cerrar el proceso
        - solo ocultar la ventana (minimizar a la bandeja)
        """
        event.ignore()
        self.hide()