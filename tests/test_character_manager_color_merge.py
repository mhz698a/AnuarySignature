from character_visor.character_manager import CharacterManager


def make_manager(tmp_path):
    return CharacterManager(
        base_path=tmp_path / "dependent",
        cache_path=tmp_path / "characters_cache.json",
        infrastructure_path=tmp_path / "infrastructure.json",
    )


def test_researched_structure_colors_fill_empty_legacy_credential_fields(tmp_path):
    manager = make_manager(tmp_path)
    manager._cache = {
        "2018": [
            {
                "name": "emiru_aisaki",
                "alterego": "cure_machérie",
                "color_group": "rojo",
                "secondary_color": "rosa",
            }
        ]
    }
    credential_data = {
        "name": "emiru_aisaki",
        "alterego": "cure_machérie",
        "color_group": "",
        "secondary_color": "",
    }

    cached = manager._find_cached_character(
        2018, "emiru_aisaki", "cure_machérie"
    )
    changed = manager._merge_cached_researched_colors(
        credential_data, cached
    )

    assert changed is True
    assert credential_data["color_group"] == "rojo"
    assert credential_data["secondary_color"] == "rosa"


def test_existing_non_empty_credential_colors_remain_authoritative(tmp_path):
    manager = make_manager(tmp_path)
    cached = {
        "name": "emiru_aisaki",
        "alterego": "cure_machérie",
        "color_group": "rojo",
        "secondary_color": "rosa",
    }
    credential_data = {
        "color_group": "magenta",
        "secondary_color": "blanco",
    }

    changed = manager._merge_cached_researched_colors(
        credential_data, cached
    )

    assert changed is False
    assert credential_data == {
        "color_group": "magenta",
        "secondary_color": "blanco",
    }


def test_cached_colors_are_not_applied_to_unrelated_characters(tmp_path):
    manager = make_manager(tmp_path)
    manager._cache = {
        "2018": [
            {
                "name": "emiru_aisaki",
                "alterego": "cure_machérie",
                "color_group": "rojo",
                "secondary_color": "rosa",
            }
        ]
    }

    cached = manager._find_cached_character(
        2018, "ruru_amour", "cure_amour"
    )

    assert cached is None
