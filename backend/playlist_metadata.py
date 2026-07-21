from typing import Any, Dict, Optional


def resolve_refresh_description(
    existing_description: Optional[str],
    generated_description: Optional[str],
    metadata_overrides: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Resolve the description that should be stored after a playlist refresh.

    Manual edits take precedence over regenerated AI descriptions so a user-edited
    title/description is not overwritten by later refreshes.
    """
    overrides = metadata_overrides or {}

    if overrides.get("description") and existing_description is not None:
        return existing_description

    if generated_description:
        return generated_description

    return existing_description
