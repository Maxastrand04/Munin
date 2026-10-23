"""Rendering an Outline into a Mindmap page with Timestamp links."""

import json
import re
from html import escape
from pathlib import Path

from klang_notes.core.errors import OutlineError
from klang_notes.core.sources import Source
from klang_notes.core.stamps import STAMP, format_stamp, stamp_seconds
from klang_notes.core.transcribe import get_source
from klang_notes.core.youtube import YouTubeSource

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "mindmaps"

_ASSETS = Path(__file__).with_name("mindmap_assets")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_BULLET = re.compile(r"^(\s*)(?:[-+*]|\d+[.)])\s+(.+)$")


def render_mindmap(
    transcript_id: str,
    outline: str,
    *,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    """Write the Mindmap page for an Outline and return the page's absolute path.

    Markdown headings and nested list items become nodes. Each `[m:ss]` stamp
    becomes a Timestamp link to the Transcript's Source. Prose following a node
    supplies its explanation when present; this tool does not generate prose.

    The page is `<transcript_id>.html` in `output_dir`, replacing any earlier
    page for the same Transcript. CSS, JavaScript, and Outline data are embedded,
    so it opens straight from disk without network access. Topic circles is the
    default layout; settings also offers Radial rings.

    `cache_dir` defaults to the per-user cache folder for klang-notes.
    `output_dir` defaults to `mindmaps/` at the repo root, found from this
    file's location, so the server's working directory does not matter.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID, and
    `OutlineError` when the Outline has no headings or list items. Either way it
    writes nothing.
    """
    source = get_source(transcript_id, cache_dir=cache_dir)
    content = _page_html(transcript_id, outline, source)
    page = (output_dir or _DEFAULT_OUTPUT_DIR).resolve() / f"{transcript_id}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    return page


def _timestamp_url(source: Source, offset_s: int) -> str:
    if isinstance(source, YouTubeSource):
        return source.timestamp_url(offset_s)
    return f"{source.as_uri()}#t={offset_s}"


def _outline_nodes(outline: str, source: Source) -> list[dict]:
    """Read heading/list hierarchy and optional prose without interpreting HTML.

    A single top-level node is the main topic. Multiple top-level nodes get a
    common main topic. All labels and explanations are displayed as plain text.
    """
    nodes: list[dict] = []
    headings: list[tuple[int, int]] = []
    bullets: list[tuple[int, int]] = []
    current: int | None = None
    for line in outline.expandtabs(4).splitlines():
        heading = _HEADING.match(line)
        bullet = _BULLET.match(line)
        if heading:
            level, label = len(heading[1]), heading[2]
            while headings and headings[-1][0] >= level:
                headings.pop()
            parent = headings[-1][1] if headings else None
            bullets.clear()
        elif bullet:
            level, label = len(bullet[1]), bullet[2]
            while bullets and bullets[-1][0] >= level:
                bullets.pop()
            parent = (
                bullets[-1][1] if bullets else headings[-1][1] if headings else None
            )
        else:
            if line.strip() and current is not None:
                previous = nodes[current]["explanation"]
                nodes[current]["explanation"] = f"{previous}\n{line.strip()}".strip()
            continue
        current = len(nodes)
        nodes.append(
            {
                "id": current,
                "parent": parent,
                "label": STAMP.sub("", label).strip(),
                "links": [
                    {
                        "text": format_stamp(stamp_seconds(stamp)),
                        "url": _timestamp_url(source, stamp_seconds(stamp)),
                    }
                    for stamp in STAMP.finditer(label)
                ],
                "explanation": "",
            }
        )
        (headings if heading else bullets).append((level, current))
    if not nodes:
        raise OutlineError()
    if len([node for node in nodes if node["parent"] is None]) != 1:
        for node in nodes:
            node["id"] += 1
            node["parent"] = 0 if node["parent"] is None else node["parent"] + 1
        nodes.insert(
            0,
            {
                "id": 0,
                "parent": None,
                "label": "Lecture notes",
                "links": [],
                "explanation": "",
            },
        )
    return nodes


def _page_html(transcript_id: str, outline: str, source: Source) -> str:
    nodes = _outline_nodes(outline, source)
    title = nodes[0]["label"] or "Mindmap"
    source_url = source.url if isinstance(source, YouTubeSource) else source.as_uri()
    replacements = {
        "__CSS__": (_ASSETS / "mindmap.css").read_text(encoding="utf-8"),
        "__JS__": (_ASSETS / "mindmap.js").read_text(encoding="utf-8"),
        "__DATA__": _script_safe_json(nodes),
        "__PAGE__": _script_safe_json(
            {"title": title, "source_url": source_url, "transcript_id": transcript_id}
        ),
        "__TITLE__": escape(title),
        "__SOURCE__": escape(source_url, quote=True),
    }
    template = (_ASSETS / "mindmap.html").read_text(encoding="utf-8")
    # One substitution pass keeps token-like text in the Outline literal.
    return re.sub(
        r"__(?:CSS|JS|DATA|PAGE|TITLE|SOURCE)__",
        lambda match: replacements[match[0]],
        template,
    )


def _script_safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")
