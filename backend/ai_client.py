import httpx
import json
import re
from typing import List, Dict, Any, Union, Tuple, Optional
from .services.ai_providers import get_ai_provider


def clean_json_response(response: str) -> str:
    """Clean JSON response by replacing problematic characters that break parsing.
    
    Args:
        response: Raw JSON string from AI service
        
    Returns:
        Cleaned JSON string safe for parsing
    """
    # Replace smart quotes and other problematic Unicode characters
    cleaned = (
        response
        .replace('“', "'")
        .replace('”', "'")
        .replace('‘', "'")
        .replace('’', "'")
        .replace('–', "-")
        .replace('—', "-")
        .replace('…', "...")
    )
    
    # Remove any control characters except newline and tab
    cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', cleaned)
    
    return cleaned


# ---------------------------------------------------------------------------
# Global, robust AI response parser
# ---------------------------------------------------------------------------
# Alternative key names an LLM might use for the track-identifier list.
_TRACK_ID_KEYS = [
    "track_ids", "trackIds", "track_id", "track_ids_list",
    "tracks", "track_list", "tracklist", "song_ids", "songIds",
    "songs", "ids", "id_list", "idList", "selected_tracks",
    "selected_track_ids", "playlist", "playlist_tracks", "indices",
    "indexes", "selected_indices", "selected_ids", "music", "results",
]

# Alternative key names an LLM might use for a description / summary.
_DESCRIPTION_KEYS = [
    "description", "desc", "summary", "about", "note", "blurb",
    "text", "explanation", "rationale", "details", "comment",
]


def _strip_code_fences(text: str) -> str:
    """Remove markdown/code fences (``` or ~~~, optional language tag)."""
    # Backtick fences: ```json ... ``` or ``` ... ```
    fence = re.search(r"```(?:[a-zA-Z]+)?\s*(.*?)\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1).strip()
    # Tilde fences: ~~~json ... ~~~
    tilde = re.search(r"~~~(?:[a-zA-Z]+)?\s*(.*?)\s*~~~", text, re.DOTALL)
    if tilde:
        return tilde.group(1).strip()
    return text.strip()


def _coerce_to_int_list(values) -> Optional[List[int]]:
    """Coerce a list of mixed values into a list of ints where possible."""
    result: List[int] = []
    for v in values:
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            result.append(v)
        elif isinstance(v, float) and v.is_integer():
            result.append(int(v))
        elif isinstance(v, str):
            s = v.strip()
            if s.lstrip("-").isdigit():
                result.append(int(s))
    return result if result else None


def _extract_ids_from_obj(obj: dict) -> Optional[List[int]]:
    """Extract a track-id list from a dict using any known key alias."""
    for key in _TRACK_ID_KEYS:
        if key in obj:
            val = obj[key]
            if isinstance(val, list):
                return _coerce_to_int_list(val)
            if isinstance(val, str):
                parts = [p.strip() for p in val.replace("\n", ",").split(",") if p.strip()]
                return _coerce_to_int_list(parts)
    return None


def _extract_description_from_obj(obj: dict) -> str:
    """Extract a description string from a dict using any known key alias."""
    for key in _DESCRIPTION_KEYS:
        if key in obj and isinstance(obj[key], str):
            return obj[key].strip()
    return ""


def _find_json_substring(text: str):
    """Find the first JSON object or array substring in free text."""
    # Object first (greedy so we capture the whole object including nested braces)
    obj_match = re.search(r"\{.*\}", text, re.DOTALL)
    if obj_match:
        return obj_match.group(0)
    arr_match = re.search(r"\[.*\]", text, re.DOTALL)
    if arr_match:
        return arr_match.group(0)
    return None


def parse_ai_track_response(content: str) -> Tuple[List[int], str]:
    """Globally robust parser for AI track-selection responses.

    Handles the wide variety of formats an LLM may return:
    - Plain JSON object: ``{"track_ids": [...], "description": "..."}``
    - JSON wrapped in markdown code fences (````` ```json ... ````````)
    - Bare JSON array: ``[1, 2, 3]``
    - JSON with alternative key names (``tracks``, ``ids``, ``songs``, ``indices``...)
    - Free-text responses that embed a JSON block
    - Free-text responses that are just a list of numbers

    Returns:
        A tuple of ``(track_identifiers, description)`` where ``track_identifiers``
        is a list of integers (indices or IDs) and ``description`` is a string
        (possibly empty).

    Raises:
        ValueError: if no usable track identifiers can be extracted.
    """
    if not content or not content.strip():
        raise ValueError("Empty AI response")

    cleaned = clean_json_response(content.strip())

    # Step 1: strip code fences (handles trailing newlines around fences too)
    body = _strip_code_fences(cleaned)

    parsed = None
    # Step 2: try to parse the (fence-stripped) body directly
    try:
        parsed = json.loads(body)
    except (json.JSONDecodeError, ValueError):
        parsed = None

    # Step 3: try to extract an embedded JSON object/array from prose
    if parsed is None:
        sub = _find_json_substring(body)
        if sub:
            try:
                parsed = json.loads(sub)
            except (json.JSONDecodeError, ValueError):
                parsed = None

    # Step 4: handle the parsed structure
    if isinstance(parsed, dict):
        ids = _extract_ids_from_obj(parsed)
        if ids is not None:
            return ids, _extract_description_from_obj(parsed)
    elif isinstance(parsed, list):
        ids = _coerce_to_int_list(parsed)
        if ids is not None:
            return ids, ""

    # Step 5: last resort - pull every integer out of the response
    numbers = re.findall(r"-?\d+", cleaned)
    if numbers:
        ids = [int(n) for n in numbers]
        if ids:
            return ids, ""

    raise ValueError("Could not extract track_ids from AI response")


# Maximum factor by which the AI may over-return tracks relative to the requested
# count. Responses returning more than this multiple are treated as malformed and
# trigger the algorithmic fallback. Responses within the limit are trimmed to the
# exact requested length.
MAX_OVER_RETURN_FACTOR = 2.0


class AIClient:
    """Client for AI provider access and shared response handling.

    Per-type curation logic (``curate_this_is``, ``curate_genre_mix``,
    ``curate_rediscover_weekly``) lives in the respective type packages
    (``this_is/curation.py``, ``genre_mix/curation.py``, ``rediscover/curation.py``).
    This class only owns the provider plumbing, the generic ``call_ai`` method,
    the editorial ``_generate_playlist_description`` helper, and lifecycle
    management. The robust ``parse_ai_track_response`` parser is a module-level
    function reused by every type's curation module.
    """
    
    def __init__(self):
        self.provider = get_ai_provider()
        # Separate provider instance for playlist descriptions (same provider/key,
        # but can use a different model via DESCRIPTION_AI_MODEL in .env)
        self.description_provider = get_ai_provider(for_description=True)
        # Backward compatibility - keep these for fallback logic
        self.api_key = self.provider.api_key
        self.model = self.provider.model
        self.base_url = self.provider.base_url

        # Debug logging
        print(f"🔍 AIClient initialized with provider: {self.provider.provider_type}")
        print(f"🤖 Using model: {self.model}")
        print(f"📝 Description model: {self.description_provider.model}")
        print(f"🌐 Base URL: {self.base_url}")
        
        
    async def call_ai(self, llm_config: Dict[str, Any]) -> Union[str, Dict[str, Any]]:
        """Generic method to call AI with llm_config from recipes"""
        try:
            model = self.model or llm_config.get("model_fallback", "openai/gpt-3.5-turbo")
            temperature = llm_config.get("temperature", 0.7)
            max_tokens = llm_config.get("max_output_tokens", 1500)

            # Get system and user prompts from llm_config
            system_prompt = llm_config.get("system_prompt", "You are a helpful AI assistant.")
            user_prompt = llm_config.get("user_prompt", "")

            print(f"🤖 Making generic AI call with model {model}...")

            content = await self.provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )

            # Handle empty response from AI provider
            if not content or content.strip() == "":
                print(f"⚠️  AI service returned empty response")
                return ""

            # Try to parse as JSON, return as string if not
            try:
                # Clean the JSON response to handle problematic characters
                cleaned_content = clean_json_response(content)
                return json.loads(cleaned_content)
            except json.JSONDecodeError:
                return content

        except Exception as e:
            print(f"💥 Error in generic AI call: {e}")
            raise

    async def _generate_playlist_description(
        self,
        description_instructions: str,
        selected_track_ids: List[str],
        candidate_tracks: List[Dict[str, Any]],
        playlist_context: str,
        llm_config: Dict[str, Any]
    ) -> str:
        """Generate an editorial description for an already-built playlist.

        Uses a separate AI request (and optionally a separate model via DESCRIPTION_AI_MODEL).
        On any failure, returns a generic fallback description string so the playlist
        can still be created. Shared by genre_mix and this_is curation.

        Args:
            description_instructions: System prompt for the description model
            selected_track_ids: Final ordered list of track IDs in the playlist
            candidate_tracks: Full candidate track metadata (for human-readable mapping)
            playlist_context: Human-readable playlist name/context (e.g. "Genre Mix: Rock" or "This Is Artist")
            llm_config: LLM parameters (temperature, max_output_tokens) for the description call

        Returns:
            Description string (fallback text on failure)
        """
        fallback_description = f"A curated playlist: {playlist_context}."

        if not description_instructions:
            print(f"⚠️ No description_instructions configured, using fallback description")
            return fallback_description

        # Build a human-readable, ordered list of the selected tracks
        track_id_to_info = {track["id"]: track for track in candidate_tracks}
        readable_lines = []
        for position, track_id in enumerate(selected_track_ids, start=1):
            track = track_id_to_info.get(track_id)
            if track:
                title = track.get("title", "Unknown")
                artist = track.get("artist", "Unknown")
                year = track.get("year", "Unknown")
                readable_lines.append(f"{position}. {title} - {artist} ({year})")
            else:
                readable_lines.append(f"{position}. [unknown track]")

        readable_list = "\n".join(readable_lines)

        user_content = (
            f"The following is the final, ordered track list for a {playlist_context} playlist.\n"
            f"Write a short editorial description for it.\n\n"
            f"Tracks:\n{readable_list}\n"
        )

        temperature = llm_config.get("temperature", 0.7)
        max_tokens = llm_config.get("max_output_tokens", 500)

        try:
            print(f"📝 Generating playlist description with model: {self.description_provider.model}")
            content = await self.description_provider.generate(
                system_prompt=description_instructions,
                user_prompt=user_content,
                max_tokens=max_tokens,
                temperature=temperature
            )

            if not content or content.strip() == "":
                print(f"⚠️ Description AI returned empty response, using fallback description")
                return fallback_description

            # Parse: accept plain text, or extract "description" from a JSON wrapper
            cleaned = content.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            try:
                parsed = json.loads(clean_json_response(cleaned))
                if isinstance(parsed, dict) and isinstance(parsed.get("description"), str):
                    description = parsed["description"].strip()
                else:
                    description = cleaned
            except (json.JSONDecodeError, ValueError):
                # Plain text response - use as-is
                description = cleaned

            if not description:
                print(f"⚠️ Description AI returned empty content, using fallback description")
                return fallback_description

            print(f"✅ Playlist description generated (length: {len(description)} chars)")
            return description

        except Exception as e:
            print(f"💥 Error generating playlist description: {e}")
            return fallback_description

    async def close(self):
        """Close the HTTP client"""
        try:
            if hasattr(self, 'provider') and self.provider:
                await self.provider.close()
        except Exception as e:
            print(f"Warning: Error closing AI provider: {e}")
        try:
            if hasattr(self, 'description_provider') and self.description_provider:
                await self.description_provider.close()
        except Exception as e:
            print(f"Warning: Error closing description AI provider: {e}")