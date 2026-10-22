"""YouTube videos as a Source: telling their URLs apart, linking into them, and downloading their audio."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from klang_notes.core.errors import SourceError

_SCHEMES = {"http", "https"}
_SHORT_HOST = "youtu.be"
_WATCH_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com"}
_WATCH_PATH = "/watch"
_VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}")


@dataclass(frozen=True)
class YouTubeSource:
    """A YouTube video, identified by its 11-character video ID."""

    video_id: str

    @property
    def url(self) -> str:
        """The canonical watch URL, `https://www.youtube.com/watch?v=<video_id>`.

        Every accepted URL form of one video gives this same string, so it is the
        cache key for the video's Transcript.
        """
        return f"https://www.youtube.com/watch?v={self.video_id}"

    def timestamp_url(self, offset_s: int) -> str:
        """Return the Timestamp link that opens the video at `offset_s` seconds.

        The link is `https://www.youtube.com/watch?v=<video_id>&t=<offset_s>s`.
        """
        return f"{self.url}&t={offset_s}s"


Download = Callable[[YouTubeSource, Path], Path]
"""Takes a video and a work folder, writes the video's audio track into the folder, and returns that file's path.

Raises `SourceError` naming the video's `url` when the audio cannot be fetched.
"""


def parse_youtube_url(text: str) -> YouTubeSource | None:
    """Return the video `text` points at, or None when `text` is not a YouTube video URL.

    Accepted forms, with `http://`, `https://` or no scheme:

    - `youtube.com/watch?v=<id>`, `www.youtube.com/watch?v=<id>` and
      `m.youtube.com/watch?v=<id>`, with any other query parameters, such as
      `list` or `t`, in any order and ignored,
    - `youtu.be/<id>`, with any query parameters ignored.

    The ID must be 11 characters from `A-Z`, `a-z`, `0-9`, `_` and `-`.
    Shorts, embeds, live streams, bare playlists and other hosts return None.
    """
    try:
        parsed = urlsplit(text if "://" in text else f"https://{text}")
    except ValueError:
        return None
    if parsed.scheme not in _SCHEMES:
        return None
    host = parsed.netloc.lower()
    if host == _SHORT_HOST:
        video_id = parsed.path.removeprefix("/")
    elif host in _WATCH_HOSTS and parsed.path == _WATCH_PATH:
        video_id = parse_qs(parsed.query).get("v", [""])[0]
    else:
        return None
    return YouTubeSource(video_id) if _VIDEO_ID.fullmatch(video_id) else None


def download_audio(video: YouTubeSource, workdir: Path) -> Path:
    """Download only the audio track of `video` with yt-dlp into `workdir` and return the file's path.

    This is the default `Download`. It imports yt-dlp on call, so parsing URLs
    never loads it.

    Raises `SourceError` naming `video.url`, with yt-dlp's reason, when the video
    is private, removed, or unreachable, for example because the machine is
    offline.
    """
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    options = {
        "format": "bestaudio",
        "outtmpl": str(workdir / "download.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "cachedir": False,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(video.url, download=True)
            return Path(downloader.prepare_filename(info))
    except DownloadError as error:
        raise SourceError(video.url, str(error)) from error
