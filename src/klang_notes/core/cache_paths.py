"""The per-user cache folder, through platformdirs."""

from pathlib import Path

from platformdirs import user_cache_path


def default_cache_dir() -> Path:
    """Return the per-user cache folder for klang-notes. The folder may not exist yet."""
    return user_cache_path("klang-notes")
