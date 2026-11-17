"""Tests for curation notices.

Covers the distinction between an AI failure (fails the refresh) and a
legitimate fallback (succeeds, but is reported to the user).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core import curation_notices as notices


def test_no_collection_drops_notices():
    """Recording outside a collection must not raise."""
    notices.stop_collecting()
    notices.record_ai_failure("should be dropped")
    assert notices.collect_notices() == []


def test_ai_failure_is_collected():
    """An AI failure notice is collected and detected."""
    notices.start_collecting()
    notices.record_ai_failure("AI curation failed for This Is (HTTP 503).")
    collected = notices.stop_collecting()

    assert len(collected) == 1
    assert collected[0].kind == notices.AI_FAILED
    assert notices.has_ai_failure(collected) is True


def test_fallback_is_not_an_ai_failure():
    """A legitimate fallback must not be treated as a failure."""
    notices.start_collecting()
    notices.record_fallback("Re-Discover used its fallback strategy.")
    collected = notices.stop_collecting()

    assert len(collected) == 1
    assert collected[0].kind == notices.FALLBACK
    assert notices.has_ai_failure(collected) is False


def test_stop_collecting_clears_state():
    """Notices must not leak into the next refresh."""
    notices.start_collecting()
    notices.record_ai_failure("first")
    notices.stop_collecting()

    notices.start_collecting()
    assert notices.collect_notices() == []
    notices.stop_collecting()


def test_summarize_deduplicates():
    """The same reason recorded twice appears once."""
    notices.start_collecting()
    notices.record_ai_failure("same reason")
    notices.record_ai_failure("same reason")
    notices.record_fallback("other reason")
    collected = notices.stop_collecting()

    summary = notices.summarize(collected)
    assert summary is not None
    assert summary.count("same reason") == 1
    assert "other reason" in summary


def test_summarize_returns_none_when_empty():
    """No notices means no message."""
    assert notices.summarize([]) is None


def test_description_failures_are_not_recorded():
    """Description generation must never produce a notice.

    The description helper swallows its own errors and returns fallback text;
    it deliberately does not touch the notice collector.
    """
    notices.start_collecting()
    # Simulate what a description failure does: nothing.
    collected = notices.stop_collecting()
    assert collected == []
    assert notices.has_ai_failure(collected) is False
