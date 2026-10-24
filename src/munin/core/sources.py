"""What a Source is, and telling a YouTube or KTH Play URL from a local path."""

import os
from collections.abc import Callable
from pathlib import Path

from munin.core.kthplay import KthPlaySource
from munin.core.youtube import YouTubeSource, parse_youtube_url

Video = YouTubeSource | KthPlaySource
"""A Source that is downloaded before it is transcribed."""

Source = Path | Video
"""A local audio or video file, a YouTube video, or a KTH Play video."""

Download = Callable[[Video, Path], Path]
"""Takes a video and a work folder, writes the video's audio, or for KTH Play its video file, into the folder, and returns that file's path.

Raises `SourceError` naming the video's `url` when the file cannot be fetched.
"""


def parse_source(text: str | os.PathLike[str]) -> Source:
    """Return the video `text` points at, or `text` as a Path when it is neither a YouTube nor a KTH Play video URL.

    The YouTube check runs first, per `parse_youtube_url`, then the KTH Play
    check, per `parse_kthplay_url`. The Path is returned as given, with no `~`
    expansion, resolving, or check that it exists.
    """
    return parse_youtube_url(os.fspath(text)) or Path(text)
