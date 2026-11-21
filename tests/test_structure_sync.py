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
