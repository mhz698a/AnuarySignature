import json
from pathlib import Path

from engines.structure_orders import StructureOrderError, StructureOrderService


class FakeCharacterManager:
    def __init__(self, cache):
        self._cache = cache
        self.saved = False

    def save_cache_file(self):
        self.saved = True


def setup_order_service(tmp_path):
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
        json.dumps(credential_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    structure_dir = tmp_path / "Structure" / "__structure__"
    (structure_dir.parent / ".git").mkdir(parents=True)
    (structure_dir / "orders" / "pending").mkdir(parents=True)
    manager = FakeCharacterManager({
        "2018": [{
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
            "character_json_path": str(credential),
            "icon_path": "",
            "background_path": "",
            "color_group": "",
            "secondary_color": "",
        }]
    })
    service = StructureOrderService(
        dependent_path=dependent,
        character_manager=manager,
        structure_dir=structure_dir,
        state_path=tmp_path / "OrderState" / "applied.json",
        backup_root=tmp_path / "OrderBackups",
    )
    return service, manager, dependent, structure_dir, credential


def make_order(operation, order_id="order-2026-001"):
    return {
        "schema_version": 1,
        "id": order_id,
        "title": "Actualizar credencial de prueba",
        "description": "Orden controlada para pruebas.",
        "created_at": "2026-11-21T12:00:00-06:00",
        "operation": operation,
    }


def test_update_character_credential_creates_prechange_backup(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    order = make_order({
        "type": "update_character_credential",
        "target": {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
        },
        "fields": {
            "color_group": "rojo",
            "secondary_color": "rosa",
            "profession_group": "cantante",
        },
    })

    result = service.apply_order(order)

    payload = json.loads(credential.read_text(encoding="utf-8"))
    assert payload["character_data"]["color_group"] == "rojo"
    assert payload["character_data"]["secondary_color"] == "rosa"
    assert manager._cache["2018"][0]["profession_group"] == "cantante"
    assert manager.saved is True
    assert Path(result["details"]["backup"]["backup_path"]).is_file()
    assert result["status"] == "applied"
    assert result["destructive_operations"] is False
    assert (structure_dir / "orders" / "results" / "order-2026-001.json").is_file()


def test_order_cannot_be_applied_twice_on_same_machine(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    order = make_order({
        "type": "update_character_credential",
        "target": {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
        },
        "fields": {"profession_group": "cantante"},
    })
    service.apply_order(order)

    try:
        service.apply_order(order)
    except StructureOrderError as error:
        assert "ya fue aplicada" in str(error)
    else:
        raise AssertionError("The same order must not be applied twice")


def test_update_dependent_json_backs_up_existing_content(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    target = dependent / "2018" / "identity.json"
    target.write_text('{"old": true}\n', encoding="utf-8")
    order = make_order({
        "type": "update_dependent_json",
        "path": "2018/identity.json",
        "document": {"new": True},
    }, order_id="order-json-001")

    result = service.apply_order(order)

    assert json.loads(target.read_text(encoding="utf-8")) == {"new": True}
    backup = Path(result["details"]["backup"]["backup_path"])
    assert backup.read_text(encoding="utf-8") == '{"old": true}\n'


def test_create_directory_does_not_overwrite_existing_directory(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    order = make_order({
        "type": "create_directory",
        "path": "2018/15. new-folder",
    }, order_id="order-dir-001")

    result = service.apply_order(order)

    assert (dependent / "2018" / "15. new-folder").is_dir()
    assert result["details"]["operation"] == "create_directory"

    try:
        service.apply_order({
            **order,
            "id": "order-dir-002",
        })
    except StructureOrderError as error:
        assert "ya existe" in str(error)
    else:
        raise AssertionError("Existing directory must not be overwritten")


def test_orders_cannot_delete_move_or_traverse_outside_dependent_root(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)

    delete_order = make_order(
        {"type": "delete_file", "path": "2018/identity.json"},
        order_id="order-del-001",
    )
    try:
        service.validate_order(delete_order)
    except StructureOrderError as error:
        assert "deshabilitadas" in str(error)
    else:
        raise AssertionError("Delete operations must be rejected")

    move_order = make_order(
        {"type": "move", "from": "2018/a.json", "to": "2018/b.json"},
        order_id="order-move-01",
    )
    try:
        service.validate_order(move_order)
    except StructureOrderError as error:
        assert "deshabilitadas" in str(error)
    else:
        raise AssertionError("Move operations must be rejected")

    traversal_order = make_order({
        "type": "update_dependent_json",
        "path": "../outside.json",
        "document": {},
    }, order_id="order-path-001")
    try:
        service.validate_order(traversal_order)
    except StructureOrderError as error:
        assert "traversal" in str(error)
    else:
        raise AssertionError("Path traversal must be rejected")


def test_pending_orders_are_listed_and_invalid_orders_remain_visible(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    pending = structure_dir / "orders" / "pending"
    good = make_order({
        "type": "create_directory",
        "path": "2018/15. ai-created",
    }, order_id="order-good-001")
    (pending / "good.json").write_text(
        json.dumps(good),
        encoding="utf-8",
    )
    (pending / "invalid.json").write_text(
        '{"schema_version": 99}',
        encoding="utf-8",
    )

    orders = service.load_pending_orders()

    assert len(orders) == 2
    assert sum(bool(item["error"]) for item in orders) == 1
    assert sum(item["validated"] is not None for item in orders) == 1


def test_replace_character_asset_preserves_previous_image_and_updates_credential(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    old_image = credential.parent / "old-icon.png"
    old_image.write_bytes(b"previous-image")
    payload = json.loads(credential.read_text(encoding="utf-8"))
    payload["character_data"]["icon_path"] = old_image.name
    credential.write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    manager._cache["2018"][0]["icon_path"] = old_image.name

    asset_source = structure_dir / "orders" / "assets" / "new-icon.webp"
    asset_source.parent.mkdir(parents=True, exist_ok=True)
    asset_source.write_bytes(b"replacement-image")
    order = make_order({
        "type": "replace_character_asset",
        "target": {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
        },
        "field": "icon_path",
        "asset_path": "assets/new-icon.webp",
    }, order_id="order-image-001")

    result = service.apply_order(order)

    updated = json.loads(credential.read_text(encoding="utf-8"))
    new_name = updated["character_data"]["icon_path"]
    new_image = credential.parent / new_name
    assert new_image.read_bytes() == b"replacement-image"
    assert old_image.read_bytes() == b"previous-image"
    assert new_name.startswith("__structure_order_order-image-001_icon.")
    assert result["details"]["previous_image_preserved"] is True
    assert manager._cache["2018"][0]["icon_path"] == new_name


def test_replace_character_asset_rejects_asset_outside_order_assets_directory(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    order = make_order({
        "type": "replace_character_asset",
        "target": {
            "year": 2018,
            "name": "emiru_aisaki",
            "alterego": "cure_machérie",
        },
        "field": "icon_path",
        "asset_path": "../outside.png",
    }, order_id="order-image-002")

    try:
        service.validate_order(order)
    except StructureOrderError as error:
        assert "traversal" in str(error) or "debe estar bajo orders/assets" in str(error)
    else:
        raise AssertionError("Order image assets must remain inside orders/assets")


def test_shared_applied_result_prevents_reapplication_on_another_machine(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    pending = structure_dir / "orders" / "pending"
    results = structure_dir / "orders" / "results"
    results.mkdir(parents=True, exist_ok=True)
    order = make_order({
        "type": "create_directory",
        "path": "2018/15. already-applied",
    }, order_id="order-shared-01")
    (pending / "already-applied.json").write_text(
        json.dumps(order),
        encoding="utf-8",
    )
    (results / "order-shared-01.json").write_text(
        json.dumps({
            "schema_version": 1,
            "order_id": "order-shared-01",
            "status": "applied",
        }),
        encoding="utf-8",
    )

    assert service.load_pending_orders() == []


def test_generic_json_update_cannot_bypass_character_credential_validation(tmp_path):
    service, manager, dependent, structure_dir, credential = setup_order_service(tmp_path)
    relative = credential.relative_to(dependent).as_posix()
    order = make_order({
        "type": "update_dependent_json",
        "path": relative,
        "document": {"character_data": {"color_group": "rojo"}},
    }, order_id="order-cred-bypass")

    try:
        service.validate_order(order)
    except StructureOrderError as error:
        assert "update_character_credential" in str(error)
    else:
        raise AssertionError("Character credentials must use the character-aware operation")


def test_order_target_lookup_finds_character_outside_six_profile_ui_cache(tmp_path):
    service, manager, dependent, structure_dir, first_credential = setup_order_service(tmp_path)
    album_root = dependent / "2018" / "15. album"

    for index in range(2, 8):
        name = f"character_{index}"
        alterego = f"cure_{index}"
        folder = album_root / (
            f"15. {index:02d};{alterego};{name};2000-01-01;18"
        )
        folder.mkdir(parents=True)
        (folder / f"__{name}__.json").write_text(
            json.dumps({
                "character_data": {
                    "name": name,
                    "alterego": alterego,
                    "icon_path": "",
                    "background_path": "",
                    "color_group": "",
                    "secondary_color": "",
                }
            }),
            encoding="utf-8",
        )

    assert len(manager._cache["2018"]) == 1
    credential, character = service._find_character_credential({
        "year": 2018,
        "name": "character_7",
        "alterego": "cure_7",
    })

    assert credential.name == "__character_7__.json"
    assert character["name"] == "character_7"
    assert character["alterego"] == "cure_7"
    assert credential.is_file()
