"""Rendering an Outline into a Mindmap page with Timestamp links."""

import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal

from klang_notes.core.errors import OutlineError
from klang_notes.core.sources import Source
from klang_notes.core.stamps import STAMP, format_stamp, stamp_seconds
from klang_notes.core.transcribe import CacheEntry, cached_entry
from klang_notes.core.youtube import YouTubeSource

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "mindmaps"

_ASSETS = Path(__file__).with_name("mindmap_assets")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_BULLET = re.compile(r"^(\s*)(?:[-+*]|\d+[.)])\s+(.+)$")
_SPACE_RUN = re.compile(r"\s{2,}")


@dataclass(frozen=True)
class UnlinkedStamp:
    """A stamp in a node label that `render_mindmap` left as plain text.

    `label` is the node's label as written in the Outline, every stamp
    included, so `Gauss [0:02] [1:75]` stays whole. `stamp` is the stamp's text,
    brackets included, such as `[1:75]`. `reason` is `"malformed"` when
    `stamp_seconds` rejects its shape, and `"past_end"` when it is well-formed
    but later than the Source's duration.
    """

    label: str
    stamp: str
    reason: Literal["malformed", "past_end"]


@dataclass(frozen=True)
class RenderResult:
    """What `render_mindmap` tells the caller about the page it wrote.

    `page` is the page's absolute path. `unlinked` holds one entry per bad stamp
    occurrence in node labels, in Outline order and left to right within a
    label, so the same bad stamp on two nodes gives two entries. It is empty
    when every stamp linked.
    """

    page: Path
    unlinked: tuple[UnlinkedStamp, ...]


def render_mindmap(
    transcript_id: str,
    outline: str,
    *,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
) -> RenderResult:
    """Write the Mindmap page for an Outline and return its path and any unlinked stamps.

    Markdown headings and nested list items become nodes. Each `STAMP` match in
    a node label is resolved with `stamp_seconds`. A stamp at or before the
    Transcript's stored audio duration becomes a Timestamp link to the
    Transcript's Source and leaves the label. A malformed stamp, or one past
    the duration, stays in the label as plain text with no link, and is
    reported in `unlinked`. Bracketed text that is not a `STAMP` match stays in
    the label and is never reported. Prose following a node supplies its
    explanation when present; its stamps are neither linked nor reported, and
    this tool does not generate prose.

    The page is `<transcript_id>.html` in `output_dir`, replacing any earlier
    page for the same Transcript, and is written even when stamps go unlinked.
    CSS, JavaScript, and Outline data are embedded, so it opens straight from
    disk without network access. Radial rings is the default layout; settings
    also offers Topic circles.

    `cache_dir` defaults to the per-user cache folder for klang-notes.
    `output_dir` defaults to `mindmaps/` at the repo root, found from this
    file's location, so the server's working directory does not matter.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID, and
    `OutlineError` when the Outline has no headings or list items. Either way it
    writes nothing.
    """
    entry = cached_entry(transcript_id, cache_dir=cache_dir)
    nodes, unlinked = _outline_nodes(outline, entry)
    content = _page_html(transcript_id, nodes, entry.source)
    page = (output_dir or _DEFAULT_OUTPUT_DIR).resolve() / f"{transcript_id}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    return RenderResult(page, unlinked)


def _timestamp_url(source: Source, offset_s: int) -> str:
    if isinstance(source, YouTubeSource):
        return source.timestamp_url(offset_s)
    return f"{source.as_uri()}#t={offset_s}"


def _outline_nodes(outline: str, entry: CacheEntry) -> tuple[list[dict], tuple[UnlinkedStamp, ...]]:
    """Read heading/list hierarchy and optional prose without interpreting HTML.

    A single top-level node is the main topic. Multiple top-level nodes get a
    common main topic. All labels and explanations are displayed as plain text.
    Returns the nodes and every node label's bad stamps, in Outline order.
    """
    nodes: list[dict] = []
    unlinked: list[UnlinkedStamp] = []
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
        shown, links, bad = _resolve_stamps(label, entry)
        unlinked.extend(bad)
        nodes.append(
            {
                "id": current,
                "parent": parent,
                "label": shown,
                "links": links,
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
    return nodes, tuple(unlinked)


def _resolve_stamps(label: str, entry: CacheEntry) -> tuple[str, list[dict], list[UnlinkedStamp]]:
    """Return the label without its linked stamps, their links, and its bad stamps."""
    shown, links, unlinked = label, [], []
    for stamp in STAMP.finditer(label):
        offset = stamp_seconds(stamp[0])
        if offset is None:
            unlinked.append(UnlinkedStamp(label, stamp[0], "malformed"))
        elif offset > entry.duration_s:
            unlinked.append(UnlinkedStamp(label, stamp[0], "past_end"))
        else:
            links.append({"text": format_stamp(offset), "url": _timestamp_url(entry.source, offset)})
            shown = shown.replace(stamp[0], "", 1)
    return _SPACE_RUN.sub(" ", shown).strip(), links, unlinked


def _page_html(transcript_id: str, nodes: list[dict], source: Source) -> str:
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
    return re.sub(
        r"__(?:CSS|JS|DATA|PAGE|TITLE|SOURCE)__",
        lambda match: replacements[match[0]],
        template,
    )


def _script_safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")
