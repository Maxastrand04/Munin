"""The one place Munin calls yt-dlp, shared by every video site's module."""

from pathlib import Path

from munin.core.errors import SourceError


def fetch(url: str, workdir: Path, format_selector: str) -> Path:
    """Download `url` with yt-dlp into `workdir` using `format_selector` and return the file's path.

    It imports yt-dlp on call, so parsing URLs never loads it. It writes nothing
    to stdout, which the stdio MCP server uses for its messages.

    Raises `SourceError` naming `url`, with yt-dlp's reason, when the download fails.
    """
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    options = {
        "format": format_selector,
        "outtmpl": str(workdir / "download.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "noprogress": True,
        "cachedir": False,
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            return Path(downloader.prepare_filename(info))
    except DownloadError as error:
        raise SourceError(url, str(error)) from error
