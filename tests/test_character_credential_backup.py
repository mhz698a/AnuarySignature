import json
from pathlib import Path

from engines.character_credential_backup import CharacterCredentialBackupService


def make_character(tmp_path, extension=".png"):
    dependent_root = tmp_path / "dependent"
    character_dir = (
        dependent_root / "2018" / "15. album"
        / "15. 01;cure_machérie;emiru_aisaki;2008-11-30;10"
    )
    character_dir.mkdir(parents=True)
    credential_path = character_dir / "__emiru_aisaki__.json"
    icon_path = character_dir / f"emiru_icon{extension}"
    background_path = character_dir / "background.jpg"

    credential_path.write_text(
        json.dumps({
            "character_data": {
                "year": 2018,
                "name": "emiru_aisaki",
                "alterego": "cure_machérie",
                "icon_path": icon_path.name,
                "background_path": background_path.name,
                "color_group": "rojo",
                "secondary_color": "rosa",
            }
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    icon_path.write_bytes(b"icon-image-content")
    background_path.write_bytes(b"background-image-content")

    return dependent_root, credential_path, icon_path, background_path, {
        "year": 2018,
        "name": "emiru_aisaki",
        "alterego": "cure_machérie",
        "character_json_path": str(credential_path),
        "icon_path": icon_path.name,
        "background_path": background_path.name,
    }


def make_service(tmp_path, dependent_root):
    structure_dir = tmp_path / "Structure" / "__structure__"
    (structure_dir.parent / ".git").mkdir(parents=True)
    structure_dir.mkdir(parents=True)
    return CharacterCredentialBackupService(
        dependent_root,
        structure_dir=structure_dir,
    )


def test_backup_contains_credential_and_selected_assets(tmp_path):
    dependent, credential, icon, background, character = make_character(tmp_path)
    service = make_service(tmp_path, dependent)

    result = service.backup_character(character)
    backup_dir = Path(result["backup_dir"])

    assert (backup_dir / "credential.json").read_bytes() == credential.read_bytes()
    assert (backup_dir / "icon.png").read_bytes() == icon.read_bytes()
    assert (backup_dir / "background.jpg").read_bytes() == background.read_bytes()

    manifest = json.loads(
        (backup_dir / "backup_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["character"]["alterego"] == "cure_machérie"
    assert manifest["credential"]["backup_path"] == "credential.json"
    assert manifest["assets"]["icon"]["backup_path"] == "icon.png"
    assert manifest["assets"]["background"]["backup_path"] == "background.jpg"


def test_changed_image_replaces_only_the_private_backup_copy(tmp_path):
    dependent, credential, old_icon, background, character = make_character(tmp_path, ".jpg")
    service = make_service(tmp_path, dependent)

    first_result = service.backup_character(character)
    backup_dir = Path(first_result["backup_dir"])
    old_backup = backup_dir / "icon.jpg"
    assert old_backup.is_file()

    new_icon = old_icon.with_suffix(".webp")
    new_icon.write_bytes(b"new-icon-image-content")
    character["icon_path"] = new_icon.name

    second_result = service.backup_character(character)

    assert (backup_dir / "icon.webp").read_bytes() == new_icon.read_bytes()
    assert not old_backup.exists()
    assert old_icon.is_file()
    assert new_icon.is_file()
    assert second_result["replaced_backup_copies"] == ["icon.jpg"]
    assert len(list(backup_dir.glob("icon.*"))) == 1


def test_missing_selected_image_does_not_delete_previous_backup(tmp_path):
    dependent, credential, icon, background, character = make_character(tmp_path)
    service = make_service(tmp_path, dependent)
    first_result = service.backup_character(character)
    backup_dir = Path(first_result["backup_dir"])
    previous_copy = backup_dir / "icon.png"

    character["icon_path"] = "missing-image.png"
    result = service.backup_character(character)

    assert previous_copy.is_file()
    assert result["warnings"]
    assert icon.is_file()


def test_backup_rejects_credential_outside_dependent_root(tmp_path):
    dependent = tmp_path / "dependent"
    dependent.mkdir()
    service = make_service(tmp_path, dependent)
    outside = tmp_path / "outside.json"
    outside.write_text(
        '{"character_data": {"name": "x"}}',
        encoding="utf-8",
    )

    try:
        service.backup_character({
            "year": 2018,
            "name": "x",
            "alterego": "x",
            "character_json_path": str(outside),
        })
    except Exception as error:
        assert "fuera de la unidad dependiente" in str(error)
    else:
        raise AssertionError("Expected a credential path validation failure")


def test_backup_requires_a_git_checkout(tmp_path):
    dependent, credential, icon, background, character = make_character(tmp_path)
    service = CharacterCredentialBackupService(
        dependent,
        structure_dir=tmp_path / "not-a-git-checkout",
    )

    try:
        service.backup_character(character)
    except Exception as error:
        assert "no está clonado correctamente" in str(error)
    else:
        raise AssertionError("Expected a local Structure checkout validation failure")



def test_backup_discovery_finds_all_disk_credentials_beyond_ui_cache_limit(tmp_path):
    dependent_root = tmp_path / "dependent"
    structure_dir = tmp_path / "Structure" / "__structure__"
    (structure_dir.parent / ".git").mkdir(parents=True)
    structure_dir.mkdir(parents=True)

    year_dir = dependent_root / "2018" / "15. album"
    for index in range(1, 9):
        character_name = f"character_{index}"
        alterego = f"cure_{index}"
        folder = year_dir / (
            f"15. {index:02d};{alterego};{character_name};2000-01-01;18"
        )
        folder.mkdir(parents=True)
        (folder / f"__{character_name}__.json").write_text(
            json.dumps({
                "character_data": {
                    "name": character_name,
                    "alterego": alterego,
                    "icon_path": "",
                    "background_path": "",
                }
            }),
            encoding="utf-8",
        )

    service = CharacterCredentialBackupService(
        dependent_root,
        structure_dir=structure_dir,
    )
    cached_subset = {
        "2018": [{"year": 2018, "name": "character_1", "alterego": "cure_1"}]
    }
    discovered, failures = service.discover_characters(cached_subset)

    assert len(discovered) == 8
    assert failures == []
    assert {item["name"] for item in discovered} == {
        f"character_{index}" for index in range(1, 9)
    }

    result = service.backup_all(cached_subset)
    assert result["discovered"] == 8
    assert result["backed_up"] == 8
    assert result["failed"] == 0


def test_clearing_selected_asset_removes_only_its_archive_copy(tmp_path):
    dependent, credential, icon, background, character = make_character(tmp_path)
    service = make_service(tmp_path, dependent)
    first = service.backup_character(character)
    backup_dir = Path(first["backup_dir"])
    archive_icon = backup_dir / "icon.png"

    character["icon_path"] = ""
    service.backup_character(character)

    assert not archive_icon.exists()
    assert icon.is_file()
    manifest = json.loads(
        (backup_dir / "backup_manifest.json").read_text(encoding="utf-8")
    )
    assert "icon" not in manifest["assets"]
