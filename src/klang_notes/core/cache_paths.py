"""The per-user cache folder, through platformdirs."""

from pathlib import Path

from platformdirs import user_cache_path


def default_cache_dir() -> Path:
    return user_cache_path("klang-notes")
