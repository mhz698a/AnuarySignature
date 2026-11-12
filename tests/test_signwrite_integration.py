from pathlib import Path

from signwrite.const import (
    APP_NAME,
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


def test_integrated_note_writer_uses_anuary_signature_name():
    assert APP_NAME == "AnuarySignature"


def test_domainviewer_autostart_helper_is_removed():
    assert not (Path(PROJECT_ROOT) / "engines" / "autostart.py").exists()


def test_knowledge_management_dialogs_are_window_modal():
    """Keep the shared note editor usable while Knowledge dialogs are open."""
    import ast

    dialog_specs = (
        ("domain_visor/domain_management_dialog.py", "DomainManagementDialog"),
        ("domain_visor/superdomain_rename_dialog.py", "SuperDomainManagementDialog"),
        ("year_visor/year_dialog.py", "YearDialog"),
        ("character_visor/character_dialog.py", "CharacterEditDialog"),
    )

    for relative_path, class_name in dialog_specs:
        source_path = Path(PROJECT_ROOT) / relative_path
        module = ast.parse(source_path.read_text(encoding="utf-8"))
        dialog_class = next(
            node
            for node in module.body
            if isinstance(node, ast.ClassDef) and node.name == class_name
        )
        uses_window_modality = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "setWindowModality"
            and node.args
            and ast.unparse(node.args[0]) == "Qt.WindowModality.WindowModal"
            for node in ast.walk(dialog_class)
        )

        assert uses_window_modality, f"{class_name} debe usar Qt.WindowModal"
