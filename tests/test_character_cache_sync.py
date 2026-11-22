import json
from pathlib import Path

import pytest

from engines import character_cache_sync
from engines.character_cache_sync import (
    CharacterCacheSyncError,
    CharacterCacheSyncService,
)


class FakeCharacterManager:
    def __init__(self, cache_path):
        self.cache_path = Path(cache_path)
        self._cache = {}

    def save_cache_file(self):
        raise AssertionError("Cache-to-credential sync must not write Structure cache data")


def setup_service(tmp_path, cache_character):
    dependent = tmp_path / "dependent"
    character_dir = dependent / "2018" / "15. album" / (
        "15. 01;cure_machérie;emiru_aisaki;2008-11-30;10"
    )
    character_dir.mkdir(parents=True)
    credential = character_dir / "__emiru_aisaki__.json"
    credential_payload = {
        "character_data": {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "icon_path": "",
            "background_path": "",
            "type_underwear": [],
            "short_masked_alterego": "",
            "color_group": "",
            "secondary_color": "",
            "profession_group": "",
            "time_of_year": "",
        }
    }
    credential.write_text(
        json.dumps(credential_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    structure_root = tmp_path / "Structure"
    structure_dir = structure_root / "__structure__"
    structure_dir.mkdir(parents=True)
    (structure_root / ".git").mkdir()

    cache_path = structure_dir / "characters_cache.json"
    cache_path.write_text(
        json.dumps({"2018": [cache_character]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manager = FakeCharacterManager(cache_path)
    service = CharacterCacheSyncService(
        dependent_path=dependent,
        character_manager=manager,
        structure_dir=structure_dir,
        cache_path=cache_path,
        state_root=tmp_path / "AppData" / "CharacterCacheSync",
    )
    return service, credential, structure_dir


def test_cache_diff_is_previewed_against_local_credential_without_using_cached_path(tmp_path):
    service, credential, structure_dir = setup_service(
        tmp_path,
        {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "character_json_path": "Z:/from-another-computer/__emiru_aisaki__.json",
            "color_group": "rojo",
            "profession_group": "cantante",
        },
    )

    service.capture_pending_snapshot()
    rows = service.preview_changes()

    assert {row["field"] for row in rows} == {"color_group", "profession_group"}
    assert all(Path(row["credential_path"]).is_relative_to(credential.parent) for row in rows)
    assert credential.read_text(encoding="utf-8").find('"color_group": ""') >= 0


def test_selected_cache_fields_are_applied_with_prechange_backup(tmp_path):
    service, credential, structure_dir = setup_service(
        tmp_path,
        {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "color_group": "rojo",
            "secondary_color": "rosa",
            "profession_group": "cantante",
        },
    )
    service.capture_pending_snapshot()
    rows = service.preview_changes()
    selected = [row for row in rows if row["field"] == "color_group"]

    result = service.apply_selected(selected)

    updated = json.loads(credential.read_text(encoding="utf-8"))["character_data"]
    assert updated["color_group"] == "rojo"
    assert updated["secondary_color"] == ""
    assert updated["profession_group"] == ""
    assert result["applied_characters"] == 1
    assert result["applied_fields"] == 1
    backup = Path(result["backup_root"]) / credential.relative_to(service.dependent_root)
    assert backup.is_file()
    assert json.loads(backup.read_text(encoding="utf-8"))["character_data"]["color_group"] == ""
    assert service.has_pending_snapshot()


def test_applying_all_differences_removes_completed_pending_snapshot(tmp_path):
    service, credential, structure_dir = setup_service(
        tmp_path,
        {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "color_group": "rojo",
            "profession_group": "cantante",
        },
    )
    service.capture_pending_snapshot()
    rows = service.preview_changes()

    result = service.apply_selected(rows)

    assert result["applied_fields"] == 2
    assert result["remaining_changes"] == 0
    assert service.has_pending_snapshot() is False


def test_local_credential_change_after_preview_is_not_overwritten(tmp_path):
    service, credential, structure_dir = setup_service(
        tmp_path,
        {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "color_group": "rojo",
        },
    )
    service.capture_pending_snapshot()
    rows = service.preview_changes()
    payload = json.loads(credential.read_text(encoding="utf-8"))
    payload["character_data"]["color_group"] = "azul"
    credential.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = service.apply_selected(rows)

    current = json.loads(credential.read_text(encoding="utf-8"))["character_data"]
    assert current["color_group"] == "azul"
    assert result["applied_fields"] == 0
    assert any("cambió después de la previsualización" in item for item in result["issues"])
    assert service.has_pending_snapshot()


def test_cached_absolute_image_path_from_another_machine_is_not_applied(tmp_path):
    service, credential, structure_dir = setup_service(
        tmp_path,
        {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "icon_path": "Z:/characters/icon.png",
        },
    )
    service.capture_pending_snapshot()

    rows = service.preview_changes()

    assert len(rows) == 1
    assert rows[0]["field"] == "icon_path"
    assert "no existe en este equipo" in rows[0]["error"]



def test_pending_cache_snapshot_is_not_overwritten_by_a_different_cache(tmp_path):
    service, credential, structure_dir = setup_service(
        tmp_path,
        {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "color_group": "rojo",
        },
    )
    first = service.capture_pending_snapshot()
    original_snapshot = Path(first["snapshot_path"]).read_bytes()
    service.cache_path.write_text(
        json.dumps({"2019": []}, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(CharacterCacheSyncError, match="otra versión pendiente"):
        service.capture_pending_snapshot()

    assert Path(first["snapshot_path"]).read_bytes() == original_snapshot



def test_history_write_failure_reports_partial_application_and_keeps_snapshot(
    tmp_path,
    monkeypatch,
):
    service, credential, structure_dir = setup_service(
        tmp_path,
        {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "color_group": "rojo",
        },
    )
    service.capture_pending_snapshot()
    rows = service.preview_changes()
    original_write_json = character_cache_sync._atomic_write_json

    def fail_history_write(path, payload):
        if Path(path) == service.history_path:
            raise OSError("disk full")
        return original_write_json(path, payload)

    monkeypatch.setattr(
        character_cache_sync,
        "_atomic_write_json",
        fail_history_write,
    )

    result = service.apply_selected(rows)

    current = json.loads(credential.read_text(encoding="utf-8"))["character_data"]
    assert current["color_group"] == "rojo"
    assert result["applied_fields"] == 1
    assert result["history_saved"] is False
    assert any("no se pudo guardar el historial local" in issue for issue in result["issues"])
    assert service.has_pending_snapshot()
    backup = Path(result["backup_root"]) / credential.relative_to(service.dependent_root)
    assert backup.is_file()
