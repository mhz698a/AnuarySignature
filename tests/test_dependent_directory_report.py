import json
from pathlib import Path

import pytest

from engines.dependent_directory_report import (
    DependentDirectoryReportError,
    DependentDirectoryReportService,
)


def test_report_contains_only_years_and_two_directory_levels(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_dir = tmp_path / "Structure" / "__structure__"
    report_path = report_dir / "dependent_directory_report.json"

    deepest = (
        dependent_root
        / "2009"
        / "06. music"
        / "06. s.rt.example"
        / "deeper"
    )
    deepest.mkdir(parents=True)
    (dependent_root / "2009" / "06. music" / "track.mp3").write_text(
        "not part of the report",
        encoding="utf-8",
    )
    (dependent_root / "2009" / "year.json").write_text(
        "{}",
        encoding="utf-8",
    )
    (dependent_root / "README.txt").write_text(
        "not a year directory",
        encoding="utf-8",
    )
    (dependent_root / "misc").mkdir()
    (dependent_root / "2010" / "00. archive").mkdir(parents=True)

    service = DependentDirectoryReportService(dependent_root, report_path)
    result = service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    relative_paths = {
        item["relative_path"] for item in payload["directories"]
    }

    assert relative_paths == {
        "2009",
        "2009\\06. music",
        "2009\\06. music\\06. s.rt.example",
        "2010",
        "2010\\00. archive",
    }
    assert all(
        item["depth_after_year"] <= 2
        for item in payload["directories"]
    )
    assert payload["max_subfolder_levels_after_year"] == 2
    assert payload["year_count"] == 2
    assert result["directory_count"] == 5
    assert "track.mp3" not in report_path.read_text(encoding="utf-8")
    assert "year.json" not in report_path.read_text(encoding="utf-8")
    assert "README.txt" not in report_path.read_text(encoding="utf-8")
    assert "deeper" not in report_path.read_text(encoding="utf-8")


def test_report_updates_after_new_directories_are_created(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    (dependent_root / "2025").mkdir(parents=True)

    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update()

    new_directory = dependent_root / "2025" / "10. new folder"
    new_directory.mkdir()
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert "2025\\10. new folder" in {
        item["relative_path"] for item in payload["directories"]
    }


def test_report_does_not_follow_symlinked_directories(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    target = dependent_root / "2010" / "real"
    target.mkdir(parents=True)
    external = tmp_path / "outside"
    external.mkdir()
    (external / "not_inside_report").mkdir()

    link = dependent_root / "2010" / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are not available in this environment.")

    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update()
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    relative_paths = {
        item["relative_path"] for item in payload["directories"]
    }
    assert "2010\\linked" not in relative_paths
    assert "2010\\linked\\not_inside_report" not in relative_paths


def test_unavailable_dependent_root_preserves_previous_report(tmp_path):
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    report_path.parent.mkdir(parents=True)
    original = '{"previous": true}\n'
    report_path.write_text(original, encoding="utf-8")

    service = DependentDirectoryReportService(
        tmp_path / "missing-drive",
        report_path,
    )

    with pytest.raises(DependentDirectoryReportError):
        service.generate_or_update()

    assert report_path.read_text(encoding="utf-8") == original
