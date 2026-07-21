from backend.playlist_metadata import resolve_refresh_description


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
