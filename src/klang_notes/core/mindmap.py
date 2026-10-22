"""Rendering an Outline into a Mindmap page with Timestamp links."""

import json
import re
from pathlib import Path

from klang_notes.core.sources import Source
from klang_notes.core.stamps import STAMP, format_stamp, stamp_seconds
from klang_notes.core.transcribe import get_source
from klang_notes.core.youtube import YouTubeSource

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "mindmaps"

_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Mindmap {transcript_id}</title>
<style>
  html, body {{ margin: 0; height: 100%; }}
  .markmap {{ width: 100vw; height: 100vh; }}
  .markmap > svg {{ width: 100%; height: 100%; }}
</style>
</head>
<body>
<div class="markmap"><script type="text/template"></script></div>
<script>
  document.querySelector(".markmap script").textContent = {outline_json};
</script>
<script src="https://cdn.jsdelivr.net/npm/markmap-autoloader@0.18"></script>
</body>
</html>
"""


def render_mindmap(
    transcript_id: str,
    outline: str,
    *,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Write the Mindmap page for an Outline and return the page's absolute path.

    Each `[m:ss]` stamp in the Outline becomes a Timestamp link to the
    Transcript's Source, per `link_stamps`. The link is inline HTML, since
    Markmap's Markdown parser drops `file:` links. Text without a stamp stays as
    written.

    The page is `<transcript_id>.html` in `output_dir`, replacing any earlier
    page for the same Transcript. It loads Markmap from a CDN and embeds the
    Outline, so it opens straight from disk.

    `cache_dir` defaults to the per-user cache folder for klang-notes.
    `output_dir` defaults to `mindmaps/` at the repo root, found from this
    file's location, so the server's working directory does not matter.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID, and
    writes nothing.
    """
    source = get_source(transcript_id, cache_dir=cache_dir)
    linked = link_stamps(outline, source)
    page = (output_dir or _DEFAULT_OUTPUT_DIR).resolve() / f"{transcript_id}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_page_html(transcript_id, linked), encoding="utf-8")
    return page


def link_stamps(outline: str, source: Source) -> str:
    """Replace each `[m:ss]` stamp with an `<a>` linking to `source` at that second.

    A local Source links to `file://<path>#t=<s>`, with the path percent-encoded.
    A YouTube Source links to its `timestamp_url`,
    `https://www.youtube.com/watch?v=<id>&t=<s>s`.

    Minutes may count past 59, so `[75:03]` links to 4503 s. The link text is the
    stamp written as `m:ss`.
    """

    def link(stamp: re.Match[str]) -> str:
        offset_s = stamp_seconds(stamp)
        return f'<a href="{_timestamp_url(source, offset_s)}">{format_stamp(offset_s)}</a>'

    return STAMP.sub(link, outline)


def _timestamp_url(source: Source, offset_s: int) -> str:
    if isinstance(source, YouTubeSource):
        return source.timestamp_url(offset_s)
    return f"{source.as_uri()}#t={offset_s}"


def _page_html(transcript_id: str, outline: str) -> str:
    return _PAGE.format(transcript_id=transcript_id, outline_json=_script_safe_json(outline))


def _script_safe_json(text: str) -> str:
    return json.dumps(text, ensure_ascii=False).replace("<", "\\u003c")
