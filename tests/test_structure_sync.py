from pathlib import Path

import pytest

from engines import structure_sync
from engines.structure_sync import StructureSyncService


def test_sync_service_detects_unmerged_paths(tmp_path):
    service = StructureSyncService(repo_root=tmp_path)

    conflicts = service._conflicts(
        [
            " M __structure__/infrastructure.json",
            "UU __structure__/contacts_db.json",
            "AA __structure__/new.json",
            " D __structure__/removed.json",
        ]
    )

    assert conflicts == [
        "UU __structure__/contacts_db.json",
        "AA __structure__/new.json",
    ]


def test_git_process_options_hide_windows_console(monkeypatch):
    class FakeStartupInfo:
        def __init__(self):
            self.dwFlags = 0
            self.wShowWindow = None

    monkeypatch.setattr(
        structure_sync.subprocess, "STARTUPINFO", FakeStartupInfo, raising=False
    )
    monkeypatch.setattr(
        structure_sync.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False
    )
    monkeypatch.setattr(
        structure_sync.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False
    )

    options = structure_sync._background_process_options("nt")

    assert options["creationflags"] == 0x08000000
    assert options["startupinfo"].dwFlags & 1
    assert options["startupinfo"].wShowWindow == 0


def test_git_process_options_are_unchanged_on_non_windows():
    assert structure_sync._background_process_options("posix") == {}


def test_revision_counts_uses_the_selected_remote_branch(tmp_path):
    from types import SimpleNamespace

    service = StructureSyncService(repo_root=tmp_path)
    calls = []

    def fake_run_git(*arguments, **kwargs):
        calls.append(arguments)
        return SimpleNamespace(stdout="2\t3\n", returncode=0)

    service._run_git = fake_run_git

    assert service._revision_counts("phase-6/reviewed-character-colours") == (2, 3)
    assert calls == [
        (
            "rev-list",
            "--left-right",
            "--count",
            "HEAD...origin/phase-6/reviewed-character-colours",
        )
    ]


def test_switch_branch_refuses_to_switch_with_uncommitted_changes(tmp_path):
    from types import SimpleNamespace

    import pytest

    service = StructureSyncService(repo_root=tmp_path)
    service._ensure_repository = lambda: None
    service._ensure_expected_remote = lambda: "https://github.com/mhz698a/AnuarySignature-Structure.git"
    service._ensure_no_pending_character_cache_snapshot = lambda: None
    service._fetch = lambda **kwargs: None
    service._working_tree_changes = lambda: [" M characters_cache.json"]
    commands = []

    def fake_run_git(*arguments, **kwargs):
        commands.append(arguments)
        if arguments[:2] == ("check-ref-format", "--branch"):
            return SimpleNamespace(stdout="", returncode=0)
        if arguments[:2] == ("rev-parse", "--verify"):
            return SimpleNamespace(stdout="abc123\n", returncode=0)
        return SimpleNamespace(stdout="", returncode=0)

    service._run_git = fake_run_git

    with pytest.raises(structure_sync.StructureSyncError, match="cambios locales"):
        service.switch_branch("phase-6/reviewed-character-colours")

    assert not any(command and command[0] == "switch" for command in commands)

def test_cache_snapshot_is_written_outside_checkout_and_not_overwritten(tmp_path, monkeypatch):
    cache_dir = tmp_path / "Structure" / "__structure__"
    cache_dir.mkdir(parents=True)
    cache_file = cache_dir / "characters_cache.json"
    cache_file.write_text('{"2018": []}', encoding="utf-8")

    pending = tmp_path / "AppData" / "CharacterCacheSync" / "pending_characters_cache.json"
    monkeypatch.setattr(structure_sync, "get_structure_dir", lambda: cache_dir)
    monkeypatch.setattr(
        StructureSyncService,
        "_pending_character_cache_snapshot_path",
        staticmethod(lambda: pending),
    )
    service = StructureSyncService(repo_root=tmp_path / "checkout")

    result = service._capture_character_cache_snapshot()

    assert Path(result["snapshot_path"]) == pending
    assert pending.read_text(encoding="utf-8") == '{"2018": []}'
    cache_file.write_text('{"2019": []}', encoding="utf-8")

    with pytest.raises(structure_sync.StructureSyncError, match="Ya existe otra versión"):
        service._capture_character_cache_snapshot()

    assert pending.read_text(encoding="utf-8") == '{"2018": []}'


def test_pending_cache_snapshot_blocks_branch_change(tmp_path, monkeypatch):
    pending = tmp_path / "pending_characters_cache.json"
    pending.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        StructureSyncService,
        "_pending_character_cache_snapshot_path",
        staticmethod(lambda: pending),
    )
    service = StructureSyncService(repo_root=tmp_path)

    with pytest.raises(structure_sync.StructureSyncError, match="copia pendiente"):
        service._ensure_no_pending_character_cache_snapshot()
