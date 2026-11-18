"""Tests for application version parsing and comparison."""

from backend.services.version_service import (
    is_update_available,
    normalize_tag,
    parse_local_tag,
    version_key,
)


def test_parse_local_tag_skips_unreleased():
    changelog = "# Changelog\n\n## [Unreleased]\n\n## [1.2.1] - 2026-11-16\n"
    assert parse_local_tag(changelog) == "1.2.1"


def test_normalize_and_compare_semantic_versions():
    assert normalize_tag("v1.2.1") == "1.2.1"
    assert version_key("1.2.1") == (1, 2, 1)
    assert is_update_available("1.2.1", "1.3.0") is True
    assert is_update_available("1.3.0", "1.2.1") is False
    assert is_update_available("1.2", "1.2.0") is False
