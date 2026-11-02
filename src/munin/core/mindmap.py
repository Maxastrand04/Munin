"""Rendering a JSON Outline into a Mindmap page with Timestamp links."""

import base64
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from munin.core import pdf
from munin.core.cache_ids import is_cache_id
from munin.core.cache_paths import default_cache_dir
from munin.core.errors import (
    OutlineStructureError,
    OutlineSyntaxError,
    UnknownDeckError,
)
from munin.core.latex import KATEX_OPTIONS, katex_css, katex_js
from munin.core.outline import check_outline
from munin.core.slides import deck_path, standalone_deck_path
from munin.core.sources import Source, Video
from munin.core.stamps import display_stamp, stamp_seconds
from munin.core.transcribe import CacheEntry, cached_entry

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_OUTPUT_DIR = _REPO_ROOT / "mindmaps"

_ASSETS = Path(__file__).with_name("mindmap_assets")


@dataclass(frozen=True)
class RenderResult:
    """What `render_mindmap` and `render_deck_mindmap` tell the caller about the page they wrote.

    `page` is the page's absolute path. A render that returns linked every
    stamp and every Slide number, since anything it could not link fails the
    render instead.
    """

    page: Path


def render_mindmap(
    transcript_id: str,
    outline: dict | str,
    *,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
) -> RenderResult:
    """Check a JSON Outline against the Transcript, write its Mindmap page, and return the page's path.

    `outline` is the Outline in the format `get_outline_schema` describes,
    either already parsed, as a dict, or as JSON text. Text that is not JSON,
    such as a Markdown Outline, raises `OutlineSyntaxError`.

    Before anything is rendered, one check reads the whole Outline and
    collects every problem it finds, in Outline order, each as an
    `OutlineProblem` naming its node by label path:

    - a root that is not one main-topic node, such as a list or a node of
      another type,
    - an unknown `type`,
    - a missing part, or a part the node's type does not have, such as an
      `explanation` on an exempel, a misspelled key, or `children` on an
      exempel or övning, even an empty list,
    - a part of the wrong kind, such as a `stamps` that is not a list of
      strings, or a Slide number that is not an integer, `true` included,
    - a blank `label`, `task` or step `calculation`,
    - a `label` on any node that starts with `Exempel:` or `Övning:`, in any
      case and with any spaces before the colon, since the page adds that
      prefix to exempel and övning labels,
    - a node under the wrong parent type, by the nesting rules
      `get_outline_schema` gives,
    - a control character in any string part but `explanation`, which is what
      JSON makes of an unescaped LaTeX backslash such as `\\frac` or `\\times`,
    - a malformed stamp, meaning one `stamp_seconds` rejects once wrapped in
      brackets, such as `"1:75"`, or a stamp later than the Transcript's
      stored audio duration,
    - a Slide number below 1, a Slide number past the last Slide of the Deck
      attached to the Transcript, any Slide number when the Transcript has no
      Deck, and a Slide number listed twice on one node,
    - broken LaTeX, meaning a piece the page's KaTeX cannot draw inline. The
      pieces are each `$...$` in an explanation, a task, an answer or a step
      reason, and each step calculation as a whole. A `$` with no closing `$`
      is broken from that `$` to the end of the part, and `$$` is broken,
      since math is never display mode. `\\$` is a literal dollar sign and
      never opens or closes math. Labels are not checked.

    Each broken piece is one problem, whose message names the part, as
    `explanation`, `task`, `answer`, `step 2 calculation` or `step 2 reason`,
    then the piece exactly as the part holds it, dollars included, then
    KaTeX's own reason, unedited, with `at end of input` or `at position N`
    (N counted from 1) added when KaTeX knows where, such as `Unexpected end
    of input in a macro argument, expected '}' at end of input`.
    The LaTeX check accepts exactly what the page's KaTeX draws, because it
    runs the same KaTeX build the page embeds.

    A node of an unknown type is one problem, and nothing else about it is
    checked. A part of the wrong kind is one problem, and what it holds is
    not checked. A `children` part on an exempel or övning is one problem,
    whatever the list holds, and the nodes in it are not checked. Every other
    fault is a problem of its own, so a misspelled key gives one problem for
    the unknown key and one for the missing part. Stamps and Slide numbers
    are checked only on nodes whose parts have the right kind, and LaTeX
    only in parts that are strings. Any problem
    raises `OutlineStructureError` with all of them.

    An Outline that passes renders every node. Each stamp becomes a Timestamp
    link to the Transcript's Source, shown as `display_stamp` gives it, and
    each Slide number links that Slide to the node. A slide node with no
    Slide numbers is fine, and in a Transcript with no Deck it stands for a
    Slide-sized part of the lecture. Clicking a node shows, in its panel, its
    explanation, then its linked Slides in Slide order, each captioned and
    alt-texted `Slide N`, then the Source link. The page embeds each linked
    Slide's image once, as a base64 `data:image/png` URI, and no Slide that no
    node links.

    An explanation's math typesets inline with KaTeX, prose wraps like a
    paragraph, and long math breaks at `=` and `+`. An explanation with no
    `$` shows as plain text, line breaks kept. A piece the browser's KaTeX
    still cannot draw shows as written, dollars included, and the rest
    typesets. Labels show as plain text everywhere, LaTeX included.

    An exempel or övning panel labels its text `Exempel` or `Övning` in place
    of "A simple explanation", and shows a box where the explanation would
    be. The box's heading is `Exempel N` or `Övning N`, where N counts
    exempel and övning nodes separately in Outline order, from 1. Under it
    come the task, then a closed "Visa lösning" section with the step count
    beside it, holding the steps numbered from 1, each with its calculation
    as inline math and its reason under it, then a closed "Visa svar"
    section holding the answer. A task, reason or answer typesets as an
    explanation does. A box with no steps leaves out "Visa lösning", one with
    an empty answer leaves out "Visa svar", and one with neither shows the
    muted line "Ingen lösning i föreläsningen. Försök själv." Box text is set
    in KaTeX_Main, and the section toggles in the app's sans.

    Each topic gives its branch one colour. Exempel and övning nodes are
    orange because of their type, whatever their label says: an orange of hue
    25 to 45 degrees that no topic gets. An orange node's border, background,
    selected fill, stamps, and panel path and rule are orange. The edge into
    an exempel or övning keeps its topic's colour, and the edge into one
    directly under the main-topic is orange. An exempel or övning directly
    under the main-topic takes no topic colour, so the topics after it get the
    colours they would have had without it. A topic whose label starts with
    `Exempel:` is not orange. The page puts `Exempel: ` or `Övning: ` before
    an exempel's or övning's label on its map card, its card's aria-label,
    its panel title, and its button under Explore next.

    Term nodes whose labels match ignoring case and runs of whitespace are
    copies of one term. Clicking a copy of a term with two or more copies
    lists every copy in its panel, in Outline order, as `topic › slide` in its
    topic's colour, linked to the copy's first stamp. A copy with no stamp is
    listed without a link. Only nodes of type `term` count.

    The page is `<transcript_id>.html` in `output_dir`, replacing any earlier
    page for the same Transcript. CSS, JavaScript, KaTeX with its fonts,
    Outline data and Slide images are embedded, so it opens straight from
    disk and typesets its math without network access. Radial rings is the default layout; settings also offers Topic
    circles.

    `cache_dir` defaults to the per-user cache folder for Munin.
    `output_dir` defaults to `mindmaps/` at the repo root, found from this
    file's location, so the server's working directory does not matter.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID,
    before the Outline is read, then `OutlineSyntaxError` or
    `OutlineStructureError` as above. Any of them means nothing is written.
    """
    entry = cached_entry(transcript_id, cache_dir=cache_dir)
    deck = deck_path(transcript_id, cache_dir or default_cache_dir())
    return _write_page(transcript_id, outline, entry, deck, output_dir)


def render_deck_mindmap(
    deck_id: str,
    outline: dict | str,
    *,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
) -> RenderResult:
    """Check a JSON Outline written from a Deck read on its own, write its Mindmap page, and return what `render_mindmap` returns.

    Checks and renders as `render_mindmap` does, with these differences.
    Slide numbers resolve against the copy `read_deck` stored under
    `deck_id`, so a Slide number below 1 or past its last Slide is a problem.
    There is no Source, so any stamp on any node is a problem. The page has no
    link to a Source: no lecture link in its header and no Source link in any
    node's panel.

    The page is `<deck_id>.html` in `output_dir`, replacing any earlier page
    for the same Deck. `cache_dir` and `output_dir` default as for
    `render_mindmap`.

    Raises `UnknownDeckError` when no Deck read on its own has this ID, before
    the Outline is read, then `OutlineSyntaxError` or `OutlineStructureError`
    as `render_mindmap` does. Any of them means nothing is written.
    """
    cache_dir = cache_dir or default_cache_dir()
    deck = standalone_deck_path(deck_id, cache_dir)
    if not is_cache_id(deck_id) or not deck.is_file():
        raise UnknownDeckError(deck_id)
    return _write_page(deck_id, outline, None, deck, output_dir)


def _write_page(
    page_id: str, outline: dict | str, entry: CacheEntry | None, deck: Path, output_dir: Path | None
) -> RenderResult:
    """Check the Outline, then write `<page_id>.html`, linking stamps to the entry's Source and Slide numbers to the Deck at `deck`.

    `entry` is None when there is no Source, and `deck` need not exist.
    """
    parsed = _parsed(outline)
    deck_pages = pdf.page_count(deck) if deck.is_file() else None
    problems = check_outline(parsed, duration_s=entry.duration_s if entry else None, deck_pages=deck_pages)
    if problems:
        raise OutlineStructureError(problems)
    source = entry.source if entry else None
    nodes = _flat_nodes(parsed, source)
    linked = sorted({number for node in nodes for number in node["slides"]})
    content = _page_html(page_id, nodes, source, _slide_images(deck, linked))
    page = (output_dir or _DEFAULT_OUTPUT_DIR).resolve() / f"{page_id}.html"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(content, encoding="utf-8")
    return RenderResult(page)


def _parsed(outline: dict | str) -> object:
    """Return the Outline as parsed JSON, raising `OutlineSyntaxError` when text is not JSON."""
    if not isinstance(outline, str):
        return outline
    try:
        return json.loads(outline)
    except json.JSONDecodeError as error:
        raise OutlineSyntaxError(error.lineno, error.colno, error.msg) from error


def _flat_nodes(outline: dict, source: Source | None) -> list[dict]:
    """Return the checked Outline's nodes in Outline order, each pointing at its parent by index."""
    nodes: list[dict] = []
    counts = {"exempel": 0, "övning": 0}

    def add(node: dict, parent: int | None) -> None:
        index = len(nodes)
        links = []
        for stamp in node["stamps"]:
            offset = stamp_seconds(f"[{stamp}]")
            links.append({"text": display_stamp(offset), "url": _timestamp_url(source, offset)})
        worked = None
        if node["type"] in counts:
            counts[node["type"]] += 1
            worked = _worked_box(node, counts[node["type"]])
        nodes.append(
            {
                "id": index,
                "parent": parent,
                "type": node["type"],
                "label": node["label"],
                "links": links,
                "slides": sorted(node["slides"]),
                "term": " ".join(node["label"].split()).casefold(),
                "explanation": node.get("explanation", ""),
                "worked": worked,
            }
        )
        for child in node.get("children", []):
            add(child, index)

    add(outline, None)
    return nodes


def _worked_box(node: dict, number: int) -> dict:
    """Return what an exempel's or övning's box shows, `number` counting its type in Outline order."""
    title = node["type"].capitalize()
    return {
        "title": title,
        "heading": f"{title} {number}",
        "task": node["task"],
        "steps": node["steps"],
        "answer": node["answer"],
    }


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


def _page_html(page_id: str, nodes: list[dict], source: Source | None, slide_images: dict[str, str]) -> str:
    title = nodes[0]["label"] or "Mindmap"
    source_url = _source_url(source)
    source_link = (
        ""
        if source_url is None
        else f'<a class="source-link" href="{escape(source_url, quote=True)}" target="_blank" rel="noopener">Open Source ↗</a>'
    )
    replacements = {
        "__CSS__": (_ASSETS / "mindmap.css").read_text(encoding="utf-8"),
        "__JS__": (_ASSETS / "mindmap.js").read_text(encoding="utf-8"),
        "__KATEX_CSS__": katex_css(),
        "__KATEX_JS__": katex_js().replace("</script", "<\\/script"),
        "__DATA__": _script_safe_json(nodes),
        "__PAGE__": _script_safe_json(
            {
                "title": title,
                "source_url": source_url,
                "page_id": page_id,
                "slides": slide_images,
                "katex_options": KATEX_OPTIONS,
            }
        ),
        "__TITLE__": escape(title),
        "__SOURCE_LINK__": source_link,
    }
    template = (_ASSETS / "mindmap.html").read_text(encoding="utf-8")
    return re.sub(
        r"__(?:CSS|JS|KATEX_CSS|KATEX_JS|DATA|PAGE|TITLE|SOURCE_LINK)__",
        lambda match: replacements[match[0]],
        template,
    )


def _source_url(source: Source | None) -> str | None:
    """Return the address the page's Source links open, or None when there is no Source."""
    if source is None:
        return None
    return source.url if isinstance(source, Video) else source.as_uri()


def _script_safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False).replace("<", "\\u003c")
