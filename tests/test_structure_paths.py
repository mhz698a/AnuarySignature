from pathlib import Path

import pytest

from engines.structure_paths import (
    REQUIRED_STRUCTURE_FILES,
    get_missing_structure_files,
    get_structure_dir,
    get_structure_file,
    get_structure_repo_root,
)


def test_structure_checkout_uses_local_app_data(tmp_path):
    assert get_structure_repo_root(tmp_path) == (
        tmp_path / "AnuarySignature" / "Structure"
    )


def test_structure_files_resolve_inside_private_checkout(tmp_path):
    expected = (
        tmp_path
        / "AnuarySignature"
        / "Structure"
        / "__structure__"
        / "infrastructure.json"
    )
    assert get_structure_file("infrastructure.json", tmp_path) == expected
    assert get_structure_dir(tmp_path) == expected.parent


@pytest.mark.parametrize("filename", ["../secrets.json", "folder/file.json", "/absolute.json"])
def test_structure_file_rejects_paths_outside_structure(filename, tmp_path):
    with pytest.raises(ValueError):
        get_structure_file(filename, tmp_path)


def test_missing_structure_files_reports_required_json(tmp_path):
    missing = get_missing_structure_files(tmp_path)
    assert missing == list(REQUIRED_STRUCTURE_FILES)
