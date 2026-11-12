"""Constants and shared paths for SingEtude integrated into DomainViewer."""

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

APP_NAME = "DomainViewer"
ORG_NAME = "EtudeProduts"

# Reuse DomainViewer's icon for every integrated window and dialog.
ICON_PATH = str(PROJECT_ROOT / "assets" / "directorio.ico")

# DomainViewer injects its configured dependent path when creating the editor.
BASE_DIR = os.environ.get("DOMAINVIEWER_DEPENDENT_PATH", r"E:\_Internal")
DEST_FOLDER = "knowledge"
DEST_BASIC = "_basic"

FILENAME_REPLACE_CHAR = "-"
FORMATS = ["txt", "md", "docx", "other"]
OTHER_OPTION = "Other..."

# Shared databases remain in DomainViewer's existing __structure__ folder.
CONTACTS_DB_PATH = str(PROJECT_ROOT / "__structure__" / "contacts_db.json")
CLASSIFICATIONS_DB_PATH = str(PROJECT_ROOT / "__structure__" / "classifications_db.json")

DEFAULT_CONTACTS_DB = {"autores": [], "destinatarios": [], "supervisores": []}

CONTACT_FIELDS = [
    ("autor", "Autor/Organismo representante:", "autores"),
    ("para", "Dirigido (Para):", "destinatarios"),
    ("cc", "Copia para otros interesados (CC):", "destinatarios"),
    ("cco", "Copia oculta anónima (CCO):", "destinatarios"),
    ("supervisor", "Supervisor:", "supervisores"),
]

default_clasifications_dict = [
    ("Análisis de episodios/peliculas", "analyze-ep"),
    ("Análisis de temporadas", "analyze-se"),
    ("Análisis de personajes", "analyse-ch"),
    ("Análisis globales", "analyze-gl"),
    ("Análisis bíblicos", "analyze-bi"),
    ("Datos interesantes", "light-data"),
    ("Dictamenes", "dictamen-judicial"),
    ("Sucesos y eventos de registro", "event-logg"),
    ("Dedicatorias y reflexiones", "dedic-refl"),
    ("Código de programación", "code-progr"),
    ("Conocimeintos serios", "serialknow"),
]
