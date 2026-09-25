"""AI curation logic for 'Genre Mix' playlists.

Moved here from ``ai_client.py``. Reuses the shared parser / provider plumbing via
the passed-in ``AIClient`` instance.
"""
import httpx
import json
from typing import Any, Dict, List, Optional, Tuple, Union

from ..recipe_manager import recipe_manager
from ..ai_client import (
    parse_ai_track_response,
    MAX_OVER_RETURN_FACTOR,
)
from ..output_sorting import space_id_track_list_by_artist_and_album
from ..services.candidate_limiter import limit_candidates_for_ai


async def curate_genre_mix(
    ai_client,
    genres: List[str],
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int = 20,
    include_description: bool = False,
    variety_context: Optional[str] = None,
) -> Union[List[str], Tuple[List[str], str]]:
    """Curate a 'Genre Mix' playlist for multiple genres using AI."""
    if not ai_client.api_key and not ai_client.provider.provider_type == "ollama":
        genre_names = ", ".join(genres)
        print(f"❌ No AI API key configured, using fallback curation for {genre_names}")
        return _fallback_genre_mix_selection(candidate_tracks, num_tracks, include_description, f"No AI API key configured for {genre_names}")

    try:
        genre_names = ", ".join(genres)
        recipe_inputs = {
            "genres": genre_names,
            "num_tracks": num_tracks,
            "variety_context": variety_context or "",
        }

        print(f"🍳 Applying recipe for {genre_names} ({num_tracks} tracks)")
        final_recipe = recipe_manager.apply_recipe("genre_mix", recipe_inputs, include_description)
        ai_candidate_tracks = limit_candidates_for_ai(
            candidate_tracks,
            final_recipe,
            ai_client,
        )

        user_content = ""
        track_id_map = []

        llm_config = final_recipe.get("llm_config", {})
        selection_instructions = final_recipe.get("selection_instructions") or final_recipe.get("model_instructions", "")
        description_instructions = final_recipe.get("description_instructions", "")
        description_llm_config = final_recipe.get("description_llm_config", {"temperature": 0.7, "max_output_tokens": 500})
        output_sorting_params = final_recipe.get("output_sorting", {})
        artist_spacing = output_sorting_params.get("space_between_same_artist", 4)
        album_spacing = output_sorting_params.get("space_between_same_album", 3)

        model = ai_client.model or "openai/gpt-3.5-turbo"
        temperature = llm_config.get("temperature", 0.7)
        max_tokens = llm_config.get("max_output_tokens", 16000)

        print(f"🤖 Using AI model: {model} (from {ai_client.provider.provider_type} provider)")

        indexed_tracks = []
        for index, track in enumerate(ai_candidate_tracks):
            track_id_map.append(track["id"])
            track_score = round(track.get("play_count", 0)) * 1.5
            liked = track.get("local_library_likes", False)
            if liked:
                track_score += 15
            indexed_track = (
                index,
                f"{track.get('title', 'Unknown')} - {track.get('artist', 'Unknown')}",
                track.get("year", "Unknown"),
                track_score,
            )
            indexed_tracks.append(indexed_track)

        print(f"🔢 Using index-based approach for {len(track_id_map)} tracks")

        user_content = (
            f"Select {num_tracks} tracks for your {genre_names} playlist.\n"
            f"Tracks: {indexed_tracks}\n"
        )

        content = await ai_client.provider.generate(
            system_prompt=selection_instructions,
            user_prompt=user_content,
            max_tokens=max_tokens,
            temperature=temperature,
        )

        print(f"🤖 FULL RAW AI RESPONSE for Genre Mix: {content}")

        if not content or content.strip() == "":
            print(f"⚠️  AI service returned empty response")
            return _fallback_genre_mix_selection(candidate_tracks, num_tracks, include_description, "AI service returned empty response")

        try:
            track_ids, _description = parse_ai_track_response(content)
            returned_track_count = len(track_ids)

            if returned_track_count == 0:
                print(f"❌ AI returned no tracks - invalid response")
                raise ValueError("AI response validation failed: No tracks returned")

            max_reasonable = int(num_tracks * MAX_OVER_RETURN_FACTOR)
            if returned_track_count > max_reasonable:
                print(f"❌ AI returned {returned_track_count} tracks, more than {MAX_OVER_RETURN_FACTOR}x requested {num_tracks}")
                raise ValueError(f"AI response validation failed: Too many tracks returned ({returned_track_count} vs max {max_reasonable})")

            source_track_count = len(ai_candidate_tracks)
            if returned_track_count > source_track_count:
                print(f"❌ AI returned {returned_track_count} tracks but we only provided {source_track_count}")
                raise ValueError(f"AI response validation failed: More tracks returned than provided")

            print(f"✅ AI returned {returned_track_count} tracks (requested: {num_tracks}), validation passed")

            valid_indices = [idx for idx in track_ids if 0 <= idx < len(track_id_map)]
            mapped_track_ids = [track_id_map[idx] for idx in valid_indices]
            mapped_track_ids = mapped_track_ids[:num_tracks]

            final_selection = space_id_track_list_by_artist_and_album(
                mapped_track_ids, ai_candidate_tracks, artist_spacing=artist_spacing, album_spacing=album_spacing
            )

            description = ""
            if include_description:
                description = await ai_client._generate_playlist_description(
                    description_instructions=description_instructions,
                    selected_track_ids=final_selection,
                    candidate_tracks=ai_candidate_tracks,
                    playlist_context=f"Genre Mix: {genre_names}",
                    llm_config=description_llm_config,
                )

            if include_description:
                return final_selection, description
            return final_selection

        except (json.JSONDecodeError, ValueError) as e:
            print(f"Failed to parse AI response: {e}")
            print(f"Response content: {content}")
            return _fallback_genre_mix_selection(candidate_tracks, num_tracks, include_description)
    except httpx.RequestError as e:
        print(f"🌐 Network error calling AI API: {e}")
        return _fallback_genre_mix_selection(candidate_tracks, num_tracks, include_description, f"Network error: {e}")
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
            return _fallback_genre_mix_selection(candidate_tracks, num_tracks, include_description, user_message)
        print(f"🚨 HTTP error from AI API: {e.response.status_code} - {response_text}")
        return _fallback_genre_mix_selection(candidate_tracks, num_tracks, include_description, f"HTTP {e.response.status_code}: {response_text}")
    except Exception as e:
        print(f"💥 Unexpected error in Genre Mix AI curation: {e}")
        import traceback
        print(f"📋 Traceback: {traceback.format_exc()}")
        return _fallback_genre_mix_selection(candidate_tracks, num_tracks, include_description, f"Unexpected error: {e}")


def _fallback_genre_mix_selection(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    include_description: bool = False,
    error_reason: str = "AI service was unavailable",
) -> Union[List[str], Tuple[List[str], str]]:
    """Fallback selection algorithm for genre mix when AI is unavailable."""
    sorted_tracks = sorted(candidate_tracks, key=lambda x: x.get("play_count", 0), reverse=True)
    track_ids = [track["id"] for track in sorted_tracks[:num_tracks]]
    spaced_tracks = space_id_track_list_by_artist_and_album(track_ids, candidate_tracks, artist_spacing=4, album_spacing=3)

    if include_description:
        description = f"Fallback curation: Selected top {len(track_ids)} tracks sorted by play count (highest first). {error_reason}"
        return spaced_tracks, description
    return spaced_tracks
