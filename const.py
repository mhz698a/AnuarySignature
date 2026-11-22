from pathlib import Path

from engines.structure_paths import get_structure_file

APP_NAME = "AnuarySignature"
APP_DIR = Path(__file__).resolve().parent
ICON_WIN = APP_DIR / "assets" / "directorio.ico"
JSON_DOMAINS = get_structure_file("infrastructure.json")
CONTAINER_DOMAINS = get_structure_file("container.json")
MYAPPID = "AnuarySignature.StructureTools.AnuarySignature.1.0"