from backend.playlist_metadata import resolve_refresh_description
from backend.database.playlists import _safe_json_loads


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
