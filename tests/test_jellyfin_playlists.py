import asyncio

from backend.jellyfin import JellyfinClient


class _Response:
    def __init__(self):
        self.status_code = 204

    def raise_for_status(self):
        return None


class _HttpClient:
    def __init__(self):
        self.calls = []

    async def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return _Response()

    async def delete(self, url, **kwargs):
        self.calls.append(("DELETE", url, kwargs))
        return _Response()


def _client():
    client = object.__new__(JellyfinClient)
    client.base_url = "https://jellyfin.example"
    client.client = _HttpClient()
    client.api_key = "api-key"
    client.username = None
    client.password = None
    client._auth_token = None
    client._user_id = None
    return client


def test_jellyfin_delete_uses_generic_item_endpoint():
    client = _client()

    assert asyncio.run(client.delete_playlist("playlist-id")) is True
    assert client.client.calls == [
        (
            "DELETE",
            "https://jellyfin.example/Items/playlist-id",
            {"headers": {"Authorization": client._get_auth_headers()["Authorization"]}},
        )
    ]


def test_jellyfin_refresh_replaces_track_ids():
    client = _client()

    assert asyncio.run(
        client.update_playlist("playlist-id", ["track-1", "track-2"])
    ) is True
    assert client.client.calls == [
        (
            "POST",
            "https://jellyfin.example/Playlists/playlist-id",
            {
                "headers": {"Authorization": client._get_auth_headers()["Authorization"]},
                "json": {"Ids": ["track-1", "track-2"]},
            },
        )
    ]


def test_jellyfin_edit_can_clear_description_and_visibility():
    client = _client()

    assert asyncio.run(
        client.update_playlist_metadata(
            "playlist-id",
            name="",
            comment="",
            is_public=False,
        )
    ) is True
    method, url, kwargs = client.client.calls[0]
    assert (method, url) == (
        "POST",
        "https://jellyfin.example/Playlists/playlist-id",
    )
    assert kwargs["json"] == {"Name": "", "IsPublic": False}

    method, url, kwargs = client.client.calls[1]
    assert (method, url) == (
        "POST",
        "https://jellyfin.example/Items/playlist-id",
    )
    assert kwargs["json"] == {"Overview": ""}
    assert "params" not in kwargs
