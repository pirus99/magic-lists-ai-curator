"""Async HTTP client for ListenBrainz Labs recommendations."""
import os
from typing import Any, Dict, List, Optional

import httpx


class ListenBrainzClient:
    """Fetch and normalize similar artists and recordings from ListenBrainz Labs."""

    def __init__(self, client: Optional[httpx.AsyncClient] = None) -> None:
        self.base_url = os.getenv("LISTENBRAINZ_LABS_URL", "https://labs.api.listenbrainz.org").rstrip("/")
        self.token = os.getenv("LISTENBRAINZ_TOKEN")
        self.timeout = float(os.getenv("LISTENBRAINZ_TIMEOUT", "15"))
        self.client = client or httpx.AsyncClient(timeout=self.timeout)

    async def get_similar_artists(
        self,
        artist_mbid: str,
        algorithm: str,
        *,
        limit: int = 100,
        filter_artists: bool = True,
        skip: int = 30,
    ) -> List[Dict[str, Any]]:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        try:
            response = await self.client.get(
                f"{self.base_url}/similar-artists/json",
                params={
                    "artist_mbids": artist_mbid,
                    "algorithm": algorithm,
                    "limit": limit,
                    "filter": str(filter_artists).lower().capitalize(),
                    "skip": skip,
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("ListenBrainz request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"ListenBrainz returned HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Could not reach ListenBrainz: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("ListenBrainz returned invalid JSON") from exc

        if not isinstance(payload, list):
            raise RuntimeError("ListenBrainz returned an invalid response")
        artists = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            mbid, name, score = item.get("artist_mbid"), item.get("name"), item.get("score")
            if not mbid or not name or not isinstance(score, (int, float)):
                continue
            artists.append({
                "mbid": str(mbid),
                "name": str(name).strip(),
                "score": score,
                "comment": item.get("comment") or "",
                "type": item.get("type"),
            })
        return artists


    async def get_similar_recordings(
        self,
        recording_mbid: str,
        algorithm: str,
        *,
        limit: int = 100,
        filter_recordings: bool = True,
        skip: int = 30,
    ) -> List[Dict[str, Any]]:
        """Fetch and normalize similar recordings from ListenBrainz Labs.

        Uses the ``similar-recordings`` endpoint. The payload is a list of
        recordings, each carrying a MusicBrainz recording MBID, a title, an
        artist name, and a similarity score.
        """
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Token {self.token}"
        try:
            response = await self.client.get(
                f"{self.base_url}/similar-recordings/json",
                params={
                    "recording_mbids": recording_mbid,
                    "algorithm": algorithm,
                    "limit": limit,
                    "filter": str(filter_recordings).lower().capitalize(),
                    "skip": skip,
                },
                headers=headers,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise RuntimeError("ListenBrainz request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"ListenBrainz returned HTTP {exc.response.status_code}") from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Could not reach ListenBrainz: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError("ListenBrainz returned invalid JSON") from exc

        if not isinstance(payload, list):
            raise RuntimeError("ListenBrainz returned an invalid response")
        recordings = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            raw_mbid = item.get("recording_mbid")
            if raw_mbid is None:
                raw_mbid = item.get("mbid")
            if raw_mbid is None:
                continue
            mbid = str(raw_mbid).strip()
            if not mbid:
                continue
            # The similar-recordings endpoint uses ``recording_name`` and
            # ``artist_credit_name``; older/alternate payloads use ``name`` and
            # ``artist_name``.
            title = (
                item.get("recording_name")
                or item.get("name")
                or item.get("title")
            )
            if not title:
                continue
            title = str(title).strip()
            artist = (
                item.get("artist_credit_name")
                or item.get("artist_name")
                or item.get("artist")
            )
            if not artist:
                continue
            artist = str(artist).strip()
            score = item.get("score")
            if not isinstance(score, (int, float)):
                continue
            recordings.append({
                "mbid": mbid,
                "title": title,
                "artist": artist,
                "score": score,
                "comment": item.get("comment") or "",
                "type": item.get("type"),
                "release_name": item.get("release_name"),
            })
        return recordings
