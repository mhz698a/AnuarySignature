# domain_visor/year_creator.py

import os
import json
import datetime
from pathlib import Path
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QMessageBox
from PyQt6.QtCore import Qt
from domain_visor.theme import Theme
from year_visor.year_dialog import calculate_id_package_default
from character_visor.character_manager import CharacterManager

class SeasonNameDialog(QDialog):
    """
    Diálogo de entrada ancho y oscuro para ingresar el nombre de la temporada.
    """
    def __init__(self, year: int, parent=None):
        super().__init__(parent)
        self.year = year
        self.season_name = ""
        self.accepted_value = False

        self.setWindowTitle("Nombre de la Temporada")
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

        info_label = QLabel(f"Ingrese el nombre de la temporada para el año {self.year}:")
        layout.addWidget(info_label)

        self.txt_name = QLineEdit()
        self.txt_name.setPlaceholderText("Ejemplo: Estacion de Prueba")
        layout.addWidget(self.txt_name)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self.on_save)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

    def on_save(self):
        name = self.txt_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Advertencia", "El nombre de la temporada no puede estar vacío.")
            return
        self.season_name = name
        self.accepted_value = True
        self.accept()


def validate_date_constraints(clicked_year: int, today_date=None) -> tuple[bool, str]:
    """
    Valida las restricciones de fecha para la creación del nuevo año.
    - El año actual se puede crear en cualquier mes.
    - El próximo año solo se puede crear a partir de diciembre (mes 12).
    - Un año con más de 1 año de distancia no se puede crear.
    - Un año del pasado que no exista no se puede crear.
    """
    if today_date is None:
        today_date = datetime.date.today()

    current_year = today_date.year
    current_month = today_date.month

    if clicked_year < current_year:
        return False, f"No se puede crear una carpeta para el año {clicked_year} ya que es un año anterior. Si hay un error revisela."

    if clicked_year == current_year:
        return True, ""

    if clicked_year == current_year + 1:
        if current_month == 12:
            return True, ""
        else:
            return False, "Este año que intentas acceder aun no ocurre, espera a diciembre de este año para poder crearlo"

    if clicked_year > current_year + 1:
        return False, f"El año {clicked_year} falta mucho para que llegue y no puedes crearlo porque requiere {current_year - 1}"

    return False, "Fecha o año no válido para la creación."


def find_fallback_template_year(base_path: Path, current_year: int) -> int:
    """
    Busca la mejor carpeta de año plantilla en base_path:
    - Primero comprueba current_year.
    - Luego comprueba current_year - 1.
    - Si no, busca el año máximo que exista en base_path.
    """
    if (base_path / str(current_year)).exists():
        return current_year
    if (base_path / str(current_year - 1)).exists():
        return current_year - 1

    existing_years = []
    if base_path.exists():
        for item in base_path.iterdir():
            if item.is_dir() and item.name.isdigit():
                existing_years.append(int(item.name))
    if existing_years:
        return max(existing_years)
    return None


def replicate_structure_from_fallback(template_year_dir: Path, target_year_dir: Path, new_prefix: str, season_name: str):
    """
    Replica la estructura de directorios del año plantilla al año de destino.
    Remueve el prefijo viejo de las carpetas y agrega el nuevo.
    Si la carpeta contiene '___', limpia los corchetes e inserta el season_name.
    """
    target_year_dir.mkdir(parents=True, exist_ok=True)

    for item in template_year_dir.iterdir():
        if item.is_dir():
            dir_name = item.name
            clean_name = dir_name

            if ". " in dir_name:
                parts = dir_name.split(". ", 1)
                if parts[0].isdigit():
                    clean_name = parts[1]

            if "___" in clean_name:
                clean_name = f"___[{season_name}]"

            new_dir_name = f"{new_prefix}. {clean_name}"
            new_dir_path = target_year_dir / new_dir_name
            new_dir_path.mkdir(parents=True, exist_ok=True)

            # Replicar subcarpetas
            for child in item.iterdir():
                if child.is_dir():
                    child_name = child.name
                    clean_child = child_name

                    if ". " in child_name:
                        c_parts = child_name.split(". ", 1)
                        if c_parts[0].isdigit():
                            clean_child = c_parts[1]

                    new_child_name = f"{new_prefix}. {clean_child}"
                    (new_dir_path / new_child_name).mkdir(parents=True, exist_ok=True)


def create_structure_from_json(json_data: dict, target_year_dir: Path, new_prefix: str, season_name: str):
    """
    Crea la estructura de carpetas a partir de folders.json.
    """
    target_year_dir.mkdir(parents=True, exist_ok=True)
    for key, subfolders in json_data.items():
        clean_key = key
        if clean_key == "___[]":
            clean_key = f"___[{season_name}]"

        main_dir_name = f"{new_prefix}. {clean_key}"
        main_dir_path = target_year_dir / main_dir_name
        main_dir_path.mkdir(parents=True, exist_ok=True)

        for sub_name in subfolders:
            sub_dir_name = f"{new_prefix}. {sub_name}"
            (main_dir_path / sub_dir_name).mkdir(parents=True, exist_ok=True)


def trigger_year_creation(year_value: int, parent_window, base_path=None, infra_path=None, today_date=None) -> bool:
    """
    Función principal llamada desde el click del YearItem.
    Maneja validaciones de fecha, confirmaciones, diálogo de entrada de temporada y creación de carpetas/credenciales.
    Retorna True si la creación fue exitosa.
    """

    # Inicializar rutas
    mgr = CharacterManager()
    if base_path is None:
        base_path = mgr.base_path
    base_path = Path(base_path)

    if infra_path is None:
        infra_path = Path("__structure__/infrastructure.json")
    infra_path = Path(infra_path)

    if today_date is None:
        today_date = datetime.date.today()

    target_year_dir = base_path / str(year_value)

    # 1. Validar restricciones de fecha
    allowed, message = validate_date_constraints(year_value, today_date)
    if not allowed:
        # Aplicar stylesheet oscuro a la caja de diálogo
        msg_box = QMessageBox(parent_window)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Advertencia")
        msg_box.setText(message)
        msg_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                color: {Theme.TEXT_WHITE};
                font-weight: bold;
            }}
        """)
        msg_box.exec()
        return False

    # 2. Paso 0: Mensaje de confirmación estándar si desea crear un nuevo año (yes/no)
    confirm_box = QMessageBox(parent_window)
    confirm_box.setIcon(QMessageBox.Icon.Question)
    confirm_box.setWindowTitle("Confirmación de Creación")
    confirm_box.setText(f"¿Desea crear un nuevo año ({year_value})?")
    confirm_box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    confirm_box.setDefaultButton(QMessageBox.StandardButton.No)
    confirm_box.setStyleSheet(f"""
        QMessageBox {{
            background-color: {Theme.APP_BACKGROUND};
            color: {Theme.TEXT_WHITE};
        }}
        QLabel {{
            color: {Theme.TEXT_WHITE};
        }}
        QPushButton {{
            background-color: #2d2d2d;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 6px 12px;
            color: {Theme.TEXT_WHITE};
            font-weight: bold;
        }}
    """)
    
    reply = confirm_box.exec()
    if reply != QMessageBox.StandardButton.Yes:
        return False

    # 3. Paso 1: Diálogo de entrada para el nombre de la temporada
    dialog = SeasonNameDialog(year_value, parent_window)
    if dialog.exec() != QDialog.DialogCode.Accepted or not dialog.accepted_value:
        return False

    season_name = dialog.season_name
    new_prefix = f"{max(0, year_value - 2003):02d}"

    # 4. Cargar folders.json o fallback
    folders_json_path = Path("__structure__/folders.json")
    use_fallback = True
    json_data = {}

    if folders_json_path.exists():
        try:
            with open(folders_json_path, "r", encoding="utf-8") as f:
                json_data = json.load(f)
            # Validar que sea un diccionario no vacío
            if isinstance(json_data, dict) and json_data:
                use_fallback = False
        except Exception:
            use_fallback = True

    # 5. Crear la estructura
    try:
        if use_fallback:
            # Buscar año plantilla
            template_year = find_fallback_template_year(base_path, today_date.year)
            if template_year is not None:
                template_dir = base_path / str(template_year)
                replicate_structure_from_fallback(template_dir, target_year_dir, new_prefix, season_name)
            else:
                # Si de plano no hay ninguna plantilla, crear una básica con código mínimo de respaldo
                target_year_dir.mkdir(parents=True, exist_ok=True)
                (target_year_dir / f"{new_prefix}. ___[{season_name}]").mkdir(parents=True, exist_ok=True)
                (target_year_dir / f"{new_prefix}. album").mkdir(parents=True, exist_ok=True)
                (target_year_dir / f"{new_prefix}. identity").mkdir(parents=True, exist_ok=True)
        else:
            create_structure_from_json(json_data, target_year_dir, new_prefix, season_name)

        # 6. Paso 6: Crear la credencial de año dentro de identity
        identity_dir = target_year_dir / f"{new_prefix}. identity"
        identity_dir.mkdir(parents=True, exist_ok=True)
        json_filepath = identity_dir / f"The_ID_Year_{year_value}.json"

        id_pkg = calculate_id_package_default(year_value, infra_path)

        year_data = {
            "year_data": {
                "year": str(year_value),
                "prefix": new_prefix,
                "season_name": season_name,
                "season_abreviation": "",
                "esentia_name": "",
                "id_package_default": id_pkg,
                "other_id_package_default": []
            }
        }

        with open(json_filepath, "w", encoding="utf-8") as f:
            json.dump(year_data, f, indent=4, ensure_ascii=False)

        return True

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        err_box = QMessageBox(parent_window)
        err_box.setIcon(QMessageBox.Icon.Critical)
        err_box.setWindowTitle("Error de Creación")
        err_box.setText(f"Ocurrió un error al crear la estructura del año:\n{e}\n\nDetalles:\n{tb}")
        err_box.setStyleSheet(f"""
            QMessageBox {{
                background-color: {Theme.APP_BACKGROUND};
                color: {Theme.TEXT_WHITE};
            }}
            QLabel {{
                color: {Theme.TEXT_WHITE};
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                color: {Theme.TEXT_WHITE};
                font-weight: bold;
            }}
        """)
        err_box.exec()
        return False
