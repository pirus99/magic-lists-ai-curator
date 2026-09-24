"""AI curation logic for 'This Is' (single-artist) playlists.

Moved here from ``ai_client.py`` so that the per-type curation code lives next to
the rest of the type's logic. The shared parser / provider plumbing still lives in
``ai_client.py`` and is reused via the passed-in ``AIClient`` instance.
"""
import httpx
import json
import random
from typing import Any, Dict, List, Optional, Tuple, Union

from ..recipe_manager import recipe_manager
from ..ai_client import (
    clean_json_response,
    parse_ai_track_response,
    MAX_OVER_RETURN_FACTOR,
)
from ..output_sorting import space_id_track_list_by_artist_and_album
from ..services.track_scoring_service import calculate_track_score


async def curate_this_is(
    ai_client,
    artist_name: str,
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int = 20,
    include_description: bool = False,
    variety_context: Optional[str] = None,
) -> Union[List[str], Tuple[List[str], str]]:
    """Curate a 'This Is' playlist for a single artist using AI."""
    if not ai_client.api_key and ai_client.provider.provider_type == "openrouter":
        print(f"❌ No AI API key configured, using fallback curation for {artist_name}")
        sorted_tracks = sorted(candidate_tracks, key=lambda x: x.get("play_count", 0), reverse=True)
        track_ids = [track["id"] for track in sorted_tracks[:num_tracks]]
        if include_description:
            fallback_description = (
                f"Fallback curation: Selected {len(track_ids)} tracks sorted by play count "
                f"(highest first). No AI API key configured."
            )
            return track_ids, fallback_description
        return track_ids

    try:
        shuffled_tracks = candidate_tracks.copy()
        random.shuffle(shuffled_tracks)

        shuffled_track_count = len(shuffled_tracks)
        print(f"🎵 Preparing {shuffled_track_count} tracks for AI curation")

        if shuffled_tracks:
            sample_track = shuffled_tracks[0]
            essential_fields = ["id", "title", "artist", "album"]
            missing_fields = [f for f in essential_fields if f not in sample_track]
            if missing_fields:
                print(f"⚠️  Missing essential fields in tracks: {missing_fields}")
        else:
            print(f"❌ ERROR: No tracks available for curation!")

        recipe_inputs = {
            "artists": artist_name,
            "num_tracks": num_tracks,
            "variety_context": variety_context or "",
        }

        print(f"🍳 Applying recipe for {artist_name} ({num_tracks} tracks)")
        final_recipe = recipe_manager.apply_recipe("this_is", recipe_inputs, include_description)

        if "llm_config" in final_recipe:
            llm_config = final_recipe.get("llm_config", {})
            model_instructions = final_recipe.get("model_instructions", "")
            description_instructions = final_recipe.get("description_instructions", "")
            description_llm_config = final_recipe.get("description_llm_config", {"temperature": 0.7, "max_output_tokens": 500})
            output_sorting_params = final_recipe.get("output_sorting", {})
            album_spacing = output_sorting_params.get("space_between_same_album", 1)

            model = ai_client.model or "openai/gpt-3.5-turbo"
            temperature = llm_config.get("temperature", 0.7)
            max_tokens = llm_config.get("max_output_tokens", 1000)

            print(f"🤖 Using AI model: {model} (from {ai_client.provider.provider_type} provider)")

            indexed_tracks = []
            track_id_map = []
            for index, track in enumerate(shuffled_tracks):
                track_id_map.append(track["id"])
                indexed_track = (
                    index,
                    f"{track.get('title', 'Unknown')} - {track.get('artist', 'Unknown')}",
                    track.get("album", "Unknown"),
                    track.get("year", "Unknown"),
                    calculate_track_score(track),
                )
                indexed_tracks.append(indexed_track)

            print(f"🔢 Using index-based approach for {len(track_id_map)} tracks")

            user_content = (
                f"Select up to {num_tracks} tracks for a 'This Is {artist_name}' playlist.\n"
                f"If fewer than {num_tracks} tracks are available, select all available tracks.\n"
                f"Tracks: {indexed_tracks}\nReturn JSON: {{'track_ids': [indices]}}"
            )
        else:
            prompt = final_recipe["prompt"]
            llm_params = final_recipe["llm_params"]
            model = ai_client.model or llm_params.get("model_fallback", "openai/gpt-3.5-turbo")
            temperature = llm_params.get("temperature", 0.7)
            max_tokens = llm_params.get("max_tokens", 1000)

        if "llm_config" in final_recipe:
            content = await ai_client.provider.generate(
                system_prompt=model_instructions,
                user_prompt=user_content,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        else:
            content = await ai_client.provider.generate(
                system_prompt=(
                    "You are a professional music curator. Always respond with valid JSON "
                    "containing track_ids array and description string. No other text outside the JSON."
                ),
                user_prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        print(f"🤖 FULL RAW AI RESPONSE for This Is: {content}")

        if not content or content.strip() == "":
            print(f"⚠️  AI service returned empty response")
            return _fallback_this_is(candidate_tracks, num_tracks, include_description, "AI service returned empty response")

        try:
            track_ids, _description = parse_ai_track_response(content)
            print(f"✅ AI returned {len(track_ids)} tracks (requested: {num_tracks}), validation passed")

            max_allowed = int(num_tracks * MAX_OVER_RETURN_FACTOR)
            if len(track_ids) > max_allowed:
                print(f"❌ AI returned {len(track_ids)} tracks, more than {MAX_OVER_RETURN_FACTOR}x requested {num_tracks}")
                raise ValueError(f"AI response validation failed: Too many tracks returned ({len(track_ids)} vs max {max_allowed})")

            valid_indices = [idx for idx in track_ids if 0 <= idx < len(track_id_map)]
            mapped_track_ids = [track_id_map[idx] for idx in valid_indices]
            final_selection = space_id_track_list_by_artist_and_album(
                mapped_track_ids, candidate_tracks, artist_spacing=0, album_spacing=album_spacing
            )

            description = ""
            if include_description:
                description = await ai_client._generate_playlist_description(
                    description_instructions=description_instructions,
                    selected_track_ids=final_selection[:20],
                    candidate_tracks=shuffled_tracks,
                    playlist_context=f"This Is {artist_name}",
                    llm_config=description_llm_config,
                )

            if include_description:
                return final_selection, description
            return final_selection

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse AI response: {e}")
            print(f"Response content: {content}")
            return _fallback_this_is(candidate_tracks, num_tracks, include_description)
    except httpx.RequestError as e:
        print(f"🌐 Network error calling AI API: {e}")
        return _fallback_this_is(candidate_tracks, num_tracks, include_description, f"Network error: {e}")
    except httpx.HTTPStatusError as e:
        response_text = e.response.text
        if (response_text.strip().startswith("<!DOCTYPE html") or response_text.strip().startswith("<html") or len(response_text) > 500):
            truncated_text = response_text[:200] + "..." if len(response_text) > 200 else response_text
            print(f"🚨 HTTP error from AI API: {e.response.status_code} - {truncated_text}")
            user_message = (
                f"AI service temporarily unavailable (error {e.response.status_code}). Please try again in a minute."
                if e.response.status_code in [502, 503, 504]
                else f"AI service error (HTTP {e.response.status_code}). Please try again."
            )
            return _fallback_this_is(candidate_tracks, num_tracks, include_description, user_message)
        print(f"🚨 HTTP error from AI API: {e.response.status_code} - {response_text}")
        return _fallback_this_is(candidate_tracks, num_tracks, include_description, f"HTTP {e.response.status_code}: {response_text}")
    except Exception as e:
        print(f"💥 Unexpected error in This Is AI curation: {e}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return _fallback_this_is(candidate_tracks, num_tracks, include_description, f"Unexpected error: {e}")


def _fallback_this_is(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    include_description: bool = False,
    error_reason: str = "AI service was unavailable",
) -> Union[List[str], Tuple[List[str], str]]:
    """Fallback selection for This Is when AI is unavailable."""
    sorted_tracks = sorted(candidate_tracks, key=lambda x: x.get("play_count", 0), reverse=True)
    track_ids = [track["id"] for track in sorted_tracks[:num_tracks]]
    if include_description:
        description = (
            f"Fallback curation: Selected {len(track_ids)} tracks sorted by play count "
            f"(highest first). {error_reason}"
        )
        return track_ids, description
    return track_ids
