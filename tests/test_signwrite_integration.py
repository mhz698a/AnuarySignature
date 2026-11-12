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


class _CharacterManagerStub:
    def __init__(self, characters):
        self.characters = characters

    def get_characters_for_year(self, year):
        return self.characters


def test_year_with_character_icons_reserves_six_pixels_below_them():
    from engines.layout_engine import LayoutEngine

    layout = LayoutEngine(_CharacterManagerStub([{"name": "Test"}]))

    assert layout.get_year_height(2026) == 45.0


def test_year_without_character_icons_keeps_base_height():
    from engines.layout_engine import LayoutEngine

    layout = LayoutEngine(_CharacterManagerStub([]))

    assert layout.get_year_height(2026) == 15.0
