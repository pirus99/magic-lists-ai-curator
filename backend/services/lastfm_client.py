"""Async HTTP client for the Last.fm API."""
import os
from typing import Any, Dict, List, Optional

import httpx

DEFAULT_LASTFM_API_URL = "https://ws.audioscrobbler.com"


class LastFmClient:
    """Fetch artist top tracks and artist metadata from Last.fm."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self.base_url = os.getenv("LASTFM_API_URL", DEFAULT_LASTFM_API_URL).rstrip("/")
        self.api_key = os.getenv("LASTFM_API_KEY")
        self.timeout = float(os.getenv("LASTFM_TIMEOUT", "15"))
        self.client = client or httpx.AsyncClient(timeout=self.timeout)

    def is_configured(self) -> bool:
        """Return True when an API key is available for authenticated calls."""
        return bool(self.api_key)

    async def _call(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a Last.fm 2.0 JSON endpoint and return the ``result`` payload.

        Args:
            method: Last.fm API method name, e.g. ``artist.getTopTracks``.
            params: Additional query parameters for the method.

        Returns:
            The parsed ``result`` object from the response.

        Raises:
            RuntimeError: On timeout, transport failure, HTTP error, invalid JSON,
                a missing API key, or a Last.fm-level error payload.
        """
        if not self.api_key:
            raise RuntimeError("LASTFM_API_KEY is not configured")

        query: Dict[str, Any] = {
            "method": method,
            "api_key": self.api_key,
            "format": "json",
        }
        query.update({key: value for key, value in params.items() if value not in (None, "")})

        try:
            response = await self.client.get(f"{self.base_url}/2.0/", params=query)
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("Last.fm request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Last.fm returned HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Could not reach Last.fm: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("Last.fm returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Last.fm returned an invalid response")

        if "error" in payload:
            message = payload.get("message") or "Unknown error"
            raise RuntimeError(f"Last.fm error: {message}")

        result = payload.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Last.fm returned an unexpected response shape")

        return result

    async def get_top_tracks(
        self,
        artist_name: str,
        *,
        artist_mbid: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Fetch an artist's most popular tracks via ``artist.getTopTracks``.

        Args:
            artist_name: Artist name, used when no MBID is supplied.
            artist_mbid: Optional MusicBrainz ID, preferred over the name.
            limit: Maximum number of tracks to request.

        Returns:
            List of dicts with ``name``, ``artist``, ``mbid``, ``listeners``,
            ``playcount``, ``rank`` and ``url`` keys, in Last.fm rank order.
        """
        params: Dict[str, Any] = {"limit": max(1, min(500, limit))}
        if artist_mbid:
            params["mbid"] = artist_mbid
        elif artist_name:
            params["artist"] = artist_name
        else:
            return []

        result = await self._call("artist.getTopTracks", params)
        raw_tracks = result.get("toptracks", {}).get("track", [])
        if not isinstance(raw_tracks, list):
            raw_tracks = [raw_tracks] if raw_tracks else []

        tracks: List[Dict[str, Any]] = []
        for item in raw_tracks:
            if not isinstance(item, dict):
                continue
            title = item.get("name")
            if not title:
                continue
            artist = item.get("artist")
            artist_mbid = artist.get("mbid") if isinstance(artist, dict) else None
            if isinstance(artist, dict):
                artist = artist.get("name")
            tracks.append({
                "name": str(title).strip(),
                "artist": str(artist).strip() if artist else "",
                # Last.fm nests the artist MBID inside the artist object; fall back to
                # the track-level mbid when the artist object omits it.
                "mbid": artist_mbid or item.get("mbid") or None,
                "listeners": _as_int(item.get("listeners")),
                "playcount": _as_int(item.get("playcount")),
                "rank": _as_int(item.get("@attr", {}).get("rank")) if isinstance(item.get("@attr"), dict) else None,
                "url": item.get("url"),
            })
        return tracks

    async def get_artist_info(self, artist_name: str) -> Dict[str, Any]:
        """Fetch artist metadata via ``artist.getInfo``.

        Used as a name-to-MBID resolver for the 'This Is' manual artist fallback.
        ``autocorrect=1`` lets Last.fm resolve misspellings.

        Returns:
            Dict with ``name``, ``mbid``, ``url`` and ``tags`` keys.
        """
        if not artist_name:
            return {}

        result = await self._call("artist.getInfo", {
            "artist": artist_name,
            "autocorrect": 1,
        })
        artist = result.get("artist", {})
        if not isinstance(artist, dict):
            return {}

        tags = artist.get("tags", {}).get("tag", [])
        if not isinstance(tags, list):
            tags = [tags] if tags else []
        return {
            "name": artist.get("name") or artist_name,
            "mbid": artist.get("mbid") or None,
            "url": artist.get("url"),
            "tags": [
                str(tag.get("name", "")).strip()
                for tag in tags
                if isinstance(tag, dict) and tag.get("name")
            ],
        }

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self.client.aclose()


def _as_int(value: Any) -> Optional[int]:
    """Best-effort conversion to int, returning None for unusable values."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None