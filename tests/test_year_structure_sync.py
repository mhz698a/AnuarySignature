import json
from pathlib import Path

import pytest

from engines.year_structure_sync import (
    YearStructureSyncError,
    YearStructureSyncService,
)


def _make_year(root: Path, year: int, prefix: str, structure: dict[str, list[str]]):
    year_dir = root / str(year)
    for category, physical_subfolders in structure.items():
        category_dir = year_dir / f"{prefix}. {category}"
        category_dir.mkdir(parents=True, exist_ok=True)
        for subfolder in physical_subfolders:
            (category_dir / f"{prefix}. {subfolder}").mkdir(
                parents=True,
                exist_ok=True,
            )
    return year_dir


def test_preview_syncs_only_top_level_categories_and_preserves_manual_templates(
    tmp_path,
):
    dependent_root = tmp_path / "_Internal"
    structure_dir = tmp_path / "Structure" / "__structure__"
    folders_json = structure_dir / "folders.json"
    backup_root = tmp_path / "Backups"

    # Physical child folders intentionally differ between years and from the
    # manually maintained folders.json template. They must never be collected.
    _make_year(
        dependent_root,
        2024,
        "21",
        {
            "album": ["physical_only_2024"],
            "music": ["physical_music"],
            "___[Season 2024]": ["physical_season_folder"],
            "identity": [],
            "knowledge": [],
            "resources.local.images": [],
        },
    )
    _make_year(
        dependent_root,
        2025,
        "22",
        {
            "album": ["physical_only_2025"],
            "music": ["another_physical_music_folder"],
            "___[Season 2025]": ["another_physical_season_folder"],
            "identity": [],
            "overworld": [],
            "new.category": ["must_not_be_imported"],
        },
    )

    template = {
        "___[]": [
            "_eps.on",
            "_eps.v1",
            "lyrics",
            "mov_1",
            "mov_2",
            "sh_1",
            "sh_2",
            "sp",
            "vocals",
            "writed",
            "wroad",
        ],
        "album": [
            "_ahead",
            "_edits",
            "_nodef",
            "_other",
            "01;alter_ex;name_ex;2000-01-01;12",
        ],
        "music": ["_b.r", "_b.t"],
        "identity": [],
        "knowledge": [],
        "overworld": [],
        "resources.local.family": [],
        "resources.local.images": [],
    }
    folders_json.parent.mkdir(parents=True)
    folders_json.write_text(
        json.dumps(template, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    service = YearStructureSyncService(
        dependent_root,
        folders_json,
        backup_root=backup_root,
    )
    result = service.preview()

    expected = {
        "___[]": template["___[]"],
        "album": template["album"],
        "music": template["music"],
        "identity": [],
        "knowledge": [],
        "overworld": [],
        "resources.local.images": [],
        "new.category": [],
    }
    assert result["years"] == ["2025", "2024"]
    assert result["folders_data"] == expected
    assert result["added_categories"] == ["new.category"]
    assert result["removed_categories"] == ["resources.local.family"]
    assert result["category_count"] == 8
    assert result["subfolder_count"] == (
        len(template["___[]"]) + len(template["album"]) + len(template["music"])
    )
    assert "added_subfolders" not in result
    assert "removed_subfolders" not in result
    assert result["changed"] is True
    assert not backup_root.exists()
    assert json.loads(folders_json.read_text(encoding="utf-8")) == template


def test_synchronize_keeps_existing_template_arrays_and_adds_empty_new_category(
    tmp_path,
):
    dependent_root = tmp_path / "_Internal"
    folders_json = tmp_path / "Structure" / "__structure__" / "folders.json"
    backup_root = tmp_path / "Backups"

    _make_year(
        dependent_root,
        2026,
        "23",
        {
            "album": ["physical_child_not_in_template"],
            "identity": [],
            "knowledge": ["another_physical_child"],
        },
    )
    folders_json.parent.mkdir(parents=True)
    original_template = {
        "album": ["_ahead", "_edits", "01;alter_ex;name_ex;2000-01-01;12"],
        "removed.category": ["manually_defined_but_category_was_deleted"],
    }
    original = json.dumps(original_template, indent=2, ensure_ascii=False) + "\n"
    folders_json.write_text(original, encoding="utf-8")

    service = YearStructureSyncService(
        dependent_root,
        folders_json,
        backup_root=backup_root,
    )
    result = service.synchronize()

    assert result["written"] is True
    assert result["backup_path"]
    assert Path(result["backup_path"]).read_text(encoding="utf-8") == original
    assert json.loads(folders_json.read_text(encoding="utf-8")) == {
        "album": original_template["album"],
        "identity": [],
        "knowledge": [],
    }
    assert not list(folders_json.parent.glob(".folders.json.*.tmp"))

    second_result = service.synchronize()
    assert second_result["written"] is False
    assert second_result["backup_path"] is None


def test_preview_refuses_to_overwrite_when_no_year_directories_exist(tmp_path):
    dependent_root = tmp_path / "_Internal"
    dependent_root.mkdir()
    folders_json = tmp_path / "Structure" / "__structure__" / "folders.json"
    folders_json.parent.mkdir(parents=True)
    original = '{"album": []}'
    folders_json.write_text(original, encoding="utf-8")

    service = YearStructureSyncService(dependent_root, folders_json)

    with pytest.raises(YearStructureSyncError, match="No se encontraron"):
        service.synchronize()

    assert folders_json.read_text(encoding="utf-8") == original


def test_preview_refuses_to_replace_json_when_years_have_no_categories(tmp_path):
    dependent_root = tmp_path / "_Internal"
    (dependent_root / "2025").mkdir(parents=True)
    folders_json = tmp_path / "folders.json"
    original = '{"album": []}'
    folders_json.write_text(original, encoding="utf-8")

    service = YearStructureSyncService(dependent_root, folders_json)

    with pytest.raises(YearStructureSyncError, match="No se detectaron carpetas"):
        service.synchronize()

    assert folders_json.read_text(encoding="utf-8") == original


def test_preview_rejects_invalid_existing_json_without_replacing_it(tmp_path):
    dependent_root = tmp_path / "_Internal"
    _make_year(dependent_root, 2025, "22", {"album": []})
    folders_json = tmp_path / "folders.json"
    folders_json.write_text("{invalid", encoding="utf-8")

    service = YearStructureSyncService(dependent_root, folders_json)

    with pytest.raises(YearStructureSyncError, match="JSON UTF-8 válido"):
        service.synchronize()

    assert folders_json.read_text(encoding="utf-8") == "{invalid"


def test_preview_ignores_non_year_directories_and_year_files(tmp_path):
    dependent_root = tmp_path / "_Internal"
    _make_year(dependent_root, 2025, "22", {"album": ["ignored_child"]})
    (dependent_root / "misc").mkdir()
    (dependent_root / "2026.txt").write_text(
        "not a year directory",
        encoding="utf-8",
    )

    service = YearStructureSyncService(
        dependent_root,
        tmp_path / "Structure" / "folders.json",
    )
    result = service.preview()

    assert result["years"] == ["2025"]
    assert result["folders_data"] == {"album": []}
