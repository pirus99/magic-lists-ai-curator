import json

from backend.playlist_metadata import resolve_refresh_description
from backend.database.playlists import _safe_json_loads
from backend.recipe_manager import RecipeManager


def test_re_discover_phase1_recipe_replaces_all_input_placeholders():
    recipe_manager = RecipeManager(recipes_dir="recipes")
    inputs = {
        "tracks_found": 42,
        "top_genres": json.dumps({"Rock": 5, "Pop": 3}),
        "top_artists": json.dumps({"Artist A": 6}),
        "top_decades": json.dumps({"2000s": 10}),
        "avg_play_count": 12.4,
        "available_genres": json.dumps(["Rock", "Pop", "Jazz"]),
    }

    final_recipe = recipe_manager.apply_recipe("re_discover_phase1_v2", inputs)
    instructions = final_recipe["model_instructions"]

    assert "{{tracks_found}}" not in instructions
    assert "{{top_genres}}" not in instructions
    assert "{{top_artists}}" not in instructions
    assert "{{top_decades}}" not in instructions
    assert "{{avg_play_count}}" not in instructions
    assert "{{available_genres}}" not in instructions
    assert "42" in instructions
    assert "Rock" in instructions
    assert "2000s" in instructions


def test_manual_description_is_preserved_during_refresh():
    existing_description = "Manual playlist description"
    generated_description = "AI-generated description"

    result = resolve_refresh_description(
        existing_description=existing_description,
        generated_description=generated_description,
        metadata_overrides={"description": True},
    )

    assert result == existing_description


def test_generated_description_is_used_when_no_manual_override_exists():
    result = resolve_refresh_description(
        existing_description="Manual playlist description",
        generated_description="AI-generated description",
        metadata_overrides={},
    )

    assert result == "AI-generated description"


def test_safe_json_loads_handles_null_values_without_crashing():
    assert _safe_json_loads(None, []) == []
    assert _safe_json_loads(None, {}) == {}
    assert _safe_json_loads('[]', []) == []
    assert _safe_json_loads('{"x": 1}', {}) == {"x": 1}
