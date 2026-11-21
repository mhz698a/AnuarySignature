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
