"""The one place Munin calls yt-dlp, shared by every video site's module."""

from pathlib import Path

from munin.core.errors import SourceError


def fetch(url: str, workdir: Path, format_selector: str, format_sort: list[str] | None = None) -> Path:
    """Download `url` with yt-dlp into `workdir` using `format_selector` and return the file's path.

    `format_sort` goes to yt-dlp as its `format_sort` option and sets the order
    `format_selector` picks from, so `["+size", "+br"]` with `"b"` takes the
    smallest file. None leaves yt-dlp's default order.

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
    if format_sort is not None:
        options["format_sort"] = format_sort
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(url, download=True)
            return Path(downloader.prepare_filename(info))
    except DownloadError as error:
        raise SourceError(url, str(error)) from error
