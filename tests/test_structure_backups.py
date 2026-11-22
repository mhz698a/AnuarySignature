from pathlib import Path
import zipfile

import pytest

from engines.structure_backups import (
    BACKUP_MANIFEST,
    StructureBackupError,
    StructureBackupManager,
)


def test_backup_excludes_git_metadata_and_restores_files(tmp_path):
    repo = tmp_path / "Structure"
    repo.mkdir()
    (repo / ".git").mkdir()
    (repo / ".git" / "config").write_text("git metadata", encoding="utf-8")
    data_dir = repo / "__structure__"
    data_dir.mkdir()
    data_file = data_dir / "infrastructure.json"
    data_file.write_text('{"version": 1}', encoding="utf-8")

    manager = StructureBackupManager(
        repo_root=repo,
        backup_root=tmp_path / "Backups",
    )
    backup = manager.create_backup(operation="manual", source_commit="abc123")

    data_file.write_text('{"version": 2}', encoding="utf-8")
    (data_dir / "new.json").write_text("new", encoding="utf-8")

    result = manager.restore_backup(backup)

    assert data_file.read_text(encoding="utf-8") == '{"version": 1}'
    assert not (data_dir / "new.json").exists()
    assert (repo / ".git" / "config").read_text(encoding="utf-8") == "git metadata"
    assert result["pre_restore_backup"] is not None
    assert len(manager.list_backups()) == 2


def test_restore_rejects_backup_outside_backup_directory(tmp_path):
    repo = tmp_path / "Structure"
    repo.mkdir()
    outside = tmp_path / "outside.zip"
    outside.write_bytes(b"not a backup")
    manager = StructureBackupManager(
        repo_root=repo,
        backup_root=tmp_path / "Backups",
    )

    with pytest.raises(StructureBackupError):
        manager.restore_backup(outside, create_pre_restore_backup=False)


def test_restore_rejects_path_traversal_inside_backup(tmp_path):
    repo = tmp_path / "Structure"
    repo.mkdir()
    backup_root = tmp_path / "Backups"
    backup_root.mkdir()
    malicious = backup_root / "structure-malicious.zip"
    import json
    with zipfile.ZipFile(malicious, "w") as archive:
        archive.writestr(
            BACKUP_MANIFEST,
            json.dumps({"files": [{"path": "../escaped.txt", "sha256": "invalid"}]}),
        )

    manager = StructureBackupManager(repo_root=repo, backup_root=backup_root)

    with pytest.raises(StructureBackupError):
        manager.restore_backup(malicious, create_pre_restore_backup=False)

    assert not (tmp_path / "escaped.txt").exists()
