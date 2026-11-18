"""AI curation logic for 'Re-Discover' playlists.

Moved here from ``ai_client.py``. Reuses the shared parser / provider plumbing via
the passed-in ``AIClient`` instance.
"""
import json
import logging
import traceback
from typing import Any, Dict, List, Tuple, Union

from ..recipe_manager import recipe_manager
from ..ai_client import parse_ai_track_response
from ..core.curation_notices import record_ai_failure, record_fallback


logger = logging.getLogger(__name__)



async def curate_rediscover_weekly(
    ai_client,
    candidate_tracks: List[Dict[str, Any]],
    analysis_summary: str,
    num_tracks: int = 20,
    include_description: bool = True,
) -> Union[List[str], Tuple[List[str], str]]:
    """Curate a Re-Discover Weekly playlist using AI."""
    if not ai_client.api_key and ai_client.provider.provider_type == "openrouter":
        logger.warning(f"❌ No AI API key configured, using fallback curation for Re-Discover Weekly")
        record_fallback(
            "No AI API key is configured, so Re-Discover was built with the "
            "algorithmic scoring fallback instead of AI curation."
        )
        track_ids = [track["id"] for track in candidate_tracks[:num_tracks]]
        if include_description:
            fallback_description = (
                f"Fallback curation: Selected top {len(track_ids)} tracks from algorithmic "
                f"scoring (highest score first). No AI API key configured."
            )
            return track_ids, fallback_description
        return track_ids

    indexed_tracks = []
    track_id_map = []
    for index, track in enumerate(candidate_tracks):
        track_id_map.append(track["id"])
        indexed_track = (
                index,
                f"{track.get('title', 'NA')} - {track.get('artist', 'NA')}",
                track.get("year", "NA"),
                track.get("genres", "NA"),
                track.get("rediscovery_score", "0",)
        )
        indexed_tracks.append(indexed_track)

    try:
        logger.debug(f"🤖 Making AI request for Re-Discover Weekly curation...")

        recipe_inputs = {
            "analysis_summary": analysis_summary,
            "num_tracks": num_tracks,
        }

        final_recipe = recipe_manager.apply_recipe("re_discover", recipe_inputs)

        if "llm_config" in final_recipe:
            llm_config = final_recipe.get("llm_config", {})
            model_instructions = final_recipe.get("model_instructions", "")
            model = ai_client.model or "openai/gpt-3.5-turbo"
            temperature = llm_config.get("temperature", 0.7)
            max_tokens = llm_config.get("max_output_tokens", 1500)

            logger.debug(f"🤖 Using AI model: {model} (from {ai_client.provider.provider_type} provider)")

            user_content = f"""Select {num_tracks} tracks for a Re-Discover Weekly playlist.
            Tracks: {indexed_tracks}
            Return JSON: {{"track_ids": [indices], "description": "summary"}}"""

            logger.debug(f"📤 Phase 2 AI Payload (first 500 chars): {user_content[:500]}...")
            logger.debug(f"📤 Phase 2 AI Payload (structured_tracks count): {len(indexed_tracks)}")

            content = await ai_client.provider.generate(
                system_prompt=model_instructions,
                user_prompt=user_content,
                max_tokens=max_tokens,
                temperature=temperature,
            )

            if not content or content.strip() == "":
                logger.warning(f"⚠️  AI service returned empty response")
                return _fallback_rediscover_selection(candidate_tracks, num_tracks, include_description, "AI service returned empty response")
        else:
            prompt = final_recipe.get("prompt", "")
            llm_params = final_recipe.get("llm_params", {})
            model = ai_client.model or llm_params.get("model_fallback", "openai/gpt-3.5-turbo")
            temperature = llm_params.get("temperature", 0.8)
            max_tokens = llm_params.get("max_tokens", 2500)

            content = await ai_client.provider.generate(
                system_prompt=(
                    "You are a professional music curator specializing in rediscovery playlists. "
                    "Always respond with valid JSON containing track_ids array and description string. "
                    "No other text outside the JSON."
                ),
                user_prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )

        if not content or content.strip() == "":
            logger.warning(f"⚠️  AI service returned empty response")
            return _fallback_rediscover_selection(candidate_tracks, num_tracks, include_description, "AI service returned empty response")

        try:
            track_indices, description = parse_ai_track_response(content)
            logger.info(f"✅ Response validation passed: {len(track_indices)} track indices, description length: {len(description)}")

            track_ids = []
            for index in track_indices:
                if 0 <= index < len(track_id_map):
                    track_ids.append(track_id_map[index])
                else:
                    logger.warning(f"⚠️ Invalid track index {index}, skipping")

            if len(track_ids) < num_tracks and len(candidate_tracks) >= num_tracks:
                used_indices = set(track_indices)
                remaining_tracks = [track_id_map[i] for i in range(len(track_id_map)) if i not in used_indices]
                track_ids.extend(remaining_tracks[: num_tracks - len(track_ids)])
                logger.debug(f"🔄 Filled to {len(track_ids)} tracks with remaining candidates")

            logger.info(f"✅ Phase 2 AI curation successful: returning {len(track_ids)} tracks with description length {len(description)}")

            if include_description:
                return track_ids, description
            return track_ids

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"❌ Failed to parse AI response as JSON: {e}")
            logger.debug(f"🔍 Raw response: {content}")
            return _fallback_rediscover_selection(candidate_tracks, num_tracks, include_description, f"AI returned invalid JSON: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to validate AI response: {e}")
            logger.debug(f"🔍 Raw response: {content}")
            return _fallback_rediscover_selection(candidate_tracks, num_tracks, include_description, f"AI response validation failed: {e}")
    except Exception as e:
        logger.error(f"💥 Unexpected error in Re-Discover Weekly AI curation: {e}")
        logger.debug(f"📋 Traceback: {traceback.format_exc()}")
        return _fallback_rediscover_selection(candidate_tracks, num_tracks, include_description, f"Unexpected error: {e}")


def _fallback_rediscover_selection(
    candidate_tracks: List[Dict[str, Any]],
    num_tracks: int,
    include_description: bool = False,
    error_reason: str = "AI service was unavailable",
) -> Union[List[str], Tuple[List[str], str]]:
    """Fallback selection algorithm for rediscover when AI is unavailable.

    Every AI failure path funnels through here, so this is where the failure is
    reported to the refresh queue.
    """
    record_ai_failure(
        f"AI curation failed for Re-Discover ({error_reason}). "
        f"The playlist was rebuilt with the algorithmic scoring fallback instead."
    )
    track_ids = [track["id"] for track in candidate_tracks[:num_tracks]]
    if include_description:
        description = (
            f"Fallback curation: Selected top {len(track_ids)} tracks from algorithmic "
            f"pre-filtering (sorted by play count × days since last play). {error_reason}"
        )
        return track_ids, description
    return track_ids
