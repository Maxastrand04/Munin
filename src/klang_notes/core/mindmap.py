"""Rendering an Outline into a Mindmap page with Timestamp links."""

import json
import re
from pathlib import Path

from klang_notes.core.transcribe import get_source

_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "mindmaps"
_STAMP = re.compile(r"\[(\d+):([0-5]\d)\]")
_SECONDS_PER_MINUTE = 60

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
    Transcript's Source, `file://<path>#t=<s>`, with the path percent-encoded.
    The link is inline HTML, since Markmap's Markdown parser drops `file:`
    links. Text without a stamp stays as written.

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


def link_stamps(outline: str, source: Path) -> str:
    """Replace each `[m:ss]` stamp with an `<a>` linking to `source` at that second.

    Minutes may count past 59, so `[75:03]` links to 4503 s. The link text is the
    stamp without its brackets.
    """

    def link(stamp: re.Match[str]) -> str:
        minutes, seconds = int(stamp[1]), int(stamp[2])
        offset_s = minutes * _SECONDS_PER_MINUTE + seconds
        return f'<a href="{source.as_uri()}#t={offset_s}">{minutes}:{seconds:02d}</a>'

    return _STAMP.sub(link, outline)


def _page_html(transcript_id: str, outline: str) -> str:
    outline_json = json.dumps(outline, ensure_ascii=False).replace("<", "\\u003c")
    return _PAGE.format(transcript_id=transcript_id, outline_json=outline_json)
