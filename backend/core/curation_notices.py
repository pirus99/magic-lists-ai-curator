"""Per-refresh curation notices.

Curation code runs deep inside per-type modules and cannot easily return extra
information without changing every signature. Instead, it records *notices* into
a context-local collector that the refresh queue sets up around each handler
call.

Two kinds of notice exist:

* ``ai_failed`` — the AI request itself failed (network error, HTTP error,
  unparseable response). The refresh is marked **failed** and the user is told.
* ``fallback`` — curation succeeded, but via a fallback algorithm for a
  legitimate reason (for example Re-Discover had no listening history to work
  with). The refresh is marked **successful** but the user is told which
  fallback was used.

Description-generation failures deliberately record nothing: a missing
description is cosmetic and must never fail or warn about a refresh.

``contextvars`` is used rather than a module-level list because each refresh
runs in its own asyncio task, so notices cannot leak between concurrent
refreshes.
"""
import contextvars
from dataclasses import dataclass
from typing import List, Optional

# Notice kinds.
AI_FAILED = "ai_failed"
FALLBACK = "fallback"


@dataclass
class CurationNotice:
    """A single note recorded during curation."""

    kind: str
    message: str


_notices: contextvars.ContextVar[Optional[List[CurationNotice]]] = contextvars.ContextVar(
    "curation_notices", default=None
)


def start_collecting() -> None:
    """Begin a fresh notice collection for the current task."""
    _notices.set([])


def record_notice(kind: str, message: str) -> None:
    """Record a notice for the current refresh.

    Safe to call when no collection is active (for example during a direct
    curation call from a test): the notice is simply dropped.
    """
    notices = _notices.get()
    if notices is None:
        return
    notices.append(CurationNotice(kind=kind, message=message))


def record_ai_failure(message: str) -> None:
    """Record that the AI request failed, which fails the whole refresh."""
    record_notice(AI_FAILED, message)


def record_fallback(message: str) -> None:
    """Record that a fallback algorithm was used, which does not fail the refresh."""
    record_notice(FALLBACK, message)


def collect_notices() -> List[CurationNotice]:
    """Return the notices recorded so far for the current refresh."""
    return list(_notices.get() or [])


def stop_collecting() -> List[CurationNotice]:
    """Return the collected notices and clear the collector."""
    notices = collect_notices()
    _notices.set(None)
    return notices


def summarize(notices: List[CurationNotice]) -> Optional[str]:
    """Join notice messages into one human-readable string, or ``None``."""
    if not notices:
        return None
    # De-duplicate while preserving order: the same reason can be recorded by
    # more than one layer (e.g. a fallback helper and its caller).
    seen = set()
    parts = []
    for notice in notices:
        if notice.message in seen:
            continue
        seen.add(notice.message)
        parts.append(notice.message)
    return " ".join(parts)


def has_ai_failure(notices: List[CurationNotice]) -> bool:
    """Return ``True`` when any notice indicates the AI request failed."""
    return any(notice.kind == AI_FAILED for notice in notices)
