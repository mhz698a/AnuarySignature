# domain_visor/about_dialog.py

import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton
)
from PyQt6.QtCore import Qt
from domain_visor.theme import Theme
from engines.structure_paths import get_structure_file

DEFAULT_ABOUT_IT_PATH = get_structure_file("about_it.json")

def load_about_data(filepath=None) -> dict:
    """
    Carga los datos de Misión y Visión desde `__structure__/about_it.json`.
    Si el archivo no existe, lo crea automáticamente con la estructura por defecto:
    { "mision": "", "vision": "" }
    """
    path = Path(filepath) if filepath else DEFAULT_ABOUT_IT_PATH
    default_structure = {"mision": "", "vision": ""}

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default_structure, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Error creando {path}: {e}")
        return default_structure

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {
                    "mision": data.get("mision", ""),
                    "vision": data.get("vision", "")
                }
    except Exception as e:
        print(f"Error leyendo {path}: {e}")

    return default_structure


class AboutDialog(QDialog):
    """
    Diálogo modal "Acerca de este visor" con estética oscura.
    Muestra Misión y Visión en dos columnas y "Domain Visor System 2026" al pie.
    """
    def __init__(self, filepath=None, parent=None):
        super().__init__(parent)
        self.filepath = Path(filepath) if filepath else DEFAULT_ABOUT_IT_PATH
        self.setWindowTitle("Acerca de este visor")
        self.setModal(True)
        self.setMinimumSize(600, 350)
        self.resize(650, 400)

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
            }}
            QPushButton {{
                background-color: #2d2d2d;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 16px;
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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        about_data = load_about_data(self.filepath)

        mision_text = about_data.get("mision", "").strip()
        if not mision_text:
            mision_text = "No hay información que mostrar"

        vision_text = about_data.get("vision", "").strip()
        if not vision_text:
            vision_text = "No hay información que mostrar"

        # Layout de 2 columnas
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(20)

        # Columna Izquierda: Misión
        col_left = QVBoxLayout()
        col_left.setSpacing(10)
        lbl_mision_title = QLabel("Misión")
        lbl_mision_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #85c1e9;")
        
        lbl_mision_content = QLabel(mision_text)
        lbl_mision_content.setWordWrap(True)
        lbl_mision_content.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lbl_mision_content.setStyleSheet("font-size: 12px; line-height: 1.4;")

        col_left.addWidget(lbl_mision_title)
        col_left.addWidget(lbl_mision_content, 1)

        # Separador vertical
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setStyleSheet("color: #3e3e42; background-color: #3e3e42;")

        # Columna Derecha: Visión
        col_right = QVBoxLayout()
        col_right.setSpacing(10)
        lbl_vision_title = QLabel("Visión")
        lbl_vision_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #85c1e9;")
        
        lbl_vision_content = QLabel(vision_text)
        lbl_vision_content.setWordWrap(True)
        lbl_vision_content.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lbl_vision_content.setStyleSheet("font-size: 12px; line-height: 1.4;")

        col_right.addWidget(lbl_vision_title)
        col_right.addWidget(lbl_vision_content, 1)

        columns_layout.addLayout(col_left, 1)
        columns_layout.addWidget(sep)
        columns_layout.addLayout(col_right, 1)

        main_layout.addLayout(columns_layout, 1)

        # Pie de página: "Domain Visor System 2026" centrado
        lbl_footer = QLabel("Domain Visor System 2026")
        lbl_footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_footer.setStyleSheet("font-size: 13px; font-weight: bold; color: #aaaaaa; padding-top: 10px;")

        main_layout.addWidget(lbl_footer)

        # Botón Aceptar / Cerrar
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Aceptar")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)
