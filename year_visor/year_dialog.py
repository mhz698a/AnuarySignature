# domain_visor/year_dialog.py

import os
import json
import traceback
import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QListWidget, QListWidgetItem, QWidget,
    QTreeView, QAbstractItemView, QMenu
)
from PyQt6.QtCore import Qt, QDir, QModelIndex, QUrl, QPoint, pyqtSignal
from PyQt6.QtGui import QFileSystemModel, QDesktopServices, QAction
from domain_visor.theme import Theme
from character_visor.character_manager import CharacterManager
from year_visor.year_creator import validate_date_constraints

def calculate_id_package_default(year: int, infra_path: Path = None) -> str:
    """
    Calcula el ID de paquete por defecto basado en las reglas:
    - Primeros dos caracteres del último nombre del superdominio en mayúsculas.
    - "-"
    - Número del dominio dentro del superdominio en dos dígitos.
    - "-"
    - prefix en dos dígitos: {max(0, year - 2003):02d}
    - "-"
    - "00A" al ser default variant key (se pone por defecto)
    """
    if infra_path is None:
        infra_path = Path("__structure__/infrastructure.json")
    if not infra_path.exists():
        return ""
    try:
        with open(infra_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return ""

    for sd_data in data:
        sd_name = sd_data.get("superdomain", "").strip()
        for idx, domain_data in enumerate(sd_data.get("domains", [])):
            range_text = domain_data.get("range", "")
            try:
                start_year, end_year = map(int, range_text.split("-"))
            except Exception:
                continue
            if start_year <= year <= end_year:
                # 1. Prefijo del superdominio: primeros dos caracteres del último nombre
                parts = [p for p in sd_name.split("_") if p]
                last_part = parts[-1] if parts else ""
                sd_prefix = last_part[:2].upper()

                # 2. Número del dominio dentro del superdominio (1-based index) en dos dígitos
                domain_index = idx + 1
                dom_index_str = f"{domain_index:02d}"

                # 3. Prefix en dos dígitos
                prefix_str = f"{max(0, year - 2003):02d}"

                # 4. Combinar con default variant key "00A"
                return f"{sd_prefix}-{dom_index_str}-{prefix_str}-00A"
    return ""


def find_season_name(year: int, base_path: Path) -> str:
    """
    Busca dentro del año una carpeta que contenga "___".
    Remueve "___[" y "]" si están presentes para que no salgan visualmente en season_name.
    """
    year_dir = base_path / str(year)
    if not year_dir.exists():
        return ""
    try:
        for item in year_dir.iterdir():
            if item.is_dir() and "___" in item.name:
                name = item.name
                # Limpieza de "___[" y "]" para season_name
                name = name.replace("___[", "").replace("]", "")
                return name
    except Exception:
        pass
    return ""


class FolderCreateDialog(QDialog):
    """
    Diálogo para crear una nueva carpeta con estilo oscuro.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.folder_name = ""
        self.setWindowTitle("Crear carpeta")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.resize(500, 150)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 12px;
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 12px;
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
                font-family: Arial;
                font-size: 11px;
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

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        info_label = QLabel("Nombre de la nueva carpeta:")
        layout.addWidget(info_label)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ejemplo: nueva_carpeta")
        layout.addWidget(self.txt_name)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("Aceptar")
        self.btn_save.clicked.connect(self.on_accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def on_accept(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Advertencia", "El nombre de la carpeta no puede estar vacío.")
            return
        self.folder_name = name
        self.accept()


class FolderRenameDialog(QDialog):
    """
    Diálogo para renombrar una carpeta con estilo oscuro.
    """
    def __init__(self, current_name, parent=None):
        super().__init__(parent)
        self.folder_name = ""
        self.setWindowTitle("Renombrar carpeta")
        self.setModal(True)
        self.setMinimumWidth(500)
        self.resize(500, 150)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self.setStyleSheet(f"""
            QDialog {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 12px;
                font-weight: bold;
            }}
            QLineEdit {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: {Theme.TEXT_WHITE};
                font-family: Arial;
                font-size: 12px;
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
                font-family: Arial;
                font-size: 11px;
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
        self.current_name = current_name
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        info_label = QLabel("Nuevo nombre de la carpeta:")
        layout.addWidget(info_label)

        self.txt_name = QLineEdit(self.current_name)
        layout.addWidget(self.txt_name)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("Aceptar")
        self.btn_save.clicked.connect(self.on_accept)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def on_accept(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Advertencia", "El nombre de la carpeta no puede estar vacío.")
            return
        self.folder_name = name
        self.accept()


class YearDialog(QDialog):
    """
    Diálogo de Año ("Year Dialog") para visualizar y editar la estructura de identidad del año.
    """

    galleryanuary_requested = pyqtSignal(str)

    def __init__(self, year_value: int, parent=None, base_path=None):
        super().__init__(parent)
        self.year_value = year_value
        self.saved = False

        # Configurar gestor de personajes para obtener la ruta base
        self.char_manager = CharacterManager()
        self.base_path = Path(base_path) if base_path else self.char_manager.base_path

        self.setWindowTitle(f"Year Dialog - {self.year_value}")
        self.setModal(True)
        self.setMinimumWidth(760)
        self.resize(900, 500)

        # Quitar botón de ayuda
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Aplicar estilos oscuros del Theme
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
            QLineEdit {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 5px;
                color: {Theme.TEXT_WHITE};
            }}
            QLineEdit:focus {{
                border-color: #85c1e9;
            }}
            QLineEdit[readOnly="true"] {{
                background-color: #1e1e1e;
                color: #888888;
                border-color: #333333;
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
            QListWidget {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                color: #ffffff;
            }}
            QListWidget::item {{
                padding: 4px;
                color: #ffffff;
            }}
            QListWidget::item:hover {{
                background-color: #3e3e42;
            }}
            QListWidget::item:selected {{
                background-color: #3e3e42;
                color: #ffffff;
            }}
            QMenu {{
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3e3e42;
                font-family: Arial;
                font-size: 12px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                background-color: transparent;
            }}
            QMenu::item:selected {{
                background-color: #2d2d2d;
                color: #ffffff;
            }}
        """)

        # Definir rutas del año y del archivo JSON
        self.prefix = f"{max(0, self.year_value - 2003):02d}"
        self.year_dir = self.base_path / str(self.year_value)
        self.identity_dir = self.year_dir / f"{self.prefix}. identity"
        self.json_filename = f"The_ID_Year_{self.year_value}.json"
        self.json_filepath = self.identity_dir / self.json_filename

        # Intentar obtener infra_path del parent si existe
        self.infra_path = None
        if parent and hasattr(parent, "json_path"):
            self.infra_path = Path(parent.json_path)

        # Cargar o inicializar estructura de datos
        self.load_or_create_year_data(self.infra_path)
        self.init_ui()

    def load_or_create_year_data(self, infra_path=None):
        """
        Carga o crea el archivo JSON. Sincroniza campos de sólo lectura.
        """
        # Calcular los campos generados automáticamente
        self.auto_season_name = find_season_name(self.year_value, self.base_path)
        self.auto_id_package_default = calculate_id_package_default(self.year_value, infra_path)

        exists = self.json_filepath.exists()
        loaded_data = {}

        if exists:
            try:
                with open(self.json_filepath, "r", encoding="utf-8") as f:
                    loaded_data = json.load(f)
            except Exception as e:
                print(f"Error cargando archivo {self.json_filepath}: {e}")

        # Estructura interna
        inner_data = loaded_data.get("year_data", {})

        # Crear o actualizar estructura combinando datos cargados y valores autocalculados
        stored_id = inner_data.get("id_package_default", "")
        final_id = self.auto_id_package_default if self.auto_id_package_default else stored_id

        self.year_data = {
            "year": str(self.year_value),
            "prefix": self.prefix,
            "season_name": self.auto_season_name,
            "season_abreviation": inner_data.get("season_abreviation", ""),
            "esentia_name": inner_data.get("esentia_name", ""),
            "id_package_default": final_id, # Generado automáticamente
            "other_id_package_default": inner_data.get("other_id_package_default", [])
        }

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(15, 15, 15, 15)
        main_layout.setSpacing(15)

        content_layout = QHBoxLayout()
        content_layout.setSpacing(15)
        fields_layout = QVBoxLayout()
        fields_layout.setSpacing(15)

        # Grid para campos (usando claves exactas como etiquetas y traduciendo Estación a Temporada)
        grid = QGridLayout()
        grid.setSpacing(10)

        # Row 0: year (Readonly)
        grid.addWidget(QLabel("year:"), 0, 0)
        self.txt_year = QLineEdit(self.year_data["year"])
        self.txt_year.setReadOnly(True)
        grid.addWidget(self.txt_year, 0, 1)

        # Row 1: prefix (Readonly)
        grid.addWidget(QLabel("prefix:"), 1, 0)
        self.txt_prefix = QLineEdit(self.year_data["prefix"])
        self.txt_prefix.setReadOnly(True)
        grid.addWidget(self.txt_prefix, 1, 1)

        # Row 2: season_name (Readonly)
        grid.addWidget(QLabel("season_name:"), 2, 0)
        self.txt_season_name = QLineEdit(self.year_data["season_name"])
        self.txt_season_name.setReadOnly(True)
        grid.addWidget(self.txt_season_name, 2, 1)

        # Row 3: id_package_default (Readonly)
        grid.addWidget(QLabel("id_package_default:"), 3, 0)
        self.txt_id_package_default = QLineEdit(self.year_data["id_package_default"])
        self.txt_id_package_default.setReadOnly(True)
        grid.addWidget(self.txt_id_package_default, 3, 1)

        # Row 4: season_abreviation (Editable)
        grid.addWidget(QLabel("season_abreviation (Abreviación Temporada):"), 4, 0)
        self.txt_season_abreviation = QLineEdit(self.year_data["season_abreviation"])
        grid.addWidget(self.txt_season_abreviation, 4, 1)

        # Row 5: esentia_name (Editable)
        grid.addWidget(QLabel("esentia_name:"), 5, 0)
        self.txt_esentia_name = QLineEdit(self.year_data["esentia_name"])
        grid.addWidget(self.txt_esentia_name, 5, 1)

        fields_layout.addLayout(grid)

        # Otros paquetes ID por defecto
        fields_layout.addWidget(QLabel("other_id_package_default:"))
        
        self.list_other_packages = QListWidget()
        for pkg in self.year_data["other_id_package_default"]:
            self.list_other_packages.addItem(QListWidgetItem(pkg))
        fields_layout.addWidget(self.list_other_packages)

        # Controles para añadir/eliminar paquetes
        add_del_layout = QHBoxLayout()
        self.txt_new_package = QLineEdit()
        self.txt_new_package.setPlaceholderText("Nuevo ID de paquete...")
        self.btn_add_package = QPushButton("Añadir")
        self.btn_add_package.clicked.connect(self.add_package_item)
        self.btn_del_package = QPushButton("Eliminar")
        self.btn_del_package.clicked.connect(self.del_package_item)

        add_del_layout.addWidget(self.txt_new_package)
        add_del_layout.addWidget(self.btn_add_package)
        add_del_layout.addWidget(self.btn_del_package)
        fields_layout.addLayout(add_del_layout)

        content_layout.addLayout(fields_layout, 2)
        content_layout.addWidget(self._create_year_folder_tree(), 1)
        main_layout.addLayout(content_layout)

        # Footer Buttons
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self.save_data)
        self.btn_discard = QPushButton("Descartar")
        self.btn_discard.clicked.connect(self.reject)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_discard)
        main_layout.addLayout(footer_layout)


    def _create_year_folder_tree(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        title = QLabel(f"Carpetas del año {self.year_value}:")
        title.setStyleSheet("color: #85c1e9; font-size: 12px;")
        layout.addWidget(title)

        year_root = str(self.year_dir)

        self.year_folder_model = QFileSystemModel(self)

        # Filtro corregido y más permisivo para carpetas (desactivado)
        # self.year_folder_model.setFilter(
        #     QDir.Filter.Dirs | QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot | QDir.Filter.Readable
        # )

        self.year_folder_tree = QTreeView()
        self.year_folder_tree.setModel(self.year_folder_model)

        # 1. Primero asignamos la ruta base
        self.year_folder_model.setRootPath(year_root)

        # 2. SOLUCIÓN: Forzamos el índice de inmediato sin esperar la señal asíncrona
        root_index = self.year_folder_model.index(year_root)
        self.year_folder_tree.setRootIndex(root_index)

        # 3. Ocultamos las columnas usando el valor por defecto de QFileSystemModel (suele ser 4)
        for column in range(1, 4):
            self.year_folder_tree.hideColumn(column)

        # Mantenemos la señal solo para refrescos o expansiones automáticas futuras
        self.year_folder_model.directoryLoaded.connect(self._refresh_year_folder_root)

        self.year_folder_tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.year_folder_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.year_folder_tree.setHeaderHidden(True)
        self.year_folder_tree.setMinimumWidth(260)
        self.year_folder_tree.doubleClicked.connect(self.open_folder_from_tree)
        self.year_folder_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.year_folder_tree.customContextMenuRequested.connect(self.show_year_folder_context_menu)

        self.year_folder_tree.expanded.connect(self._limit_tree_depth)

        layout.addWidget(self.year_folder_tree)
        return container

    def _limit_tree_depth(self, index: QModelIndex):
        """Evita que el usuario expanda más allá del segundo nivel."""
        if not index.isValid():
            return

        # Calculamos la profundidad subiendo por los padres del índice
        depth = 0
        current_index = index

        # Subimos por el árbol hasta llegar al nodo raíz visible (rootIndex)
        root_index = self.year_folder_tree.rootIndex()
        while current_index.isValid() and current_index != root_index:
            current_index = current_index.parent()
            depth += 1

        # depth == 1: Primer nivel (Carpetas principales dentro del año)
        # depth == 2: Segundo nivel (Subcarpetas)
        # Si depth >= 2, significa que el usuario intentó expandir una subcarpeta del segundo nivel
        if depth >= 2:
            self.year_folder_tree.collapse(index)


    def _refresh_year_folder_root(self, path: str):
        if Path(path) != self.year_dir:
            return

        root_index = self.year_folder_model.index(str(self.year_dir))
        self.year_folder_tree.setRootIndex(root_index)
        self.year_folder_tree.expand(root_index)

        # CORRECCIÓN: Ocultar las columnas excedentes aquí,
        # cuando el modelo ya tiene sus columnas inicializadas.
        for column in range(1, self.year_folder_model.columnCount()):
            self.year_folder_tree.hideColumn(column)

    def show_year_folder_context_menu(self, pos: QPoint):
        index = self.year_folder_tree.indexAt(pos)
        
        menu = QMenu(self.year_folder_tree)
        
        if not index.isValid():
            # Click derecho en espacio en blanco
            create_action = QAction("Crear carpeta", menu)
            create_action.triggered.connect(self.create_new_folder)
            menu.addAction(create_action)
        else:
            if not self.year_folder_model.isDir(index):
                return
            open_action = QAction("Abrir carpeta", menu)
            open_action.triggered.connect(lambda: self.open_folder_from_tree(index))
            menu.addAction(open_action)

            rename_action = QAction("Renombrar", menu)
            rename_action.triggered.connect(lambda: self.rename_folder(index))
            menu.addAction(rename_action)

        menu.exec(self.year_folder_tree.viewport().mapToGlobal(pos))

    def rename_folder(self, index: QModelIndex):
        if not index.isValid():
            return

        # Calcular profundidad
        depth = 0
        curr = index
        root_index = self.year_folder_tree.rootIndex()
        while curr.isValid() and curr != root_index:
            curr = curr.parent()
            depth += 1

        full_name = self.year_folder_model.fileName(index)
        old_path_str = self.year_folder_model.filePath(index)
        old_path = Path(old_path_str)

        if depth == 1:
            # Primer nivel
            prefix = ""
            clean_name = full_name
            if ". " in full_name:
                parts = full_name.split(". ", 1)
                if parts[0].isdigit() and len(parts[0]) == 2:
                    prefix = parts[0]
                    clean_name = parts[1]

            is_season_folder = False
            season_inside = ""
            if clean_name.startswith("___[") and clean_name.endswith("]"):
                is_season_folder = True
                season_inside = clean_name[4:-1]

            initial_dialog_name = season_inside if is_season_folder else clean_name
            dialog = FolderRenameDialog(initial_dialog_name, self)
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.folder_name:
                new_folder_name = dialog.folder_name

                if is_season_folder:
                    # Renombrar solo para el año activo
                    new_clean_name = f"___[{new_folder_name}]"
                    new_full_name = f"{prefix}. {new_clean_name}" if prefix else new_clean_name
                    new_path = old_path.parent / new_full_name
                    
                    if new_path.exists() and new_path.resolve() != old_path.resolve():
                        msg_box = QMessageBox(self)
                        msg_box.setIcon(QMessageBox.Icon.Warning)
                        msg_box.setWindowTitle("Advertencia")
                        msg_box.setText(f"La carpeta destino ya existe:\n{new_path}")
                        msg_box.setStyleSheet(self.styleSheet())
                        msg_box.exec()
                        return
                    
                    try:
                        old_path.rename(new_path)
                    except Exception as e:
                        msg_box = QMessageBox(self)
                        msg_box.setIcon(QMessageBox.Icon.Critical)
                        msg_box.setWindowTitle("Error")
                        msg_box.setText(f"No se pudo renombrar la carpeta:\n{e}")
                        msg_box.setStyleSheet(self.styleSheet())
                        msg_box.exec()
                        return

                    # Actualizar season_name en credencial/identity json y en el campo de texto
                    self.txt_season_name.setText(new_folder_name)
                    self.year_data["season_name"] = new_folder_name
                    self.save_credential_sync()
                else:
                    # Carpeta normal primer nivel
                    # 1. Renombrar / Crear en todos los años desde el primer año de infraestructura hasta el actual
                    first_year = self.char_manager.get_first_infrastructure_year()
                    import datetime
                    current_year = datetime.date.today().year

                    for y in range(first_year, current_year + 1):
                        y_prefix = f"{max(0, y - 2003):02d}"
                        y_dir = self.base_path / str(y)
                        if y_dir.exists():
                            old_y_folder = y_dir / f"{y_prefix}. {clean_name}"
                            new_y_folder = y_dir / f"{y_prefix}. {new_folder_name}"
                            if old_y_folder.exists():
                                if old_y_folder.resolve() != new_y_folder.resolve():
                                    try:
                                        old_y_folder.rename(new_y_folder)
                                    except Exception as e:
                                        print(f"Error renombrando carpeta {old_y_folder} a {new_y_folder}: {e}")
                            else:
                                # Crear nueva carpeta ya que faltaba
                                try:
                                    new_y_folder.mkdir(parents=True, exist_ok=True)
                                except Exception as e:
                                    print(f"Error creando carpeta {new_y_folder}: {e}")

                    # 2. Actualizar folders.json
                    folders_json_path = Path("__structure__/folders.json")
                    if folders_json_path.exists():
                        try:
                            with open(folders_json_path, "r", encoding="utf-8") as f:
                                folders_data = json.load(f)
                            if isinstance(folders_data, dict):
                                if clean_name in folders_data:
                                    sub_list = folders_data.pop(clean_name)
                                    folders_data[new_folder_name] = sub_list
                                else:
                                    folders_data[new_folder_name] = []
                                with open(folders_json_path, "w", encoding="utf-8") as f:
                                    json.dump(folders_data, f, indent=2, ensure_ascii=False)
                        except Exception as e:
                            print(f"Error actualizando folders.json: {e}")
        elif depth == 2:
            # Segundo nivel (subcarpeta)
            dialog = FolderRenameDialog(full_name, self)
            if dialog.exec() == QDialog.DialogCode.Accepted and dialog.folder_name:
                new_folder_name = dialog.folder_name
                new_path = old_path.parent / new_folder_name
                
                if new_path.exists() and new_path.resolve() != old_path.resolve():
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Warning)
                    msg_box.setWindowTitle("Advertencia")
                    msg_box.setText(f"La carpeta destino ya existe:\n{new_path}")
                    msg_box.setStyleSheet(self.styleSheet())
                    msg_box.exec()
                    return
                
                try:
                    old_path.rename(new_path)
                except Exception as e:
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Critical)
                    msg_box.setWindowTitle("Error")
                    msg_box.setText(f"No se pudo renombrar la carpeta:\n{e}")
                    msg_box.setStyleSheet(self.styleSheet())
                    msg_box.exec()

    def save_credential_sync(self):
        try:
            self.identity_dir.mkdir(parents=True, exist_ok=True)
            with open(self.json_filepath, "w", encoding="utf-8") as f:
                json.dump({"year_data": self.year_data}, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando credencial del año sincrónicamente: {e}")

    def create_new_folder(self):
        dialog = FolderCreateDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.folder_name:
            folder_name = dialog.folder_name
            # 1. Verificar si existe en el año activo
            active_prefix = f"{max(0, self.year_value - 2003):02d}"
            active_folder_name = f"{active_prefix}. {folder_name}"
            active_folder_path = self.year_dir / active_folder_name
            
            if active_folder_path.exists():
                msg_box = QMessageBox(self)
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setWindowTitle("Advertencia")
                msg_box.setText(f"La carpeta '{active_folder_name}' ya existe en el año activo {self.year_value}.")
                msg_box.setStyleSheet(self.styleSheet())
                msg_box.exec()
                return

            # 2. Proceder a crear la carpeta en todos los años desde el primer año de infraestructura hasta el actual
            first_year = self.char_manager.get_first_infrastructure_year()
            import datetime
            current_year = datetime.date.today().year
            
            for y in range(first_year, current_year + 1):
                y_prefix = f"{max(0, y - 2003):02d}"
                y_dir = self.base_path / str(y)
                # Asegurar que la raíz del año exista antes de crear la subcarpeta
                if y_dir.exists():
                    target_path = y_dir / f"{y_prefix}. {folder_name}"
                    try:
                        target_path.mkdir(parents=True, exist_ok=True)
                    except Exception as e:
                        print(f"Error creando carpeta {target_path}: {e}")

            # 3. Actualizar folders.json
            folders_json_path = Path("__structure__/folders.json")
            if folders_json_path.exists():
                try:
                    with open(folders_json_path, "r", encoding="utf-8") as f:
                        folders_data = json.load(f)
                    if isinstance(folders_data, dict):
                        if folder_name not in folders_data:
                            folders_data[folder_name] = []
                            with open(folders_json_path, "w", encoding="utf-8") as f:
                                json.dump(folders_data, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    print(f"Error actualizando folders.json: {e}")

    def open_folder_from_tree(self, index: QModelIndex):
        if not index.isValid() or not self.year_folder_model.isDir(index):
            return

        folder_path = Path(self.year_folder_model.filePath(index)).resolve()
        parent_folder_name = folder_path.parent.name.casefold()

        # Una subcarpeta cuyo padre pertenece al álbum se abre en GalleryAnuary.
        if "album" in parent_folder_name:
            self.galleryanuary_requested.emit(str(folder_path))
            return

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder_path)))

    def add_package_item(self):
        text = self.txt_new_package.text().strip()
        if text:
            # Comprobar si ya existe
            exists = False
            for i in range(self.list_other_packages.count()):
                if self.list_other_packages.item(i).text() == text:
                    exists = True
                    break
            if not exists:
                self.list_other_packages.addItem(QListWidgetItem(text))
                self.txt_new_package.clear()
            else:
                QMessageBox.warning(self, "Advertencia", "El ID de paquete ya existe en la lista.")

    def del_package_item(self):
        current_item = self.list_other_packages.currentItem()
        if current_item:
            self.list_other_packages.takeItem(self.list_other_packages.row(current_item))
        else:
            QMessageBox.warning(self, "Advertencia", "Seleccione un elemento de la lista para eliminar.")

    def save_data(self):
        # Evitar guardar/crear la credencial de año en años que aún no ocurren si no existía el archivo
        
        today = datetime.date.today()
        if self.year_value > today.year and not self.json_filepath.exists():
            
            allowed, message = validate_date_constraints(self.year_value)
            if not allowed:
                QMessageBox.warning(self, "Advertencia", f"No se pueden guardar credenciales para un año que aún no ocurre.\n{message}")
                self.reject()
                return

        try:
            # 1. Obtener la lista de otros paquetes
            other_packages = []
            for i in range(self.list_other_packages.count()):
                other_packages.append(self.list_other_packages.item(i).text())

            # 2. Actualizar el diccionario
            self.year_data["season_abreviation"] = self.txt_season_abreviation.text().strip()
            self.year_data["esentia_name"] = self.txt_esentia_name.text().strip()
            self.year_data["other_id_package_default"] = other_packages

            # 3. Asegurar que la carpeta exista
            self.identity_dir.mkdir(parents=True, exist_ok=True)

            # 4. Guardar archivo JSON
            with open(self.json_filepath, "w", encoding="utf-8") as f:
                json.dump({"year_data": self.year_data}, f, indent=4, ensure_ascii=False)

            self.saved = True
            self.accept()
        except Exception as e:
            tb = traceback.format_exc()
            QMessageBox.critical(self, "Error al Guardar", f"No se pudo guardar el archivo JSON:\n{e}\n\nDetalles:\n{tb}")


class ConnectionRenameDialog(QDialog):
    """
    Diálogo para cambiar el nombre de un lazo de conexión con reemplazo de espacios en tiempo real.
    """
    def __init__(self, connection, json_path, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.json_path = json_path
        self.saved = False

        self.setWindowTitle("Cambiar Nombre de Lazo / Conexión")
        self.setModal(True)
        # Tamaño un poco más ancho para ver todo el nombre
        self.setMinimumWidth(550)
        self.resize(600, 180)

        # Quitar botón de ayuda
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Aplicar estilos oscuros del Theme
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
            QLineEdit {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                color: {Theme.TEXT_WHITE};
                font-size: 12px;
            }}
            QLineEdit:focus {{
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

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(12)

        info_label = QLabel(f"Modificando lazo de conexión: {self.connection.from_year} → {self.connection.to_year}")
        info_label.setStyleSheet("color: #85c1e9; font-size: 12px;")
        layout.addWidget(info_label)

        form_layout = QHBoxLayout()
        form_layout.addWidget(QLabel("Nombre del Lazo:"))
        
        self.txt_name = QLineEdit(self.connection.name)
        form_layout.addWidget(self.txt_name)
        layout.addLayout(form_layout)

        # Reemplazar espacios por guión bajo en tiempo real
        self.txt_name.textChanged.connect(self._replace_spaces)

        # Footer Buttons
        footer_layout = QHBoxLayout()
        footer_layout.addStretch()

        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self.save_data)
        self.btn_discard = QPushButton("Descartar")
        self.btn_discard.clicked.connect(self.reject)

        footer_layout.addWidget(self.btn_save)
        footer_layout.addWidget(self.btn_discard)
        layout.addLayout(footer_layout)

    def _replace_spaces(self):
        text = self.txt_name.text()
        if " " in text:
            cursor_pos = self.txt_name.cursorPosition()
            new_text = text.replace(" ", "_")
            self.txt_name.blockSignals(True)
            self.txt_name.setText(new_text)
            self.txt_name.setCursorPosition(cursor_pos)
            self.txt_name.blockSignals(False)

    def save_data(self):
        new_name = self.txt_name.text().strip()
        
        # 1. Cargar infrastructure.json
        try:
            with open(self.json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo leer la infraestructura:\n{e}")
            return

        # 2. Modificar la conexión que corresponde
        found = False
        for sd_data in data:
            for conn_data in sd_data.get("connections", []):
                if conn_data.get("from") == self.connection.from_year and conn_data.get("to") == self.connection.to_year:
                    conn_data["range_name"] = new_name
                    found = True
                    break
            if found:
                break

        if not found:
            QMessageBox.warning(self, "Advertencia", "No se encontró la conexión lógica en el archivo de infraestructura.")
            return

        # 3. Guardar en infrastructure.json
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo guardar la infraestructura:\n{e}")
            return

        self.saved = True
        self.accept()
