"""Configuration module for MagicLists backend."""
import os

NAVIDROME_URL = os.getenv("NAVIDROME_URL", "")
NAVIDROME_USERNAME = os.getenv("NAVIDROME_USERNAME", "")
NAVIDROME_PASSWORD = os.getenv("NAVIDROME_PASSWORD", "")
