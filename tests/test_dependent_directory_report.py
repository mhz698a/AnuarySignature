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

    report_path.parent.mkdir(parents=True, exist_ok=True)
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
    report_text = report_path.read_text(encoding="utf-8")
    assert "track.mp3" not in report_text
    assert "year.json" not in report_text
    assert "README.txt" not in report_text
    assert "deeper" not in report_text


def test_report_records_credential_filename_and_relative_location(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    character_folder = (
        dependent_root
        / "2025"
        / "22. album"
        / "22. 01;Example;Character;2000-01-02;25"
    )
    character_folder.mkdir(parents=True)
    credential = character_folder / "__Character__.json"
    credential.write_text(
        json.dumps({"character_data": {"private_value": "must_not_be_embedded"}}),
        encoding="utf-8",
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    result = service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    character = payload["character_credentials"][0]

    assert character["name"] == "Character"
    assert character["alterego"] == "Example"
    assert character["credential_status"] == "found"
    assert character["credential_file"] == "__Character__.json"
    assert character["credential_relative_path"] == (
        "2025/22. album/22. 01;Example;Character;2000-01-02;25/__Character__.json"
    )
    assert character["credential_files"] == [
        {
            "file_name": "__Character__.json",
            "relative_path": character["credential_relative_path"],
        }
    ]
    assert result["credential_found_count"] == 1
    assert result["credential_file_count"] == 1
    assert "must_not_be_embedded" not in report_path.read_text(encoding="utf-8")


def test_report_recognizes_legacy_credential_filename_pattern(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    character_folder = (
        dependent_root
        / "2024"
        / "21. album"
        / "21. 01;Example;Legacy;2000-01-02;25"
    )
    character_folder.mkdir(parents=True)
    (character_folder / "__Legacy.json").write_text("{}", encoding="utf-8")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    record = payload["character_credentials"][0]
    assert record["credential_status"] == "found"
    assert record["credential_file"] == "__Legacy.json"
    assert record["credential_relative_path"].endswith("/__Legacy.json")


def test_report_prefers_standard_filename_and_counts_additional_candidates(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    character_folder = (
        dependent_root
        / "2025"
        / "22. album"
        / "22. 01;Example;Character;2000-01-02;25"
    )
    character_folder.mkdir(parents=True)
    (character_folder / "__Character__.json").write_text("{}", encoding="utf-8")
    (character_folder / "__older__.json").write_text("{}", encoding="utf-8")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    result = service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    record = payload["character_credentials"][0]
    assert record["credential_status"] == "found_with_additional_candidates"
    assert record["credential_file"] == "__Character__.json"
    assert record["credential_relative_path"].endswith("/__Character__.json")
    assert len(record["credential_files"]) == 2
    assert result["credential_additional_candidates_count"] == 1


def test_report_marks_missing_and_ambiguous_character_credentials(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    album = dependent_root / "2025" / "22. album"
    missing = album / "22. 01;Alias;Missing;2000-01-02;25"
    ambiguous = album / "22. 02;Alias;Ambiguous;2000-01-02;25"
    missing.mkdir(parents=True)
    ambiguous.mkdir()
    (ambiguous / "__one__.json").write_text("{}", encoding="utf-8")
    (ambiguous / "__two__.json").write_text("{}", encoding="utf-8")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    result = service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    by_name = {
        item["name"]: item for item in payload["character_credentials"]
    }

    assert by_name["Missing"]["credential_status"] == "missing"
    assert by_name["Missing"]["credential_relative_path"] is None
    assert by_name["Ambiguous"]["credential_status"] == "ambiguous"
    assert by_name["Ambiguous"]["credential_relative_path"] is None
    assert len(by_name["Ambiguous"]["credential_files"]) == 2
    assert result["credential_missing_count"] == 1
    assert result["credential_ambiguous_count"] == 1
    assert result["credential_file_count"] == 2


def test_report_updates_after_new_directories_are_created(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    (dependent_root / "2025").mkdir(parents=True)

    report_path.parent.mkdir(parents=True, exist_ok=True)
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

    report_path.parent.mkdir(parents=True, exist_ok=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update()
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    relative_paths = {
        item["relative_path"] for item in payload["directories"]
    }
    assert "2010\\linked" not in relative_paths
    assert "2010\\linked\\not_inside_report" not in relative_paths


def test_report_does_not_include_symlinked_credential_files(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    character_folder = (
        dependent_root
        / "2025"
        / "22. album"
        / "22. 01;Example;Character;2000-01-02;25"
    )
    character_folder.mkdir(parents=True)
    external = tmp_path / "__external__.json"
    external.write_text("{}", encoding="utf-8")
    link = character_folder / "__Character__.json"
    try:
        link.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("File symlinks are not available in this environment.")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    record = payload["character_credentials"][0]
    assert record["credential_status"] == "missing"
    assert record["credential_files"] == []


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


def test_report_excludes_resources_local_personal_by_default(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    private_folder = (
        dependent_root
        / "2025"
        / "resources.local.personal"
        / "nested"
    )
    visible_folder = dependent_root / "2025" / "22. public"
    private_folder.mkdir(parents=True)
    visible_folder.mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    result = service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    reported_paths = {
        item["relative_path"] for item in payload["directories"]
    }

    assert "2025" in reported_paths
    assert "2025\\resources.local.personal" not in reported_paths
    assert "2025\\resources.local.personal\\nested" not in reported_paths
    assert "2025\\22. public" in reported_paths
    assert payload["excluded_directories"] == [
        "2025/resources.local.personal"
    ]
    assert result["excluded_directory_count"] == 1


def test_user_can_exclude_a_different_folder_for_one_year(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    album = (
        dependent_root
        / "2025"
        / "22. album"
        / "22. 01;Example;Character;2000-01-02;25"
    )
    visible_folder = dependent_root / "2025" / "22. public" / "visible"
    album.mkdir(parents=True)
    visible_folder.mkdir(parents=True)
    (album / "__Character__.json").write_text("{}", encoding="utf-8")

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.save_exclusion_preferences(
        ["2025/22. album"],
        [],
    )
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    reported_paths = {
        item["relative_path"] for item in payload["directories"]
    }

    assert "2025\\22. album" not in reported_paths
    assert (
        "2025\\22. album\\22. 01;Example;Character;2000-01-02;25"
        not in reported_paths
    )
    assert "2025\\22. public" in reported_paths
    assert "2025\\22. public\\visible" in reported_paths
    assert payload["character_credentials"] == []
    assert payload["excluded_directories"] == ["2025/22. album"]


def test_user_can_include_resources_local_personal_for_one_year(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    personal_subfolder = (
        dependent_root
        / "2025"
        / "resources.local.personal"
        / "visible-after-override"
    )
    personal_subfolder.mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.save_exclusion_preferences(
        [],
        ["2025/resources.local.personal"],
    )
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    reported_paths = {
        item["relative_path"] for item in payload["directories"]
    }

    assert "2025\\resources.local.personal" in reported_paths
    assert (
        "2025\\resources.local.personal\\visible-after-override"
        in reported_paths
    )
    assert payload["excluded_directories"] == []


def test_year_folder_options_show_default_and_saved_exclusions(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    (dependent_root / "2025" / "resources.local.personal").mkdir(parents=True)
    (dependent_root / "2025" / "22. public").mkdir()
    (dependent_root / "2026" / "26. private").mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.save_exclusion_preferences(["2026/26. private"], [])
    options = service.list_year_directory_options()

    by_year = {
        year["year"]: {
            folder["name"]: folder
            for folder in year["folders"]
        }
        for year in options
    }
    assert by_year["2025"]["resources.local.personal"]["excluded"] is True
    assert by_year["2025"]["22. public"]["excluded"] is False
    assert by_year["2026"]["26. private"]["excluded"] is True


def test_report_progress_identifies_years_and_folders(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    character = (
        dependent_root
        / "2025"
        / "22. album"
        / "22. 01;Example;Character;2000-01-02;25"
    )
    character.mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    progress_updates = []
    service.generate_or_update(
        progress_callback=lambda completed, total, message: (
            progress_updates.append((completed, total, message))
        )
    )

    active_updates = [
        update for update in progress_updates
        if update[1] > 0
    ]
    messages = [update[2] for update in active_updates]

    assert any(message == "Año 2025" for message in messages)
    assert any("2025/22. album" in message for message in messages)
    assert any("22. 01;Example;Character" in message for message in messages)
    assert active_updates[-1][0] == active_updates[-1][1]
    assert all(
        current <= total
        for current, total, _message in active_updates
    )


def test_exclusion_preferences_are_preserved_across_service_instances(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    report_path.parent.mkdir(parents=True)
    first_service = DependentDirectoryReportService(dependent_root, report_path)
    first_service.save_exclusion_preferences(
        ["2024/04. archive"],
        ["2025/resources.local.personal"],
    )

    second_service = DependentDirectoryReportService(dependent_root, report_path)
    preferences = second_service.load_exclusion_preferences()

    assert preferences["excluded_directories"] == ["2024/04. archive"]
    assert preferences["included_directories"] == [
        "2025/resources.local.personal"
    ]
