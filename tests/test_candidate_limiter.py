from types import SimpleNamespace

from backend.services.candidate_limiter import (
    limit_candidates_for_ai,
    resolve_candidate_limit,
)


def _ai_client(provider_type: str):
    return SimpleNamespace(provider=SimpleNamespace(provider_type=provider_type))


def test_candidate_limiter_uses_recipe_limit_for_normal_provider():
    tracks = [
        {"id": "low", "play_count": 1},
        {"id": "high", "play_count": 20},
        {"id": "top", "play_count": 0, "is_top_track": True},
    ]

    result = limit_candidates_for_ai(
        tracks,
        {"max_candidate_tracks": 2},
        _ai_client("google"),
    )

    assert {track["id"] for track in result} == {"high", "top"}


def test_ollama_environment_limit_overrides_recipe(monkeypatch):
    monkeypatch.setenv("OLLAMA_MAX_TRACKS", "1")

    limit = resolve_candidate_limit(
        {"max_candidate_tracks": 100},
        _ai_client("ollama"),
    )

    assert limit == 1


def test_candidate_limiter_ignores_missing_or_invalid_limits(monkeypatch):
    monkeypatch.delenv("OLLAMA_MAX_TRACKS", raising=False)
    tracks = [{"id": "one"}, {"id": "two"}]

    assert resolve_candidate_limit({}, _ai_client("openrouter")) is None
    assert resolve_candidate_limit({"max_candidate_tracks": 0}, _ai_client("google")) is None
    assert limit_candidates_for_ai(tracks, {}, _ai_client("google")) == tracks
