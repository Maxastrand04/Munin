"""Rendering an Outline into a Mindmap page with Timestamp links."""

import base64
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Literal

from munin.core import pdf
from munin.core.cache_paths import default_cache_dir
from munin.core.errors import OutlineError
from munin.core.slides import deck_path
from munin.core.sources import Source, Video
from munin.core.stamps import STAMP, display_stamp, stamp_seconds
from munin.core.transcribe import CacheEntry, cached_entry

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "mindmaps"

_ASSETS = Path(__file__).with_name("mindmap_assets")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)(?:\s+#+)?\s*$")
_BULLET = re.compile(r"^(\s*)(?:[-+*]|\d+[.)])\s+(.+)$")
_SPACE_RUN = re.compile(r"\s{2,}")
_SLIDE_MARKER = re.compile(r"\[slide(?:\s[^\]]*)?\]", re.IGNORECASE)
_SLIDE_NUMBER = re.compile(r"\[slide\s+(\d+)\]", re.IGNORECASE)


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
class UnlinkedSlide:
    """A slide marker in a node label that `render_mindmap` could not link to a Slide.

    `label` is the node's label as written in the Outline, every marker and
    stamp included. `slide` is the marker's text as written, brackets
    included, such as `[slide 99]` or `[Slide x]`. `reason` is `"malformed"`
    when the marker is not `slide` and a positive whole number, `"past_end"`
    when its number is past the Deck's last Slide, and `"no_deck"` when the
    Transcript has no Deck attached, whatever the marker's shape.
    """

    label: str
    slide: str
    reason: Literal["malformed", "past_end", "no_deck"]


@dataclass(frozen=True)
class RenderResult:
    """What `render_mindmap` tells the caller about the page it wrote.

    `page` is the page's absolute path. `unlinked` holds one entry per bad stamp
    occurrence in node labels, in Outline order and left to right within a
    label, so the same bad stamp on two nodes gives two entries. It is empty
    when every stamp linked. `unlinked_slides` holds one entry per bad slide
    marker occurrence in node labels, in the same order, and is empty when
    every marker linked or the Outline has none.
    """

    page: Path
    unlinked: tuple[UnlinkedStamp, ...]
    unlinked_slides: tuple[UnlinkedSlide, ...] = ()


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

    A slide marker is a bracket starting with `slide`, in any case, such as
    `[slide 3]` or `[Slide 3]`. A node lists any number of Slides, one marker
    each, and a Slide may appear on any number of nodes. A marker naming a
    Slide of the Deck attached to the Transcript links that Slide to the node
    and leaves the label. A malformed marker, one past the Deck's last Slide,
    or any marker when the Transcript has no Deck, stays in the label as plain
    text and is reported in `unlinked_slides`. A Slide listed twice on one
    node counts once and is not reported. Markers in prose are neither linked
    nor reported. Clicking a node shows its linked Slides in its panel, top to
    bottom in Slide order, below the explanation and above the Source link,
    each captioned and alt-texted `Slide N`. A node with no linked Slide has no
    slide area. The page embeds each linked Slide's `image` exactly once, as a
    base64 `data:image/png` URI, however many nodes list it, and embeds no
    Slide that no node links.

    Each topic, meaning each node one level under the main topic, gives its
    branch one colour. A node whose label, as the page shows it after linked
    stamps and Slide markers leave it, starts with `Övning:` or `Exempel:` in
    any case is an example or exercise, and so is every node under one. These
    are orange: an orange of hue 25 to 45 degrees that no topic gets, since
    every topic's hue sits at least 20 degrees from it however many topics the
    Outline has. An orange node's border, background, selected fill, stamps,
    and panel path and rule are orange, and so is the edge into it from
    another orange node or from the main topic. The edge into the top example
    or exercise node of a branch keeps its topic's colour. A topic that is
    itself an example or exercise takes no topic colour, so the topics after
    it get the colours they would have had without it. The main topic stays in
    its neutral colours whatever its label. `Övning 2:`, `Övningar:`, and a
    label with `Övning:` or `Exempel:` anywhere but the start are not examples
    or exercises.

    The page is `<transcript_id>.html` in `output_dir`, replacing any earlier
    page for the same Transcript, and is written even when stamps go unlinked.
    CSS, JavaScript, Outline data and Slide images are embedded, so it opens straight from
    disk without network access. Radial rings is the default layout; settings
    also offers Topic circles.

    `cache_dir` defaults to the per-user cache folder for Munin.
    `output_dir` defaults to `mindmaps/` at the repo root, found from this
    file's location, so the server's working directory does not matter.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID, and
    `OutlineError` when the Outline has no headings or list items. Either way it
    writes nothing.
    """
    entry = cached_entry(transcript_id, cache_dir=cache_dir)
    deck = deck_path(transcript_id, cache_dir or default_cache_dir())
    deck_pages = pdf.page_count(deck) if deck.is_file() else None
    nodes, unlinked, unlinked_slides = _outline_nodes(outline, entry, deck_pages)
    linked = sorted({number for node in nodes for number in node["slides"]})
    content = _page_html(transcript_id, nodes, entry.source, _slide_images(deck, linked))
    page = (output_dir or _DEFAULT_OUTPUT_DIR).resolve() / f"{transcript_id}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    return RenderResult(page, unlinked, unlinked_slides)


def _slide_images(deck: Path, numbers: list[int]) -> dict[str, str]:
    """Return each numbered Slide of the Deck as a PNG data URI, keyed by its number as text."""
    return {
        str(number): "data:image/png;base64," + base64.b64encode(pdf.page_png(deck, number)).decode()
        for number in numbers
    }


def _timestamp_url(source: Source, offset_s: int) -> str:
    if isinstance(source, Video):
        return source.timestamp_url(offset_s)
    return f"{source.as_uri()}#t={offset_s}"


def _outline_nodes(
    outline: str, entry: CacheEntry, deck_pages: int | None
) -> tuple[list[dict], tuple[UnlinkedStamp, ...], tuple[UnlinkedSlide, ...]]:
    """Read heading/list hierarchy and optional prose without interpreting HTML.

    A single top-level node is the main topic. Multiple top-level nodes get a
    common main topic. All labels and explanations are displayed as plain text.
    Returns the nodes, and every node label's bad stamps and bad slide markers,
    in Outline order. `deck_pages` is None when the Transcript has no Deck.
    """
    nodes: list[dict] = []
    unlinked: list[UnlinkedStamp] = []
    unlinked_slides: list[UnlinkedSlide] = []
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
        shown, slides, bad_slides = _resolve_slides(label, shown, deck_pages)
        unlinked_slides.extend(bad_slides)
        nodes.append(
            {
                "id": current,
                "parent": parent,
                "label": shown,
                "links": links,
                "slides": slides,
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
                "slides": [],
                "explanation": "",
            },
        )
    return nodes, tuple(unlinked), tuple(unlinked_slides)


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
            links.append({"text": display_stamp(offset), "url": _timestamp_url(entry.source, offset)})
            shown = shown.replace(stamp[0], "", 1)
    return _SPACE_RUN.sub(" ", shown).strip(), links, unlinked


def _resolve_slides(
    label: str, shown: str, deck_pages: int | None
) -> tuple[str, list[int], list[UnlinkedSlide]]:
    """Return the label without its linked slide markers, their sorted Slide numbers, and its bad markers."""
    numbers: set[int] = set()
    unlinked: list[UnlinkedSlide] = []
    for marker in _SLIDE_MARKER.finditer(label):
        match = _SLIDE_NUMBER.fullmatch(marker[0])
        number = int(match[1]) if match else 0
        if deck_pages is None:
            unlinked.append(UnlinkedSlide(label, marker[0], "no_deck"))
        elif number < 1:
            unlinked.append(UnlinkedSlide(label, marker[0], "malformed"))
        elif number > deck_pages:
            unlinked.append(UnlinkedSlide(label, marker[0], "past_end"))
        else:
            numbers.add(number)
            shown = shown.replace(marker[0], "", 1)
    return _SPACE_RUN.sub(" ", shown).strip(), sorted(numbers), unlinked


def _page_html(transcript_id: str, nodes: list[dict], source: Source, slide_images: dict[str, str]) -> str:
    title = nodes[0]["label"] or "Mindmap"
    source_url = source.url if isinstance(source, Video) else source.as_uri()
    replacements = {
        "__CSS__": (_ASSETS / "mindmap.css").read_text(encoding="utf-8"),
        "__JS__": (_ASSETS / "mindmap.js").read_text(encoding="utf-8"),
        "__DATA__": _script_safe_json(nodes),
        "__PAGE__": _script_safe_json(
            {"title": title, "source_url": source_url, "transcript_id": transcript_id, "slides": slide_images}
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
