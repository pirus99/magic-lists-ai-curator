"""Re-Discover Weekly v2.0 processor (two-phase AI curation)."""
import json
import random
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from ..config import NAVIDROME_URL, NAVIDROME_USERNAME, NAVIDROME_PASSWORD
from ..recipe_manager import recipe_manager
from .curation import curate_rediscover_weekly
from ..navidrome.smart_playlist import SmartPlaylistAPI


class ReDiscoverV2Processor:
    """Re-Discover Weekly v2.0 - Uses OpenSubsonic API's played timestamps
    for temporal analysis and two-phase AI collaboration.
    """

    def __init__(self, navidrome_client, ai_client, db_manager):
        self.navidrome_client = navidrome_client
        self.ai_client = ai_client
        self.db = db_manager
        self.config = {
            "track_count": 25,
            "target_period_days_start": 90,
            "target_period_days_end": 30,
            "exclude_played_within_days": 30,
            "max_tracks_per_artist": 2,
            "min_target_period_tracks": 10,
            "genre_cache_hours": 24,
            "enable_fallback": True,
            # Smart-playlist target discovery settings
            "use_smart_playlist_target": True,
            "target_playlist_name": "magiclists-rediscover-targets",
            "target_playlist_limit": 1000,
        }
        self._smart_playlist_api: Optional[SmartPlaylistAPI] = None

    def _get_smart_playlist_api(self) -> SmartPlaylistAPI:
        """Get or create the SmartPlaylistAPI instance."""
        if self._smart_playlist_api is None:
            base_url = getattr(self.navidrome_client, "base_url", NAVIDROME_URL)
            client = getattr(self.navidrome_client, "client", None)
            if client is None:
                import httpx
                client = httpx.AsyncClient()
            self._smart_playlist_api = SmartPlaylistAPI(client, base_url)
        return self._smart_playlist_api

    async def generate_playlist(self, user_id: str, server_id: str, library_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Main entry point for Re-Discover Weekly v2.0 generation.

        Uses Navidrome smart-playlist criteria to directly query tracks
        last played 30-90 days ago, avoiding the need to fetch the
        entire library. Falls back to random sampling if smart-playlist
        fails or returns insufficient results.
        """
        try:
            print(f"🎵 Re-Discover Weekly v2.0: Starting generation for user {user_id}, server {server_id}")

            print("📊 Phase 0: Gathering context...")
            library_size = await self._get_library_size_cached(server_id)
            print(f"📊 Library size: {library_size} tracks")

            genres = await self._get_genres_cached(server_id)
            print(f"📊 Found {len(genres)} unique genres")

            print("🔍 Phase 1: Analyzing listening patterns...")

            # Use smart-playlist target discovery if enabled
            target_tracks = []
            used_smart_playlist = False

            if self.config.get("use_smart_playlist_target", True):
                print("🔍 Using Navidrome smart-playlist for exact 30-90 day target discovery...")
                target_tracks = await self._get_target_tracks_smart_playlist(
                    days_start=self.config["target_period_days_start"],
                    days_end=self.config["target_period_days_end"],
                    limit=self.config["target_playlist_limit"],
                )
                if target_tracks:
                    used_smart_playlist = True
                    print(f"🔍 Found {len(target_tracks)} tracks in target period (30-90 days ago) via smart playlist")

            # Fallback to random sampling if smart-playlist failed or returned too few
            if not target_tracks or len(target_tracks) < self.config["min_target_period_tracks"]:
                if self.config.get("use_smart_playlist_target", True):
                    print(f"⚠️ Smart-playlist returned {len(target_tracks)} tracks, falling back to random sampling...")
                sample_size = self._calculate_sample_size(library_size)
                print(f"📊 Calculated sample size: {sample_size} tracks")
                sample_tracks = await self._sample_library(sample_size, library_ids)
                print(f"🔍 Sampled {len(sample_tracks)} tracks from library")
                target_tracks = self._filter_to_target_period(sample_tracks)
                print(f"🔍 Found {len(target_tracks)} tracks in target period (30-90 days ago) via sampling")

            if len(target_tracks) < self.config["min_target_period_tracks"]:
                print(f"⚠️ Only {len(target_tracks)} target tracks found (minimum: {self.config['min_target_period_tracks']})")
                print("🔄 Triggering fallback strategy...")
                return await self._trigger_fallback(user_id, server_id, library_ids)

            analysis = self._analyze_target_period(target_tracks)
            theme_strategy = await self._llm_phase1_theme_detection(analysis, genres)

            search_results = await self._execute_searches(theme_strategy, library_ids)
            candidates = self._filter_and_enrich_candidates(search_results, target_tracks)
            final_tracks = await self._llm_phase2_sequencing(candidates, theme_strategy)

            playlist_data = await self._create_playlist_data(final_tracks, theme_strategy, user_id, server_id, used_smart_playlist)
            await self._log_to_database_v2(playlist_data, theme_strategy, len(target_tracks))

            return playlist_data

        except Exception as e:
            raise Exception(f"Re-Discover Weekly v2.0 failed: {e}")

    async def _get_library_size_cached(self, server_id: str) -> int:
        """Get library size with caching."""
        cache_key = f"library_size:{server_id}"
        cached = await self.db.get_cache(cache_key)
        if cached:
            return int(cached)

        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getScanStatus.view",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            count = data.get("subsonic-response", {}).get("scanStatus", {}).get("count", 0)
            await self.db.set_cache(cache_key, str(count), 86400)
            return count
        except Exception:
            return 1000

    async def _get_genres_cached(self, server_id: str) -> List[str]:
        """Get genres with caching."""
        cache_key = f"genres:{server_id}"
        cached = await self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            genres = await self.navidrome_client.get_genres()
            genre_names = [g.get("value", g.get("name", "")) for g in genres if g.get("value", g.get("name", ""))]
            await self.db.set_cache(cache_key, json.dumps(genre_names), 86400)
            return genre_names
        except Exception:
            return ["Rock", "Pop", "Electronic", "Jazz", "Classical"]

    def _calculate_sample_size(self, library_size: int) -> int:
        """Calculate optimal sample size based on library size."""
        percentage_based = int(library_size * self.config["sample_size_percentage"])
        return min(max(percentage_based, self.config["sample_size_min"]), self.config["sample_size_max"])

    async def _sample_library(self, sample_size: int, library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Sample random tracks from the library using OpenSubsonic getRandomSongs."""
        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            params["size"] = str(sample_size)
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]

            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getRandomSongs.view",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            songs = data.get("subsonic-response", {}).get("randomSongs", {}).get("song", [])
            return songs if isinstance(songs, list) else []
        except Exception as e:
            print(f"❌ Failed to sample library: {e}")
            return []

    def _filter_to_target_period(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter tracks to those played in the target period (30-90 days ago)."""
        now = datetime.now(timezone.utc)
        target_tracks = []
        tracks_with_timestamps = 0
        tracks_in_range = 0

        print(f"🔍 Filtering {len(tracks)} tracks for target period ({self.config['target_period_days_end']}-{self.config['target_period_days_start']} days ago)...")

        for track in tracks:
            played_str = track.get("played")
            if not played_str:
                continue
            tracks_with_timestamps += 1
            try:
                if played_str.endswith("Z"):
                    played_str = played_str[:-1] + "+00:00"
                played = datetime.fromisoformat(played_str)
                days_ago = (now - played).days
                if tracks_in_range < 3:
                    print(f"🔍 Track '{track.get('title', 'Unknown')}' played {days_ago} days ago")
                if self.config["target_period_days_end"] <= days_ago <= self.config["target_period_days_start"]:
                    track["played_datetime"] = played
                    track["days_ago"] = days_ago
                    target_tracks.append(track)
                    tracks_in_range += 1
            except (ValueError, TypeError) as e:
                print(f"⚠️ Failed to parse timestamp '{played_str}' for track '{track.get('title', 'Unknown')}': {e}")
                continue

        print(f"🔍 Summary: {tracks_with_timestamps} tracks had timestamps, {tracks_in_range} in target range")
        return target_tracks

    def _analyze_target_period(self, target_tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze the target period tracks to understand listening patterns."""
        if not target_tracks:
            return {"tracks_found": 0}

        genre_counts = {}
        for track in target_tracks:
            genres = track.get("genres", [])
            if isinstance(genres, list):
                for genre_obj in genres:
                    if isinstance(genre_obj, dict) and "name" in genre_obj:
                        genre_counts[genre_obj["name"]] += 1
            elif isinstance(genres, str):
                genre_counts[genres] += 1

        artist_counts = {}
        for track in target_tracks:
            artist_counts[track.get("artist", "Unknown")] = artist_counts.get(track.get("artist", "Unknown"), 0) + 1

        decades = {}
        for track in target_tracks:
            year = track.get("year", 2000)
            if year and isinstance(year, int):
                decade = (year // 10) * 10
                decades[decade] = decades.get(decade, 0) + 1

        play_counts = [track.get("playCount", 0) for track in target_tracks]

        return {
            "tracks_found": len(target_tracks),
            "top_genres": dict(genre_counts.most_common(5)),
            "top_artists": dict(artist_counts.most_common(5)),
            "top_decades": dict(decades.most_common(3)),
            "avg_play_count": sum(play_counts) / len(play_counts) if play_counts else 0,
            "date_range": {
                "oldest": min((t["played_datetime"] for t in target_tracks), default=None),
                "newest": max((t["played_datetime"] for t in target_tracks), default=None),
            },
        }

    async def _llm_phase1_theme_detection(self, analysis: Dict[str, Any], available_genres: List[str]) -> Dict[str, Any]:
        """Phase 1 AI: Analyze listening patterns and select curation strategy."""
        recipe_inputs = {
            "tracks_found": analysis["tracks_found"],
            "top_genres": json.dumps(analysis.get("top_genres", {})),
            "top_artists": json.dumps(analysis.get("top_artists", {})),
            "top_decades": json.dumps(analysis.get("top_decades", {})),
            "avg_play_count": round(analysis.get("avg_play_count", 0), 1),
            "available_genres": json.dumps(available_genres[:20]),
        }

        try:
            final_recipe = recipe_manager.apply_recipe("re_discover_phase1_v2", recipe_inputs)
            if "llm_config" in final_recipe:
                llm_config = final_recipe.get("llm_config", {})
                model_instructions = final_recipe.get("model_instructions", "")
                model = self.ai_client.model or llm_config.get("model_fallback", "openai/gpt-3.5-turbo")
                temperature = llm_config.get("temperature", 0.7)
                max_tokens = llm_config.get("max_output_tokens", 1500)

                print(f"🤖 Making Phase 1 AI call with model {model}...")

                ai_result = await self.ai_client.provider.generate(
                    system_prompt="You are an expert music curator analyzing listening patterns.",
                    user_prompt=model_instructions,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                try:
                    cleaned_content = ai_result.strip()
                    if cleaned_content.startswith("```json"):
                        cleaned_content = cleaned_content[7:]
                    if cleaned_content.startswith("```"):
                        cleaned_content = cleaned_content[3:]
                    if cleaned_content.endswith("```"):
                        cleaned_content = cleaned_content[:-3]
                    cleaned_content = cleaned_content.strip()

                    json_object_match = re.search(r"\{.*\}", cleaned_content, re.DOTALL)
                    if json_object_match:
                        json_str = json_object_match.group(0)
                    else:
                        json_str = cleaned_content

                    lines = json_str.split("\n")
                    cleaned_lines = []
                    for line in lines:
                        if "//" in line and "http://" not in line and "https://" not in line:
                            comment_pos = line.find("//")
                            line = line[:comment_pos].rstrip()
                        line = re.sub(r",(\s*[\]}])", r"\1", line)
                        if line.strip():
                            cleaned_lines.append(line)

                    final_json = "\n".join(cleaned_lines).strip()
                    strategy = json.loads(final_json)
                    return strategy
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse Phase 1 AI response as JSON: {e}")
                    print(f"🔍 Raw response: {ai_result}")
        except Exception as e:
            print(f"❌ Phase 1 AI failed: {e}")

        return {
            "selected_mode": "A",
            "mode_rationale": "AI analysis failed, using fallback strategy",
            "theme_identified": "Mixed favorites",
            "primary_genres": list(analysis.get("top_genres", {}).keys())[:3],
            "primary_decade": "2000s",
            "mood_keywords": ["nostalgic", "favorite"],
            "search_strategy": {
                "include_genres": list(analysis.get("top_genres", {}).keys())[:3],
                "include_decades": ["2000s", "2010s"],
                "play_count_min": 2,
                "play_count_max": 15,
                "exclude_played_within_days": 30,
                "prioritize_starred": True,
            },
            "description": "Fallback strategy due to AI unavailability",
        }

    async def _execute_searches(self, theme_strategy: Dict[str, Any], library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Execute targeted searches based on AI strategy."""
        search_results = []
        strategy = theme_strategy.get("search_strategy", {})

        include_genres = strategy.get("include_genres", [])
        for genre in include_genres[:3]:
            try:
                tracks = await self.navidrome_client.get_tracks_by_genre(genre, library_ids)
                search_results.extend(tracks)
            except Exception as e:
                print(f"⚠️ Genre search failed for {genre}: {e}")

        include_decades = strategy.get("include_decades", [])
        for decade in include_decades[:2]:
            try:
                if isinstance(decade, str) and decade.endswith("s"):
                    start_year = int(decade[:-1])
                else:
                    start_year = int(decade)
                end_year = start_year + 9
                tracks = await self._search_by_year_range(start_year, end_year, library_ids)
                search_results.extend(tracks)
            except Exception as e:
                print(f"⚠️ Decade search failed for {decade}: {e}")

        if strategy.get("prioritize_starred", False):
            try:
                starred = await self.navidrome_client.get_starred()
                search_results.extend(starred)
            except Exception as e:
                print(f"⚠️ Starred tracks search failed: {e}")

        return search_results

    async def _search_by_year_range(self, start_year: int, end_year: int, library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search for tracks in a specific year range."""
        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            params["size"] = "200"
            params["fromYear"] = str(start_year)
            params["toYear"] = str(end_year)
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]

            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getRandomSongs.view",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            songs = data.get("subsonic-response", {}).get("randomSongs", {}).get("song", [])
            return songs if isinstance(songs, list) else []
        except Exception as e:
            print(f"❌ Year range search failed: {e}")
            return []

    def _filter_and_enrich_candidates(self, search_results: List[Dict[str, Any]], target_tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter search results and calculate rediscovery scores."""
        candidates = []
        now = datetime.now(timezone.utc)
        exclude_before = now - timedelta(days=self.config["exclude_played_within_days"])
        target_track_ids = {t["id"] for t in target_tracks}

        for track in search_results:
            track_id = track.get("id")
            if not track_id:
                continue
            played_str = track.get("played")
            if played_str:
                try:
                    if played_str.endswith("Z"):
                        played_str = played_str[:-1] + "+00:00"
                    played = datetime.fromisoformat(played_str)
                    if played > exclude_before:
                        continue
                except Exception:
                    pass

            play_count = track.get("playCount", 0)
            days_since_play = 30
            if played_str:
                try:
                    if played_str.endswith("Z"):
                        played_str = played_str[:-1] + "+00:00"
                    played = datetime.fromisoformat(played_str)
                    days_since_play = (now - played).days
                except Exception:
                    pass

            rediscovery_score = play_count * (1 + days_since_play ** 0.5) * random.uniform(0.8, 1.2)
            was_in_target_period = track_id in target_track_ids

            candidate = {
                **track,
                "rediscovery_score": rediscovery_score,
                "days_since_last_play": days_since_play,
                "was_in_target_period": was_in_target_period,
            }
            candidates.append(candidate)

        candidates.sort(key=lambda x: x["rediscovery_score"], reverse=True)
        return candidates[:100]

    async def _llm_phase2_sequencing(self, candidates: List[Dict[str, Any]], theme_strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Phase 2 AI: Sequence exactly 25 tracks for optimal playlist flow."""
        ai_candidates = []
        for track in candidates[:80]:
            ai_candidates.append({
                "id": track["id"],
                "title": track.get("title", ""),
                "artist": track.get("artist", ""),
                "album": track.get("album", ""),
                "genres": [g.get("name", "") for g in track.get("genres", [])] if isinstance(track.get("genres"), list) else [],
                "year": track.get("year", 2000),
                "play_count": track.get("playCount", 0),
                "days_since_last_play": track.get("days_since_last_play", 30),
                "rediscovery_score": round(track.get("rediscovery_score", 0), 2),
                "was_in_target_period": track.get("was_in_target_period", False),
            })

        recipe_inputs = {
            "theme_strategy": json.dumps(theme_strategy),
            "candidate_tracks": json.dumps(ai_candidates),
            "num_tracks": self.config["track_count"],
        }

        try:
            ai_result = await curate_rediscover_weekly(
                ai_client=self.ai_client,
                candidate_tracks=ai_candidates,
                analysis_summary="",
                num_tracks=self.config["track_count"],
                include_description=True,
                variety_context=json.dumps(theme_strategy) if theme_strategy else None,
            )

            if isinstance(ai_result, tuple):
                track_ids, description = ai_result
            else:
                track_ids = ai_result
                description = ""

            final_tracks = []
            for track_id in track_ids:
                candidate = next((c for c in ai_candidates if c["id"] == track_id), None)
                if candidate:
                    final_tracks.append({
                        **candidate,
                        "ai_curated": True,
                        "ai_description": description,
                    })

            if len(final_tracks) == self.config["track_count"]:
                return final_tracks
        except Exception as e:
            print(f"❌ Phase 2 AI failed: {e}")
            theme_strategy["description"] = "Fallback strategy due to AI unavailability"

        top_candidates = candidates[: self.config["track_count"]]
        return [{
            **track,
            "ai_curated": False,
            "ai_description": "Algorithmic selection (AI not available)",
        } for track in top_candidates]

    async def _get_target_tracks_smart_playlist(
        self,
        days_start: int = 90,
        days_end: int = 30,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get target period tracks using Navidrome smart-playlist criteria.

        Creates a temporary smart playlist with lastPlayed inTheRange
        criteria, retrieves matching tracks, then cleans up the playlist.

        This avoids fetching the entire library and provides exact
        30-90 day target period filtering server-side.

        Args:
            days_start: Start of target period in days (larger = older)
            days_end: End of target period in days (smaller = newer)
            limit: Maximum tracks to retrieve

        Returns:
            List of tracks last played between days_end and days_start ago
        """
        api = self._get_smart_playlist_api()
        tracks = await api.get_target_tracks_direct(
            days_start=days_start,
            days_end=days_end,
            limit=limit,
        )
        return tracks

    async def _get_library_size_cached(self, server_id: str) -> int:
        """Get library size with caching."""
        cache_key = f"library_size:{server_id}"
        cached = await self.db.get_cache(cache_key)
        if cached:
            return int(cached)

        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getScanStatus.view",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            count = data.get("subsonic-response", {}).get("scanStatus", {}).get("count", 0)
            await self.db.set_cache(cache_key, str(count), 86400)
            return count
        except Exception:
            return 1000

    async def _get_genres_cached(self, server_id: str) -> List[str]:
        """Get genres with caching."""
        cache_key = f"genres:{server_id}"
        cached = await self.db.get_cache(cache_key)
        if cached:
            return json.loads(cached)

        try:
            genres = await self.navidrome_client.get_genres()
            genre_names = [g.get("value", g.get("name", "")) for g in genres if g.get("value", g.get("name", ""))]
            await self.db.set_cache(cache_key, json.dumps(genre_names), 86400)
            return genre_names
        except Exception:
            return ["Rock", "Pop", "Electronic", "Jazz", "Classical"]

    def _calculate_sample_size(self, library_size: int) -> int:
        """Calculate optimal sample size based on library size."""
        percentage_based = int(library_size * self.config["sample_size_percentage"])
        return min(max(percentage_based, self.config["sample_size_min"]), self.config["sample_size_max"])

    async def _sample_library(self, sample_size: int, library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Sample random tracks from the library using OpenSubsonic getRandomSongs."""
        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            params["size"] = str(sample_size)
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]

            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getRandomSongs.view",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            songs = data.get("subsonic-response", {}).get("randomSongs", {}).get("song", [])
            return songs if isinstance(songs, list) else []
        except Exception as e:
            print(f"❌ Failed to sample library: {e}")
            return []

    def _filter_to_target_period(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter tracks to those played in the target period (30-90 days ago)."""
        now = datetime.now(timezone.utc)
        target_tracks = []
        tracks_with_timestamps = 0
        tracks_in_range = 0

        print(f"🔍 Filtering {len(tracks)} tracks for target period ({self.config['target_period_days_end']}-{self.config['target_period_days_start']} days ago)...")

        for track in tracks:
            played_str = track.get("played")
            if not played_str:
                continue
            tracks_with_timestamps += 1
            try:
                if played_str.endswith("Z"):
                    played_str = played_str[:-1] + "+00:00"
                played = datetime.fromisoformat(played_str)
                days_ago = (now - played).days
                if tracks_in_range < 3:
                    print(f"🔍 Track '{track.get('title', 'Unknown')}' played {days_ago} days ago")
                if self.config["target_period_days_end"] <= days_ago <= self.config["target_period_days_start"]:
                    track["played_datetime"] = played
                    track["days_ago"] = days_ago
                    target_tracks.append(track)
                    tracks_in_range += 1
            except (ValueError, TypeError) as e:
                print(f"⚠️ Failed to parse timestamp '{played_str}' for track '{track.get('title', 'Unknown')}': {e}")
                continue

        print(f"🔍 Summary: {tracks_with_timestamps} tracks had timestamps, {tracks_in_range} in target range")
        return target_tracks

    def _analyze_target_period(self, target_tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze the target period tracks to understand listening patterns."""
        if not target_tracks:
            return {"tracks_found": 0}

        genre_counts = {}
        for track in target_tracks:
            genres = track.get("genres", [])
            if isinstance(genres, list):
                for genre_obj in genres:
                    if isinstance(genre_obj, dict) and "name" in genre_obj:
                        genre_counts[genre_obj["name"]] += 1
            elif isinstance(genres, str):
                genre_counts[genres] += 1

        artist_counts = {}
        for track in target_tracks:
            artist_counts[track.get("artist", "Unknown")] = artist_counts.get(track.get("artist", "Unknown"), 0) + 1

        decades = {}
        for track in target_tracks:
            year = track.get("year", 2000)
            if year and isinstance(year, int):
                decade = (year // 10) * 10
                decades[decade] = decades.get(decade, 0) + 1

        play_counts = [track.get("playCount", 0) for track in target_tracks]

        return {
            "tracks_found": len(target_tracks),
            "top_genres": dict(genre_counts.most_common(5)),
            "top_artists": dict(artist_counts.most_common(5)),
            "top_decades": dict(decades.most_common(3)),
            "avg_play_count": sum(play_counts) / len(play_counts) if play_counts else 0,
            "date_range": {
                "oldest": min((t["played_datetime"] for t in target_tracks), default=None),
                "newest": max((t["played_datetime"] for t in target_tracks), default=None),
            },
        }

    async def _llm_phase1_theme_detection(self, analysis: Dict[str, Any], available_genres: List[str]) -> Dict[str, Any]:
        """Phase 1 AI: Analyze listening patterns and select curation strategy."""
        recipe_inputs = {
            "tracks_found": analysis["tracks_found"],
            "top_genres": json.dumps(analysis.get("top_genres", {})),
            "top_artists": json.dumps(analysis.get("top_artists", {})),
            "top_decades": json.dumps(analysis.get("top_decades", {})),
            "avg_play_count": round(analysis.get("avg_play_count", 0), 1),
            "available_genres": json.dumps(available_genres[:20]),
        }

        try:
            final_recipe = recipe_manager.apply_recipe("re_discover_phase1_v2", recipe_inputs)
            if "llm_config" in final_recipe:
                llm_config = final_recipe.get("llm_config", {})
                model_instructions = final_recipe.get("model_instructions", "")
                model = self.ai_client.model or llm_config.get("model_fallback", "openai/gpt-3.5-turbo")
                temperature = llm_config.get("temperature", 0.7)
                max_tokens = llm_config.get("max_output_tokens", 1500)

                print(f"🤖 Making Phase 1 AI call with model {model}...")

                ai_result = await self.ai_client.provider.generate(
                    system_prompt="You are an expert music curator analyzing listening patterns.",
                    user_prompt=model_instructions,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                try:
                    cleaned_content = ai_result.strip()
                    if cleaned_content.startswith("```json"):
                        cleaned_content = cleaned_content[7:]
                    if cleaned_content.startswith("```"):
                        cleaned_content = cleaned_content[3:]
                    if cleaned_content.endswith("```"):
                        cleaned_content = cleaned_content[:-3]
                    cleaned_content = cleaned_content.strip()

                    json_object_match = re.search(r"\{.*\}", cleaned_content, re.DOTALL)
                    if json_object_match:
                        json_str = json_object_match.group(0)
                    else:
                        json_str = cleaned_content

                    lines = json_str.split("\n")
                    cleaned_lines = []
                    for line in lines:
                        if "//" in line and "http://" not in line and "https://" not in line:
                            comment_pos = line.find("//")
                            line = line[:comment_pos].rstrip()
                        line = re.sub(r",(\s*[\]}])", r"\1", line)
                        if line.strip():
                            cleaned_lines.append(line)

                    final_json = "\n".join(cleaned_lines).strip()
                    strategy = json.loads(final_json)
                    return strategy
                except json.JSONDecodeError as e:
                    print(f"❌ Failed to parse Phase 1 AI response as JSON: {e}")
                    print(f"🔍 Raw response: {ai_result}")
        except Exception as e:
            print(f"❌ Phase 1 AI failed: {e}")

        return {
            "selected_mode": "A",
            "mode_rationale": "AI analysis failed, using fallback strategy",
            "theme_identified": "Mixed favorites",
            "primary_genres": list(analysis.get("top_genres", {}).keys())[:3],
            "primary_decade": "2000s",
            "mood_keywords": ["nostalgic", "favorite"],
            "search_strategy": {
                "include_genres": list(analysis.get("top_genres", {}).keys())[:3],
                "include_decades": ["2000s", "2010s"],
                "play_count_min": 2,
                "play_count_max": 15,
                "exclude_played_within_days": 30,
                "prioritize_starred": True,
            },
            "description": "Fallback strategy due to AI unavailability",
        }

    async def _execute_searches(self, theme_strategy: Dict[str, Any], library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Execute targeted searches based on AI strategy."""
        search_results = []
        strategy = theme_strategy.get("search_strategy", {})

        include_genres = strategy.get("include_genres", [])
        for genre in include_genres[:3]:
            try:
                tracks = await self.navidrome_client.get_tracks_by_genre(genre, library_ids)
                search_results.extend(tracks)
            except Exception as e:
                print(f"⚠️ Genre search failed for {genre}: {e}")

        include_decades = strategy.get("include_decades", [])
        for decade in include_decades[:2]:
            try:
                if isinstance(decade, str) and decade.endswith("s"):
                    start_year = int(decade[:-1])
                else:
                    start_year = int(decade)
                end_year = start_year + 9
                tracks = await self._search_by_year_range(start_year, end_year, library_ids)
                search_results.extend(tracks)
            except Exception as e:
                print(f"⚠️ Decade search failed for {decade}: {e}")

        if strategy.get("prioritize_starred", False):
            try:
                starred = await self.navidrome_client.get_starred()
                search_results.extend(starred)
            except Exception as e:
                print(f"⚠️ Starred tracks search failed: {e}")

        return search_results

    async def _search_by_year_range(self, start_year: int, end_year: int, library_ids: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Search for tracks in a specific year range."""
        try:
            await self.navidrome_client._ensure_authenticated()
            params = self.navidrome_client._get_subsonic_params()
            params["size"] = "200"
            params["fromYear"] = str(start_year)
            params["toYear"] = str(end_year)
            if library_ids and len(library_ids) > 0:
                params["musicFolderId"] = library_ids[0]

            response = await self.navidrome_client.client.get(
                f"{self.navidrome_client.base_url}/rest/getRandomSongs.view",
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            songs = data.get("subsonic-response", {}).get("randomSongs", {}).get("song", [])
            return songs if isinstance(songs, list) else []
        except Exception as e:
            print(f"❌ Year range search failed: {e}")
            return []

    def _filter_and_enrich_candidates(self, search_results: List[Dict[str, Any]], target_tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter search results and calculate rediscovery scores."""
        candidates = []
        now = datetime.now(timezone.utc)
        exclude_before = now - timedelta(days=self.config["exclude_played_within_days"])
        target_track_ids = {t["id"] for t in target_tracks}

        for track in search_results:
            track_id = track.get("id")
            if not track_id:
                continue
            played_str = track.get("played")
            if played_str:
                try:
                    if played_str.endswith("Z"):
                        played_str = played_str[:-1] + "+00:00"
                    played = datetime.fromisoformat(played_str)
                    if played > exclude_before:
                        continue
                except Exception:
                    pass

            play_count = track.get("playCount", 0)
            days_since_play = 30
            if played_str:
                try:
                    if played_str.endswith("Z"):
                        played_str = played_str[:-1] + "+00:00"
                    played = datetime.fromisoformat(played_str)
                    days_since_play = (now - played).days
                except Exception:
                    pass

            rediscovery_score = play_count * (1 + days_since_play ** 0.5) * random.uniform(0.8, 1.2)
            was_in_target_period = track_id in target_track_ids

            candidate = {
                **track,
                "rediscovery_score": rediscovery_score,
                "days_since_last_play": days_since_play,
                "was_in_target_period": was_in_target_period,
            }
            candidates.append(candidate)

        candidates.sort(key=lambda x: x["rediscovery_score"], reverse=True)
        return candidates[:100]

    async def _llm_phase2_sequencing(self, candidates: List[Dict[str, Any]], theme_strategy: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Phase 2 AI: Sequence exactly 25 tracks for optimal playlist flow."""
        ai_candidates = []
        for track in candidates[:80]:
            ai_candidates.append({
                "id": track["id"],
                "title": track.get("title", ""),
                "artist": track.get("artist", ""),
                "album": track.get("album", ""),
                "genres": [g.get("name", "") for g in track.get("genres", [])] if isinstance(track.get("genres"), list) else [],
                "year": track.get("year", 2000),
                "play_count": track.get("playCount", 0),
                "days_since_last_play": track.get("days_since_last_play", 30),
                "rediscovery_score": round(track.get("rediscovery_score", 0), 2),
                "was_in_target_period": track.get("was_in_target_period", False),
            })

        recipe_inputs = {
            "theme_strategy": json.dumps(theme_strategy),
            "candidate_tracks": json.dumps(ai_candidates),
            "num_tracks": self.config["track_count"],
        }

        try:
            ai_result = await curate_rediscover_weekly(
                ai_client=self.ai_client,
                candidate_tracks=ai_candidates,
                analysis_summary="",
                num_tracks=self.config["track_count"],
                include_description=True,
                variety_context=json.dumps(theme_strategy) if theme_strategy else None,
            )

            if isinstance(ai_result, tuple):
                track_ids, description = ai_result
            else:
                track_ids = ai_result
                description = ""

            final_tracks = []
            for track_id in track_ids:
                candidate = next((c for c in ai_candidates if c["id"] == track_id), None)
                if candidate:
                    final_tracks.append({
                        **candidate,
                        "ai_curated": True,
                        "ai_description": description,
                    })

            if len(final_tracks) == self.config["track_count"]:
                return final_tracks
        except Exception as e:
            print(f"❌ Phase 2 AI failed: {e}")
            theme_strategy["description"] = "Fallback strategy due to AI unavailability"

        top_candidates = candidates[: self.config["track_count"]]
        return [{
            **track,
            "ai_curated": False,
            "ai_description": "Algorithmic selection (AI not available)",
        } for track in top_candidates]

    async def _create_playlist_data(self, tracks: List[Dict[str, Any]], theme_strategy: Dict[str, Any], user_id: str, server_id: str, used_smart_playlist: bool = False) -> Dict[str, Any]:
        """Create final playlist data structure."""
        return {
            "name": "Re-Discover Weekly",
            "tracks": tracks,
            "theme": theme_strategy.get("theme_identified", "Mixed"),
            "mode": theme_strategy.get("selected_mode", "A"),
            "description": theme_strategy.get("description", ""),
            "user_id": user_id,
            "server_id": server_id,
            "generated_at": datetime.now().isoformat(),
            "used_smart_playlist": used_smart_playlist,
        }

    async def _log_to_database_v2(self, playlist_data: Dict[str, Any], theme_strategy: Dict[str, Any], tracks_analyzed: int):
        """Log v2 playlist generation to database."""
        print(f"📊 V2 Playlist logged: {len(playlist_data['tracks'])} tracks, theme: {theme_strategy.get('theme_identified', 'Unknown')}, tracks analyzed: {tracks_analyzed}")

    async def _trigger_fallback(self, user_id: str, server_id: str, library_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fallback strategy when insufficient target period tracks are found."""
        try:
            starred_tracks = await self.navidrome_client.get_starred()
            if starred_tracks:
                now = datetime.now(timezone.utc)
                exclude_before = now - timedelta(days=self.config["exclude_played_within_days"])
                valid_starred = []
                for track in starred_tracks[:50]:
                    played_str = track.get("played")
                    if played_str:
                        try:
                            if played_str.endswith("Z"):
                                played_str = played_str[:-1] + "+00:00"
                            played = datetime.fromisoformat(played_str)
                            if played < exclude_before:
                                valid_starred.append(track)
                        except Exception:
                            continue

                if len(valid_starred) >= 10:
                    fallback_tracks = valid_starred[: self.config["track_count"]]
                    return {
                        "name": "Re-Discover Weekly",
                        "tracks": [{
                            **track,
                            "ai_curated": False,
                            "ai_description": "Fallback: Using starred tracks (limited recent listening history)",
                        } for track in fallback_tracks],
                        "theme": "Starred Favorites",
                        "mode": "FALLBACK",
                        "description": "Insufficient listening history in target period. Using starred tracks instead.",
                        "user_id": user_id,
                        "server_id": server_id,
                        "generated_at": datetime.now().isoformat(),
                        "is_fallback": True,
                    }
        except Exception as e:
            print(f"⚠️ Starred tracks fallback failed: {e}")

        try:
            print("🔄 Trying basic library fallback...")
            basic_tracks = await self._sample_library(min(100, self.config["track_count"] * 3), library_ids)
            if basic_tracks and len(basic_tracks) >= 10:
                basic_tracks.sort(key=lambda x: x.get("playCount", 0), reverse=True)
                fallback_tracks = basic_tracks[: self.config["track_count"]]
                return {
                    "name": "Re-Discover Weekly",
                    "tracks": [{
                        **track,
                        "ai_curated": False,
                        "ai_description": "Basic fallback: Using highest-played tracks (very limited listening history)",
                    } for track in fallback_tracks],
                    "theme": "Library Favorites",
                    "mode": "BASIC_FALLBACK",
                    "description": "No recent listening history found. Using your most-played tracks instead.",
                    "user_id": user_id,
                    "server_id": server_id,
                    "generated_at": datetime.now().isoformat(),
                    "is_fallback": True,
                }
        except Exception as e:
            print(f"⚠️ Basic library fallback also failed: {e}")

        raise Exception("Insufficient listening history. Star favorites and listen regularly. Check back in 2-3 weeks!")

    async def _log_to_database_v2(self, playlist_data: Dict[str, Any], theme_strategy: Dict[str, Any], tracks_analyzed: int):
        """Log v2 playlist generation to database."""
        print(f"📊 V2 Playlist logged: {len(playlist_data['tracks'])} tracks, theme: {theme_strategy.get('theme_identified', 'Unknown')}, tracks analyzed: {tracks_analyzed}")

    async def _trigger_fallback(self, user_id: str, server_id: str, library_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Fallback strategy when insufficient target period tracks are found."""
        try:
            starred_tracks = await self.navidrome_client.get_starred()
            if starred_tracks:
                now = datetime.now(timezone.utc)
                exclude_before = now - timedelta(days=self.config["exclude_played_within_days"])
                valid_starred = []
                for track in starred_tracks[:50]:
                    played_str = track.get("played")
                    if played_str:
                        try:
                            if played_str.endswith("Z"):
                                played_str = played_str[:-1] + "+00:00"
                            played = datetime.fromisoformat(played_str)
                            if played < exclude_before:
                                valid_starred.append(track)
                        except Exception:
                            continue

                if len(valid_starred) >= 10:
                    fallback_tracks = valid_starred[: self.config["track_count"]]
                    return {
                        "name": "Re-Discover Weekly",
                        "tracks": [{
                            **track,
                            "ai_curated": False,
                            "ai_description": "Fallback: Using starred tracks (limited recent listening history)",
                        } for track in fallback_tracks],
                        "theme": "Starred Favorites",
                        "mode": "FALLBACK",
                        "description": "Insufficient listening history in target period. Using starred tracks instead.",
                        "user_id": user_id,
                        "server_id": server_id,
                        "generated_at": datetime.now().isoformat(),
                        "is_fallback": True,
                    }
        except Exception as e:
            print(f"⚠️ Starred tracks fallback failed: {e}")

        try:
            print("🔄 Trying basic library fallback...")
            basic_tracks = await self._sample_library(min(100, self.config["track_count"] * 3), library_ids)
            if basic_tracks and len(basic_tracks) >= 10:
                basic_tracks.sort(key=lambda x: x.get("playCount", 0), reverse=True)
                fallback_tracks = basic_tracks[: self.config["track_count"]]
                return {
                    "name": "Re-Discover Weekly",
                    "tracks": [{
                        **track,
                        "ai_curated": False,
                        "ai_description": "Basic fallback: Using highest-played tracks (very limited listening history)",
                    } for track in fallback_tracks],
                    "theme": "Library Favorites",
                    "mode": "BASIC_FALLBACK",
                    "description": "No recent listening history found. Using your most-played tracks instead.",
                    "user_id": user_id,
                    "server_id": server_id,
                    "generated_at": datetime.now().isoformat(),
                    "is_fallback": True,
                }
        except Exception as e:
            print(f"⚠️ Basic library fallback also failed: {e}")

        raise Exception("Insufficient listening history. Star favorites and listen regularly. Check back in 2-3 weeks!")
