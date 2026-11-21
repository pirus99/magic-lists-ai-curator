"""Helpers for resolving playlist metadata across refreshes."""
from typing import Any, Dict, Optional


def description_refresh_enabled(curation_settings: Optional[Dict[str, Any]] = None) -> bool:
    """Return whether a refresh should regenerate the playlist description.

    The user controls this with the "Regenerate description on refresh"
    checkbox in the edit modal, persisted as ``refresh_description`` inside the
    playlist's ``curation_settings``. Playlists saved before the setting existed
    have no key and default to ``True`` (regenerate).
    """
    settings = curation_settings or {}
    value = settings.get("refresh_description")
    return True if value is None else bool(value)


def resolve_refresh_description(
    existing_description: Optional[str],
    generated_description: Optional[str],
    refresh_description: bool = True,
) -> Optional[str]:
    """Resolve the description that should be stored after a playlist refresh.

    When ``refresh_description`` is true the freshly generated AI description
    wins; otherwise the existing (possibly user-edited) description is kept.
    Either side may be empty, in which case the other one is used.
    """
    if refresh_description and generated_description:
        return generated_description

    if existing_description is not None:
        return existing_description

    return generated_description
