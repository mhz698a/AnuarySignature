from domain_visor.structure_status_monitor import StructureStatusMonitor


def test_status_monitor_reports_remote_pull_commits():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "main",
            "ahead": 0,
            "behind": 3,
            "local_change_count": 0,
            "conflicts": [],
            "checked_at": "2026-11-21T14:00:00+00:00",
        }
    )

    assert label == "PULL 3"
    assert "pendientes de descargar: 3" in tooltip
    assert color == "#85c1e9"


def test_status_monitor_distinguishes_uncommitted_local_changes_from_push_commits():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "main",
            "ahead": 0,
            "behind": 0,
            "local_change_count": 4,
            "conflicts": [],
            "checked_at": "2026-11-21T14:00:00+00:00",
        }
    )

    assert label == "PUSH * (4)"
    assert "modificados: 4" in tooltip
    assert color == "#e5a65e"


def test_status_monitor_reports_commits_and_local_changes_together():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "main",
            "ahead": 2,
            "behind": 0,
            "local_change_count": 5,
            "conflicts": [],
        }
    )

    assert label == "PUSH 2 · LOCAL 5"
    assert "Commits locales pendientes de subir: 2" in tooltip
    assert "Archivos locales modificados: 5" in tooltip
    assert color == "#e5a65e"


def test_status_monitor_reports_both_remote_and_local_changes():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "main",
            "ahead": 0,
            "behind": 1,
            "local_change_count": 2,
            "conflicts": [],
        }
    )

    assert label == "PULL 1 · LOCAL 2"
    assert "hay cambios en ambos lados" in tooltip
    assert color == "#e5a65e"


def test_status_monitor_reports_conflicts_before_other_states():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "main",
            "ahead": 2,
            "behind": 1,
            "local_change_count": 2,
            "conflicts": ["UU __structure__/characters_cache.json"],
        }
    )

    assert label == "CONFLICTS 1"
    assert "Rutas con conflicto" in tooltip
    assert color == "#f48771"


def test_status_monitor_treats_clean_feature_branch_as_synchronized():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "phase-6/reviewed-character-colours",
            "ahead": 0,
            "behind": 0,
            "local_change_count": 0,
            "conflicts": [],
        }
    )

    assert label == "STRUCTURE · SYNC"
    assert "Rama: phase-6/reviewed-character-colours" in tooltip
    assert color == "#8ccf9b"


def test_status_monitor_reports_clean_repository():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "main",
            "ahead": 0,
            "behind": 0,
            "local_change_count": 0,
            "conflicts": [],
        }
    )

    assert label == "STRUCTURE · SYNC"
    assert "sincronizados" in tooltip
    assert color == "#8ccf9b"


def test_status_monitor_reports_remote_and_local_commits_together():
    label, tooltip, color = StructureStatusMonitor._format_status(
        {
            "branch": "main",
            "ahead": 3,
            "behind": 2,
            "local_change_count": 1,
            "conflicts": [],
        }
    )

    assert label == "PULL 2 · PUSH 3 · LOCAL 1"
    assert color == "#e5a65e"
