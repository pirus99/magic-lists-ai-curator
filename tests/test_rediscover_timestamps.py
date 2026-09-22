import asyncio
from datetime import datetime, timedelta, timezone

from backend.rediscover import processor as rediscover_processor
from backend.rediscover.processor import ReDiscoverV2Processor


def test_parse_subsonic_datetime_handles_zulu_milliseconds_and_utc_strings():
    processor = ReDiscoverV2Processor(navidrome_client=None, ai_client=None, db_manager=None)

    dt = processor._parse_subsonic_datetime("2026-07-22T19:21:28.677Z")
    assert dt.tzinfo is not None
    assert dt.isoformat().endswith("+00:00")

    dt_no_tz = processor._parse_subsonic_datetime("2026-07-22T19:21:28.677")
    assert dt_no_tz.tzinfo is not None
    assert dt_no_tz.utcoffset() == timedelta(0)


def test_rediscovery_score_uses_real_days_since_play_not_default_30_days():
    processor = ReDiscoverV2Processor(navidrome_client=None, ai_client=None, db_manager=None)
    played_at = (datetime.now(timezone.utc) - timedelta(days=45)).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    candidates = processor._filter_and_enrich_candidates([
        {
            "id": "track-1",
            "title": "Example Song",
            "artist": "Example Artist",
            "playCount": 8,
            "played": played_at,
        }
    ], [])

    assert len(candidates) == 1
    assert candidates[0]["days_since_last_play"] >= 40
    assert candidates[0]["rediscovery_score"] > 0


def test_rediscover_phase_2_handles_string_genre_values(monkeypatch):
    processor = ReDiscoverV2Processor(navidrome_client=None, ai_client=None, db_manager=None)

    async def fake_curate(*args, **kwargs):
        return (["track-1"], "Selected for a late-night rediscovery arc")

    monkeypatch.setattr(rediscover_processor, "curate_rediscover_weekly", fake_curate)

    candidate = {
        "id": "track-1",
        "title": "Example Song",
        "artist": "Example Artist",
        "genres": ["Rock", "Indie Rock"],
        "year": 2005,
        "rediscovery_score": 42.5,
    }

    result = asyncio.run(processor._llm_phase2_sequencing([candidate], {"description": "Late-night mood"}))

    assert result[0]["id"] == "track-1"
    assert result[0]["ai_curated"] in (True, False)


def test_get_genres_cached_handles_string_lists():
    processor = ReDiscoverV2Processor(navidrome_client=None, ai_client=None, db_manager=None)

    class DummyDB:
        async def get_cache(self, key):
            return None

        async def set_cache(self, key, value, ttl):
            return None

    class DummyNavidrome:
        async def get_genres(self):
            return ["Rock", "Indie Rock / Pop", {"name": "Jazz"}]

    processor.db = DummyDB()
    processor.navidrome_client = DummyNavidrome()

    result = asyncio.run(processor._get_genres_cached("server-1"))

    assert "Rock" in result
    assert "Indie Rock" in result
    assert "Pop" in result
    assert "Jazz" in result
