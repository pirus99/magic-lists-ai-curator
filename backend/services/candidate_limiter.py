"""Shared post-filter candidate limits for AI curation requests."""
import os
from typing import Any, Dict, List, Optional

from .track_scoring_service import calculate_track_score


def resolve_candidate_limit(
    recipe: Dict[str, Any],
    ai_client: Optional[Any] = None,
) -> Optional[int]:
    """Resolve candidate limit precedence: Ollama env, then recipe value."""
    provider_type = getattr(getattr(ai_client, "provider", None), "provider_type", None)
    if provider_type == "ollama":
        ollama_limit = _positive_int(os.getenv("OLLAMA_MAX_TRACKS"))
        if ollama_limit is not None:
            return ollama_limit

    return _positive_int(recipe.get("max_candidate_tracks"))


def limit_candidates_for_ai(
    candidate_tracks: List[Dict[str, Any]],
    recipe: Dict[str, Any],
    ai_client: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Keep the highest-scoring candidates allowed by the resolved limit."""
    limit = resolve_candidate_limit(recipe, ai_client)
    if limit is None or len(candidate_tracks) <= limit:
        return candidate_tracks

    limited = sorted(candidate_tracks, key=calculate_track_score, reverse=True)[:limit]
    print(f"✂️ Candidate limiter: {len(candidate_tracks)} → {len(limited)} tracks before AI curation")
    return limited


def _positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
