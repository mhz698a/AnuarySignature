from pathlib import Path

from signwrite.const import (
    CLASSIFICATIONS_DB_PATH,
    CONTACTS_DB_PATH,
    ICON_PATH,
    PROJECT_ROOT,
)


def test_singetude_databases_use_domainviewer_structure_directory():
    structure_dir = Path(PROJECT_ROOT) / "__structure__"

    assert Path(CONTACTS_DB_PATH) == structure_dir / "contacts_db.json"
    assert Path(CLASSIFICATIONS_DB_PATH) == structure_dir / "classifications_db.json"


def test_singetude_windows_use_domainviewer_icon():
    assert Path(ICON_PATH) == Path(PROJECT_ROOT) / "assets" / "directorio.ico"
