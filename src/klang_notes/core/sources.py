"""What a Source is, and telling a YouTube URL from a local path."""

import os
from pathlib import Path

from klang_notes.core.youtube import YouTubeSource, parse_youtube_url

Source = Path | YouTubeSource
"""A local audio or video file, or a YouTube video."""


def parse_source(text: str | os.PathLike[str]) -> Source:
    """Return the YouTube video `text` points at, or `text` as a Path when it is not a YouTube video URL.

    The YouTube check runs first, per `parse_youtube_url`. The Path is returned
    as given, with no `~` expansion, resolving, or check that it exists.
    """
    return parse_youtube_url(os.fspath(text)) or Path(text)
