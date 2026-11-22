import json

import pytest

from engines.year_structure_editor import (
    YearStructureEditorError,
    YearStructureEditorService,
)


def _write_year(root, year, season):
    prefix = f"{max(0, year - 2003):02d}"
    year_path = root / str(year)
    (year_path / f"{prefix}. ___[{season}]").mkdir(parents=True)
    identity = year_path / f"{prefix}. identity"
    identity.mkdir()
    (identity / f"The_ID_Year_{year}.json").write_text(
        json.dumps({"year_data": {"year": str(year), "season_name": season}}),
        encoding="utf-8",
    )
    return year_path, prefix


def _rows_for_rename():
    return [
        {
            "old_name": "___[]",
            "name": "___[]",
            "subfolders": [{"old_name": "_eps.on", "name": "_eps.on"}],
        },
        {
            "old_name": "resources.local.acrobat",
            "name": "library.local.acrobat",
            "subfolders": [
                {
                    "old_name": "resources.local.acrobat.cache",
                    "name": "library.local.acrobat.cache",
                }
            ],
        },
    ]


def test_renames_managed_folders_and_subfolders_in_every_year(tmp_path):
    dependent = tmp_path / "_Internal"
    structure = tmp_path / "Structure" / "__structure__"
    structure.mkdir(parents=True)
    template_path = structure / "folders.json"
    original = {
        "___[]": ["_eps.on"],
        "resources.local.acrobat": ["resources.local.acrobat.cache"],
    }
    template_path.write_text(json.dumps(original), encoding="utf-8")

    years = [
        _write_year(dependent, 2025, "Season 2025"),
        _write_year(dependent, 2026, "Season 2026"),
    ]
    for year_path, prefix in years:
        old_root = year_path / f"{prefix}. resources.local.acrobat"
        old_child = old_root / f"{prefix}. resources.local.acrobat.cache"
        old_child.mkdir(parents=True)
        (old_child / "preserved.txt").write_text("keep", encoding="utf-8")

    service = YearStructureEditorService(dependent, template_path)
    preview = service.preview_template_rows(_rows_for_rename(), original)
    assert preview["renamed_count"] == 4
    assert preview["year_count"] == 2

    result = service.apply_template_rows(_rows_for_rename(), original)
    assert result["renamed_count"] == 4
    assert json.loads(template_path.read_text(encoding="utf-8")) == {
        "___[]": ["_eps.on"],
        "library.local.acrobat": ["library.local.acrobat.cache"],
    }

    for year_path, prefix in years:
        new_root = year_path / f"{prefix}. library.local.acrobat"
        new_child = new_root / f"{prefix}. library.local.acrobat.cache"
        assert new_child.is_dir()
        assert (new_child / "preserved.txt").read_text(encoding="utf-8") == "keep"
        assert not (year_path / f"{prefix}. resources.local.acrobat").exists()
        assert any(
            entry.name == f"{prefix}. ___[Season {year_path.name}]"
            for entry in year_path.iterdir()
        )


def test_adds_new_folders_and_subfolders_without_deleting_existing_data(tmp_path):
    dependent = tmp_path / "_Internal"
    structure = tmp_path / "Structure" / "__structure__"
    structure.mkdir(parents=True)
    template_path = structure / "folders.json"
    original = {"___[]": [], "album": []}
    template_path.write_text(json.dumps(original), encoding="utf-8")
    years = [
        _write_year(dependent, 2025, "Season 2025"),
        _write_year(dependent, 2026, "Season 2026"),
    ]
    for year_path, prefix in years:
        legacy = year_path / f"{prefix}. legacy"
        legacy.mkdir()
        (legacy / "important.txt").write_text("keep", encoding="utf-8")

    rows = [
        {"old_name": "___[]", "name": "___[]", "subfolders": []},
        {"old_name": "album", "name": "album", "subfolders": []},
        {
            "old_name": None,
            "name": "knowledge",
            "subfolders": [{"old_name": None, "name": "knowledge.local"}],
        },
    ]
    result = YearStructureEditorService(
        dependent,
        template_path,
    ).apply_template_rows(rows, original)

    assert result["created_count"] == 4
    for year_path, prefix in years:
        assert (year_path / f"{prefix}. knowledge").is_dir()
        assert (
            year_path
            / f"{prefix}. knowledge"
            / f"{prefix}. knowledge.local"
        ).is_dir()
        assert (year_path / f"{prefix}. legacy" / "important.txt").read_text(
            encoding="utf-8"
        ) == "keep"


def test_removed_template_entries_do_not_delete_existing_directories(tmp_path):
    dependent = tmp_path / "_Internal"
    structure = tmp_path / "Structure" / "__structure__"
    structure.mkdir(parents=True)
    template_path = structure / "folders.json"
    original = {"___[]": [], "album": [], "legacy": []}
    template_path.write_text(json.dumps(original), encoding="utf-8")
    year_path, prefix = _write_year(dependent, 2025, "Season 2025")
    legacy = year_path / f"{prefix}. legacy"
    legacy.mkdir()
    (legacy / "data.txt").write_text("preserved", encoding="utf-8")

    rows = [
        {"old_name": "___[]", "name": "___[]", "subfolders": []},
        {"old_name": "album", "name": "album", "subfolders": []},
    ]
    YearStructureEditorService(dependent, template_path).apply_template_rows(
        rows,
        original,
    )

    assert "legacy" not in json.loads(template_path.read_text(encoding="utf-8"))
    assert (legacy / "data.txt").read_text(encoding="utf-8") == "preserved"


def test_existing_destination_blocks_the_whole_template_update(tmp_path):
    dependent = tmp_path / "_Internal"
    structure = tmp_path / "Structure" / "__structure__"
    structure.mkdir(parents=True)
    template_path = structure / "folders.json"
    original = {"___[]": [], "resources.local.acrobat": []}
    template_path.write_text(json.dumps(original), encoding="utf-8")
    year_path, prefix = _write_year(dependent, 2025, "Season 2025")
    (year_path / f"{prefix}. resources.local.acrobat").mkdir()
    (year_path / f"{prefix}. library.local.acrobat").mkdir()

    rows = [
        {"old_name": "___[]", "name": "___[]", "subfolders": []},
        {
            "old_name": "resources.local.acrobat",
            "name": "library.local.acrobat",
            "subfolders": [],
        },
    ]
    with pytest.raises(YearStructureEditorError, match="ya existe la carpeta destino"):
        YearStructureEditorService(dependent, template_path).apply_template_rows(
            rows,
            original,
        )

    assert json.loads(template_path.read_text(encoding="utf-8")) == original
    assert (year_path / f"{prefix}. resources.local.acrobat").is_dir()
    assert (year_path / f"{prefix}. library.local.acrobat").is_dir()


def test_invalid_and_unsafe_template_names_are_rejected(tmp_path):
    dependent = tmp_path / "_Internal"
    dependent.mkdir()
    structure = tmp_path / "Structure" / "__structure__"
    structure.mkdir(parents=True)
    template_path = structure / "folders.json"
    original = {"___[]": [], "album": []}
    template_path.write_text(json.dumps(original), encoding="utf-8")

    rows = [
        {"old_name": "___[]", "name": "___[]", "subfolders": []},
        {"old_name": "album", "name": "../outside", "subfolders": []},
    ]
    with pytest.raises(YearStructureEditorError, match="caracteres no válidos"):
        YearStructureEditorService(dependent, template_path).preview_template_rows(
            rows,
            original,
        )
