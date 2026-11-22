import json
from pathlib import Path

import pytest

from engines.year_structure_sync import (
    YearStructureSyncError,
    YearStructureSyncService,
)


def _make_year(root: Path, year: int, prefix: str, structure: dict[str, list[str]]):
    year_dir = root / str(year)
    for category, subfolders in structure.items():
        category_dir = year_dir / f"{prefix}. {category}"
        category_dir.mkdir(parents=True, exist_ok=True)
        for subfolder in subfolders:
            (category_dir / f"{prefix}. {subfolder}").mkdir(
                parents=True,
                exist_ok=True,
            )
    return year_dir


def test_preview_unions_all_years_and_drops_categories_removed_everywhere(tmp_path):
    dependent_root = tmp_path / "_Internal"
    structure_dir = tmp_path / "Structure" / "__structure__"
    folders_json = structure_dir / "folders.json"
    backup_root = tmp_path / "Backups"

    _make_year(
        dependent_root,
        2024,
        "21",
        {
            "album": ["_edits", "_old"],
            "music": ["_b.r"],
            "___[Season 2024]": ["vocals"],
            "identity": [],
        },
    )
    _make_year(
        dependent_root,
        2025,
        "22",
        {
            "album": ["_edits", "_ahead"],
            "music": ["_b.r", "_b.t"],
            "___[Season 2025]": ["_eps.on"],
        },
    )
    folders_json.parent.mkdir(parents=True)
    folders_json.write_text(
        json.dumps(
            {
                "album": ["_old", "_edits", "_removed"],
                "music": ["_b.r"],
                "___[]": ["vocals"],
                "stale.category": [],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    service = YearStructureSyncService(
        dependent_root,
        folders_json,
        backup_root=backup_root,
    )
    result = service.preview()

    assert result["years"] == ["2025", "2024"]
    assert result["folders_data"] == {
        "album": ["_edits", "_ahead", "_old"],
        "music": ["_b.r", "_b.t"],
        "___[]": ["_eps.on", "vocals"],
        "identity": [],
    }
    assert result["added_categories"] == ["identity"]
    assert result["removed_categories"] == ["stale.category"]
    assert {
        (item["category"], item["name"])
        for item in result["added_subfolders"]
    } == {
        ("album", "_ahead"),
        ("music", "_b.t"),
        ("___[]", "_eps.on"),
    }
    assert {
        (item["category"], item["name"])
        for item in result["removed_subfolders"]
    } == {
        ("album", "_removed"),
    }
    assert result["changed"] is True
    assert not backup_root.exists()
    assert "stale.category" in folders_json.read_text(encoding="utf-8")


def test_synchronize_creates_backup_and_updates_json_atomically(tmp_path):
    dependent_root = tmp_path / "_Internal"
    folders_json = tmp_path / "Structure" / "__structure__" / "folders.json"
    backup_root = tmp_path / "Backups"
    _make_year(dependent_root, 2026, "23", {"album": ["_edits"], "identity": []})
    folders_json.parent.mkdir(parents=True)
    original = '{"outdated": []}\n'
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
        "album": ["_edits"],
        "identity": [],
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
    _make_year(dependent_root, 2025, "22", {"album": []})
    (dependent_root / "misc").mkdir()
    (dependent_root / "2026.txt").write_text("not a year directory", encoding="utf-8")

    service = YearStructureSyncService(
        dependent_root,
        tmp_path / "Structure" / "folders.json",
    )
    result = service.preview()

    assert result["years"] == ["2025"]
    assert result["folders_data"] == {"album": []}
