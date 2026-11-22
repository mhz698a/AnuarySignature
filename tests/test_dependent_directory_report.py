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
    (dependent_root / "2010" / "06. music").mkdir(parents=True)

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
        "2010\\06. music",
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


def test_user_can_exclude_a_folder_category_across_all_years(tmp_path):
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
    other_year_album = dependent_root / "2026" / "23. album" / "23. 01;Example;Other;2000-01-02;25"
    other_year_public = dependent_root / "2026" / "23. public" / "visible"
    album.mkdir(parents=True)
    visible_folder.mkdir(parents=True)
    other_year_album.mkdir(parents=True)
    other_year_public.mkdir(parents=True)
    (album / "__Character__.json").write_text("{}", encoding="utf-8")

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.save_exclusion_preferences(["22. album"])
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
    assert "2026\\23. album" not in reported_paths
    assert "2026\\23. album\\23. 01;Example;Other;2000-01-02;25" not in reported_paths
    assert "2026\\23. public\\visible" in reported_paths
    assert payload["character_credentials"] == []
    assert payload["excluded_directories"] == [
        "2025/22. album",
        "2026/23. album",
    ]


def test_user_can_include_resources_local_personal_across_all_years(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    personal_subfolders = [
        dependent_root / "2025" / "resources.local.personal" / "visible-after-override",
        dependent_root / "2026" / "23. resources.local.personal" / "visible-after-override",
    ]
    for personal_subfolder in personal_subfolders:
        personal_subfolder.mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.save_exclusion_preferences(
        [],
        ["resources.local.personal"],
    )
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    reported_paths = {
        item["relative_path"] for item in payload["directories"]
    }

    assert "2025\\resources.local.personal" in reported_paths
    assert "2026\\23. resources.local.personal" in reported_paths
    assert (
        "2025\\resources.local.personal\\visible-after-override"
        in reported_paths
    )
    assert (
        "2026\\23. resources.local.personal\\visible-after-override"
        in reported_paths
    )
    assert payload["excluded_directories"] == []


def test_directory_category_options_are_aggregated_across_years(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    year_folders = {
        "2025": [
            "22. resources.local.personal",
            "22. album",
            "22. identity",
        ],
        "2026": [
            "23. resources.local.personal",
            "23. album",
            "23. identity",
        ],
    }
    for year, folder_names in year_folders.items():
        for folder_name in folder_names:
            (dependent_root / year / folder_name).mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.save_exclusion_preferences(["resources.local.personal"])
    options = service.list_directory_category_options()

    assert options["structure_consistent"] is True
    assert options["year_count"] == 2
    by_key = {item["key"]: item for item in options["categories"]}
    assert set(by_key) == {
        "resources.local.personal",
        "album",
        "identity",
    }
    assert by_key["resources.local.personal"]["name"] == (
        "resources.local.personal"
    )
    assert by_key["resources.local.personal"]["excluded"] is True
    assert by_key["resources.local.personal"]["years_present"] == 2
    assert by_key["album"]["name"] == "album"
    assert service._directory_category_label("22. album") == "album"
    assert service._directory_category_label("23. album") == "album"
    assert service._directory_category_label(
        "22. ___[Season 2025]"
    ) == "___[...]"


def test_directory_structure_mismatch_blocks_report_and_preserves_old_file(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    (dependent_root / "2025" / "22. album").mkdir(parents=True)
    (dependent_root / "2025" / "22. identity").mkdir()
    (dependent_root / "2026" / "23. album").mkdir(parents=True)
    (dependent_root / "2026" / "23. music").mkdir()

    report_path.parent.mkdir(parents=True)
    original = '{"previous": true}\n'
    report_path.write_text(original, encoding="utf-8")
    service = DependentDirectoryReportService(
        dependent_root,
        report_path,
        current_year=2026,
    )

    options = service.list_directory_category_options()
    assert options["structure_consistent"] is False
    assert options["mismatches"][0]["year"] == "2025"

    with pytest.raises(DependentDirectoryReportError, match="no coincide con la plantilla"):
        service.generate_or_update()

    assert report_path.read_text(encoding="utf-8") == original


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
        ["04. archive"],
        ["resources.local.personal"],
    )

    second_service = DependentDirectoryReportService(dependent_root, report_path)
    preferences = second_service.load_exclusion_preferences()

    assert preferences["schema_version"] == 2
    assert preferences["excluded_directory_names"] == ["archive"]
    assert preferences["included_directory_names"] == [
        "resources.local.personal"
    ]


def test_default_exclusion_matches_a_numeric_folder_prefix(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    excluded_folder = (
        dependent_root
        / "2025"
        / "22. resources.local.personal"
        / "nested"
    )
    excluded_folder.mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    reported_paths = {
        item["relative_path"] for item in payload["directories"]
    }
    assert "2025\\22. resources.local.personal" not in reported_paths
    assert "2025\\22. resources.local.personal\\nested" not in reported_paths
    assert payload["excluded_directories"] == [
        "2025/22. resources.local.personal"
    ]


def test_legacy_year_specific_preferences_migrate_to_global_categories(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    settings_path = report_path.with_name(
        "dependent_directory_report_settings.json"
    )
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "excluded_directories": ["2024/04. archive"],
                "included_directories": ["2025/25. resources.local.personal"],
            }
        ),
        encoding="utf-8",
    )

    service = DependentDirectoryReportService(
        dependent_root,
        report_path,
        settings_path,
    )
    preferences = service.load_exclusion_preferences()

    assert preferences["schema_version"] == 2
    assert preferences["excluded_directory_names"] == ["archive"]
    assert preferences["included_directory_names"] == [
        "resources.local.personal"
    ]


def test_default_personal_exclusion_is_global_for_numbered_folders(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    (dependent_root / "2025" / "22. resources.local.personal").mkdir(
        parents=True
    )
    (dependent_root / "2025" / "22. album").mkdir()
    (dependent_root / "2026" / "23. resources.local.personal").mkdir(
        parents=True
    )
    (dependent_root / "2026" / "23. album").mkdir()

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update()

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    reported_paths = {
        item["relative_path"] for item in payload["directories"]
    }
    assert "2025\\22. resources.local.personal" not in reported_paths
    assert "2026\\23. resources.local.personal" not in reported_paths
    assert payload["excluded_directory_count"] == 2


def test_text_report_contains_plain_directory_tree_and_credential_filename(tmp_path):
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
    (character_folder / "__Character__.json").write_text(
        '{"secret": "must_not_be_included"}',
        encoding="utf-8",
    )

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(dependent_root, report_path)
    result = service.generate_or_update(report_format="txt")

    text_report_path = report_path.with_name("dependent_directory_report.txt")
    tree_text = text_report_path.read_text(encoding="utf-8")
    assert result["report_format"] == "txt"
    assert result["report_path"] == str(text_report_path)
    assert "ÁRBOL DE DIRECTORIOS:" in tree_text
    assert "2025" in tree_text
    assert "22. album" in tree_text
    assert "22. 01;Example;Character;2000-01-02;25" in tree_text
    assert "__Character__.json" in tree_text
    assert "must_not_be_included" not in tree_text


def test_text_report_does_not_overwrite_json_report(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    (dependent_root / "2025" / "22. album").mkdir(parents=True)
    report_path.parent.mkdir(parents=True)

    service = DependentDirectoryReportService(dependent_root, report_path)
    service.generate_or_update(report_format="json")
    original_json = report_path.read_text(encoding="utf-8")
    service.generate_or_update(report_format="txt")

    assert report_path.read_text(encoding="utf-8") == original_json
    assert report_path.with_name("dependent_directory_report.txt").is_file()


def test_unsupported_report_format_is_rejected(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    (dependent_root / "2025").mkdir(parents=True)
    report_path.parent.mkdir(parents=True)

    service = DependentDirectoryReportService(dependent_root, report_path)
    with pytest.raises(DependentDirectoryReportError, match="Formato"):
        service.generate_or_update(report_format="html")

def test_report_uses_folders_json_as_authoritative_year_creation_source(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    folders_json = tmp_path / "Structure" / "__structure__" / "folders.json"
    folders_json.parent.mkdir(parents=True)
    folders_json.write_text(
        json.dumps(
            {
                "___[]": [],
                "album": [],
                "identity": [],
                "resources.local.personal": [],
            }
        ),
        encoding="utf-8",
    )

    for year, prefix, season in (
        ("2025", "22", "Season 2025"),
        ("2026", "23", "Season 2026"),
    ):
        year_dir = dependent_root / year
        for folder_name in (
            f"{prefix}. ___[{season}]",
            f"{prefix}. album",
            f"{prefix}. identity",
            f"{prefix}. resources.local.personal",
        ):
            (year_dir / folder_name).mkdir(parents=True)

    service = DependentDirectoryReportService(
        dependent_root,
        report_path,
        structure_definition_path=folders_json,
        current_year=2026,
    )
    options = service.list_directory_category_options()

    assert options["structure_source"] == "folders.json"
    assert options["template_year"] is None
    assert options["structure_consistent"] is True
    by_key = {item["key"]: item for item in options["categories"]}
    assert set(by_key) == {
        "___[]",
        "album",
        "identity",
        "resources.local.personal",
    }
    assert by_key["___[]"]["name"] == "xx. ___[...]"
    assert by_key["resources.local.personal"]["excluded"] is True
    assert by_key["___[]"]["name"] == "___[...]"

    result = service.generate_or_update()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["structure_source"] == "folders.json"
    assert payload["structure_source"] == "folders.json"
    assert payload["expected_folder_count"] == 4


def test_fallback_report_uses_the_same_template_year_priority_as_creation(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    missing_folders_json = tmp_path / "Structure" / "__structure__" / (
        "missing_folders.json"
    )

    for folder_name in ("22. album", "22. identity"):
        (dependent_root / "2024" / folder_name).mkdir(parents=True)
    for folder_name in ("23. album", "23. music"):
        (dependent_root / "2025" / folder_name).mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(
        dependent_root,
        report_path,
        structure_definition_path=missing_folders_json,
        current_year=2025,
    )
    options = service.list_directory_category_options()

    assert options["structure_source"] == "fallback_template"
    assert options["template_year"] == "2025"
    assert options["structure_consistent"] is False
    assert options["mismatches"][0]["year"] == "2024"
    assert {item["key"] for item in options["categories"]} == {
        "album",
        "music",
    }


def test_fallback_report_uses_maximum_year_when_current_and_previous_are_absent(
    tmp_path,
):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    for folder_name in ("22. album", "22. knowledge"):
        (dependent_root / "2018" / folder_name).mkdir(parents=True)
    for folder_name in ("23. album", "23. identity"):
        (dependent_root / "2020" / folder_name).mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(
        dependent_root,
        report_path,
        current_year=2026,
    )
    options = service.list_directory_category_options()

    assert options["structure_source"] == "fallback_template"
    assert options["template_year"] == "2020"
    assert {item["key"] for item in options["categories"]} == {
        "album",
        "identity",
    }


def test_report_uses_minimal_creation_fallback_when_no_template_exists(tmp_path):
    dependent_root = tmp_path / "_Internal"
    dependent_root.mkdir()
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    report_path.parent.mkdir(parents=True)

    service = DependentDirectoryReportService(
        dependent_root,
        report_path,
        current_year=2026,
    )
    options = service.list_directory_category_options()

    assert options["structure_source"] == "minimal_fallback"
    assert options["template_year"] is None
    assert {item["key"] for item in options["categories"]} == {
        "___[]",
        "album",
        "identity",
    }

def test_fallback_report_prefers_previous_year_before_maximum_existing_year(tmp_path):
    dependent_root = tmp_path / "_Internal"
    report_path = tmp_path / "Structure" / "__structure__" / (
        "dependent_directory_report.json"
    )
    for folder_name in ("22. album", "22. identity"):
        (dependent_root / "2024" / folder_name).mkdir(parents=True)
    for folder_name in ("25. album", "25. music"):
        (dependent_root / "2027" / folder_name).mkdir(parents=True)

    report_path.parent.mkdir(parents=True)
    service = DependentDirectoryReportService(
        dependent_root,
        report_path,
        current_year=2025,
    )
    options = service.list_directory_category_options()

    assert options["structure_source"] == "fallback_template"
    assert options["template_year"] == "2024"
    assert {item["key"] for item in options["categories"]} == {
        "album",
        "identity",
    }
    assert options["mismatches"][0]["year"] == "2027"

