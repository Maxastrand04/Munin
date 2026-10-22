"""Rendering an Outline into a Mindmap page with Timestamp links."""

import json
from pathlib import Path

from klang_notes.core.transcribe import get_source

_DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[3] / "mindmaps"

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

    The page is `<transcript_id>.html` in `output_dir`, replacing any earlier
    page for the same Transcript. It loads Markmap from a CDN and embeds the
    Outline, so it opens straight from disk.

    `cache_dir` defaults to the per-user cache folder for klang-notes.
    `output_dir` defaults to `mindmaps/` at the repo root, found from this
    file's location, so the server's working directory does not matter.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID, and
    writes nothing.
    """
    get_source(transcript_id, cache_dir=cache_dir)
    page = (output_dir or _DEFAULT_OUTPUT_DIR).resolve() / f"{transcript_id}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(_page_html(transcript_id, outline), encoding="utf-8")
    return page


def _page_html(transcript_id: str, outline: str) -> str:
    outline_json = json.dumps(outline, ensure_ascii=False).replace("<", "\\u003c")
    return _PAGE.format(transcript_id=transcript_id, outline_json=outline_json)
