"""Local and remote application version resolution."""

import re
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import httpx


GITHUB_LATEST_RELEASE_URL = (
    "https://api.github.com/repos/pirus99/magic-lists-ai-curator/releases/latest"
)
GITHUB_RELEASES_URL = (
    "https://github.com/pirus99/magic-lists-ai-curator/releases"
)
CHANGELOG_PATH = Path(__file__).resolve().parents[2] / "CHANGELOG.md"

_cache: Optional[Dict[str, object]] = None
_cache_at = 0.0
_CACHE_SECONDS = 6 * 60 * 60


def normalize_tag(tag: str) -> str:
    """Normalize a release tag to a display string without a leading v."""
    value = (tag or "").strip()
    if value.lower().startswith("v"):
        value = value[1:]
    return value


def parse_local_tag(changelog_text: str) -> Optional[str]:
    """Return the newest released heading, ignoring Unreleased."""
    for match in re.finditer(r"^##\s*\[([^\]]+)\]", changelog_text, re.MULTILINE):
        tag = normalize_tag(match.group(1))
        if tag.lower() != "unreleased":
            return tag
    return None


def read_local_tag(changelog_path: Optional[Path] = None) -> Optional[str]:
    """Read the installed application's local release tag."""
    path = changelog_path or CHANGELOG_PATH
    try:
        return parse_local_tag(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None


def version_key(tag: str) -> Tuple[int, ...]:
    """Create a numeric comparison key for common semantic-version tags."""
    tag = normalize_tag(tag)
    match = re.search(r"(\d+(?:\.\d+)*)", tag)
    if not match:
        return (0,)
    return tuple(int(part) for part in match.group(1).split("."))


def is_update_available(local_tag: Optional[str], remote_tag: Optional[str]) -> bool:
    """Return whether the remote release is newer than the local release."""
    if not local_tag or not remote_tag:
        return False

    local = version_key(local_tag)
    remote = version_key(remote_tag)
    width = max(len(local), len(remote))
    return remote + (0,) * (width - len(remote)) > local + (0,) * (width - len(local))


async def get_version_status(force_refresh: bool = False) -> Dict[str, object]:
    """Check GitHub for the latest release and compare it with CHANGELOG.md."""
    global _cache, _cache_at

    now = time.monotonic()
    if not force_refresh and _cache is not None and now - _cache_at < _CACHE_SECONDS:
        return dict(_cache)

    local_tag = read_local_tag()
    remote_tag: Optional[str] = None
    error: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            response = await client.get(
                GITHUB_LATEST_RELEASE_URL,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
            )
            response.raise_for_status()
            payload = response.json()
            remote_tag = normalize_tag(str(payload.get("tag_name") or "")) or None
            if remote_tag is None:
                error = "GitHub returned no release tag"
    except httpx.HTTPError as exc:
        error = f"Could not reach GitHub: {exc.__class__.__name__}"
    except Exception as exc:
        error = f"Could not parse GitHub release: {exc.__class__.__name__}"

    status: Dict[str, object] = {
        "current_tag": local_tag,
        "remote_tag": remote_tag,
        "latest_tag": remote_tag,
        "update_available": is_update_available(local_tag, remote_tag),
        "releases_url": GITHUB_RELEASES_URL,
        "checked": remote_tag is not None,
        "error": error,
    }

    _cache = status
    _cache_at = now
    return dict(status)
