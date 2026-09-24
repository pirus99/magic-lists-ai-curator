"""Tests for server-specific database path resolution."""
import os

from backend.database import get_database_path


def test_navidrome_uses_configured_legacy_path(monkeypatch):
    """Navidrome must keep using the existing database without a suffix."""
    monkeypatch.setenv("SERVER_TYPE", "navidrome")
    monkeypatch.setenv("DATABASE_PATH", "/app/data/magiclists.db")

    assert get_database_path() == "/app/data/magiclists.db"


def test_navidrome_preserves_legacy_path_when_server_type_is_missing(monkeypatch):
    """Navidrome remains the default and must not rename existing storage."""
    monkeypatch.delenv("SERVER_TYPE", raising=False)
    monkeypatch.setenv("DATABASE_PATH", "magiclists.db")

    assert get_database_path() == "magiclists.db"


def test_jellyfin_uses_isolated_sibling_database(monkeypatch):
    """Jellyfin uses a separate database derived from the base path."""
    monkeypatch.setenv("SERVER_TYPE", "jellyfin")
    monkeypatch.setenv("DATABASE_PATH", "/app/data/magiclists.db")

    assert get_database_path() == "/app/data/magiclists_jellyfin.db"


def test_database_path_handles_missing_extension(monkeypatch):
    """A missing extension is preserved when isolating a client database."""
    monkeypatch.setenv("SERVER_TYPE", "JELLYFIN")
    monkeypatch.setenv("DATABASE_PATH", "data/magiclists")

    assert get_database_path() == "data/magiclists_jellyfin"


def test_navidrome_uses_container_default(monkeypatch):
    """The container default remains the legacy magiclists.db filename."""
    monkeypatch.delenv("SERVER_TYPE", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setattr(os.path, "exists", lambda path: path == "/app/data")

    assert get_database_path() == "/app/data/magiclists.db"
