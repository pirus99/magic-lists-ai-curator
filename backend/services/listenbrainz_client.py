"""Async HTTP client for ListenBrainz Labs recommendations."""
import os
from typing import Any, Dict, List, Optional

import httpx


class ListenBrainzClient:
    """Fetch and normalize similar artists from ListenBrainz Labs."""

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
