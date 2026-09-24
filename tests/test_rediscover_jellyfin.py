import asyncio
from datetime import datetime, timedelta, timezone

from backend.jellyfin import JellyfinClient
from backend.rediscover.processor import ReDiscoverV2Processor


def _jellyfin_processor():
    client = object.__new__(JellyfinClient)
    client.base_url = "https://jellyfin.example"
    client._user_id = "user-1"
    client.api_key = "api-key"
    client._auth_token = None
    client.username = None
    client.password = None
    return ReDiscoverV2Processor(client, ai_client=None, db_manager=None)


def test_jellyfin_sampling_uses_common_track_client():
    class _Client(JellyfinClient):
        async def get_recent_tracks(self, limit, library_ids):
            assert limit == 500
            assert library_ids == ["library-1"]
            return [{"id": "track-1", "played": "2026-07-01T00:00:00Z"}]

    client = object.__new__(_Client)
    client.base_url = "https://jellyfin.example"
    processor = ReDiscoverV2Processor(client, ai_client=None, db_manager=None)
    result = asyncio.run(processor._sample_library(500, ["library-1"]))

    assert result[0]["id"] == "track-1"


def test_jellyfin_generation_never_constructs_navidrome_smart_playlist_api():
    processor = _jellyfin_processor()

    class _DB:
        async def get_cache(self, key):
            return None

        async def set_cache(self, key, value, ttl):
            return None

    class _Client(JellyfinClient):
        async def get_library_stats(self):
            return {"total_tracks": 1000}

        async def get_recent_tracks(self, limit, library_ids):
            played = (datetime.now(timezone.utc) - timedelta(days=45)).isoformat()
            return [
                {
                    "id": f"track-{index}",
                    "title": f"Track {index}",
                    "artist": f"Artist {index}",
                    "genres": ["Rock"],
                    "play_count": 4,
                    "played": played,
                }
                for index in range(15)
            ]

        async def get_tracks_by_genre(self, genre, library_ids):
            return []

        async def get_starred(self):
            return []

    client = object.__new__(_Client)
    client.base_url = "https://jellyfin.example"
    client._user_id = "user-1"
    client.api_key = "api-key"
    client._auth_token = None
    client.username = None
    client.password = None

    processor.db = _DB()
    processor.navidrome_client = client
    processor._smart_playlist_api = None
    processor._get_smart_playlist_api = lambda: (_ for _ in ()).throw(
        AssertionError("Jellyfin must not use Navidrome smart-playlist login")
    )
    processor._llm_phase1_theme_detection = _async_return({
        "theme_identified": "Rock",
        "search_strategy": {"include_genres": ["Rock"]},
        "description": "Rock rediscoveries",
    })
    processor._llm_phase2_sequencing = _async_return([
        {
            "id": f"track-{index}",
            "title": f"Track {index}",
            "ai_curated": False,
            "ai_description": "Algorithmic selection",
        }
        for index in range(15)
    ])

    result = asyncio.run(processor.generate_playlist("user-1", "jellyfin"))

    assert len(result["tracks"]) == 15
    assert result["used_smart_playlist"] is False


def test_jellyfin_recent_track_preserves_date_last_played():
    client = _jellyfin_processor().navidrome_client
    normalized = client._normalize_track({
        "Id": "track-1",
        "Name": "Example",
        "Artists": ["Artist"],
        "DateLastPlayed": "2026-07-01T12:00:00Z",
    })

    assert normalized["id"] == "track-1"
    assert normalized["artist"] == "Artist"
    assert normalized["played"] == "2026-07-01T12:00:00Z"


def _async_return(value):
    async def _return(*args, **kwargs):
        return value
    return _return
