"""KTH Play videos as a Source: telling their URLs apart, linking into them, and downloading their video."""

from dataclasses import dataclass
import re
from pathlib import Path
from urllib.parse import urlsplit

from munin.core import ytdlp

_SCHEMES = {"http", "https"}
_HOST = "play.kth.se"
_ENTRY_ID = re.compile(r"[0-9]_[a-z0-9]{8}")


@dataclass(frozen=True)
class KthPlaySource:
    """A KTH Play video, identified by its Kaltura entry ID, such as `0_1zk8obn5`."""

    entry_id: str

    @property
    def url(self) -> str:
        """The fixed lecture address, `https://play.kth.se/media/t/<entry_id>`.

        Every accepted URL form of one video gives this same string, so it is the
        cache key for the video's Transcript and the Mindmap's lecture link.
        """
        return f"https://play.kth.se/media/t/{self.entry_id}"

    def timestamp_url(self, offset_s: int) -> str:
        """Return the Timestamp link that opens the video at `offset_s` seconds.

        The link is `https://play.kth.se/media/t/<entry_id>?st=<offset_s>`.
        """
        return f"{self.url}?st={offset_s}"


def parse_kthplay_url(text: str) -> KthPlaySource | None:
    """Return the video `text` points at, or None when `text` is not a KTH Play video URL.

    Accepted forms, with `http://`, `https://` or no scheme:

    - `play.kth.se/media/<slug>/<entry id>`, where the slug is any one
      non-empty path segment,
    - `play.kth.se/media/t/<entry id>`,
    - `play.kth.se/media/<entry id>`.

    The host is matched without regard to case. One trailing slash is allowed,
    and any query or fragment, such as `?st=90`, is ignored. The entry ID must be
    a digit, an underscore and 8 characters from `a-z` and `0-9`. Channels,
    playlists, search pages, other hosts such as `www.play.kth.se`, and paths
    with more than one slug segment return None.
    """
    try:
        parsed = urlsplit(text if "://" in text else f"https://{text}")
    except ValueError:
        return None
    if parsed.scheme not in _SCHEMES or parsed.netloc.lower() != _HOST:
        return None
    segments = parsed.path.removesuffix("/").split("/")
    if len(segments) < 3 or len(segments) > 4 or segments[:2] != ["", "media"]:
        return None
    entry_id = segments[-1]
    if len(segments) == 4 and not segments[2]:
        return None
    return KthPlaySource(entry_id) if _ENTRY_ID.fullmatch(entry_id) else None


def download_smallest_video(video: KthPlaySource, workdir: Path) -> Path:
    """Download the lowest-quality video file of `video` into `workdir` and return the file's path.

    This is the default `Download` for KTH Play. See ADR-0013. It writes nothing
    to stdout, which the stdio MCP server uses for its messages.

    Raises `SourceError` naming `video.url`, with the download's reason, when the
    video is restricted, removed, or unreachable, for example because the
    machine is offline.
    """
    return ytdlp.fetch(video.url, workdir, "worst")
