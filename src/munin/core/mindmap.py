"""Rendering a JSON Outline into a Mindmap page with Timestamp links."""

import base64
import json
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path

from munin.core import pdf
from munin.core.sources import Source, Video

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
    - a node under the wrong parent type, by the nesting rules
      `get_outline_schema` gives,
    - a control character in any string part but `explanation`, which is what
      JSON makes of an unescaped LaTeX backslash such as `\\frac` or `\\times`,
    - a malformed stamp, meaning one `stamp_seconds` rejects once wrapped in
      brackets, such as `"1:75"`, or a stamp later than the Transcript's
      stored audio duration,
    - a Slide number below 1, a Slide number past the last Slide of the Deck
      attached to the Transcript, any Slide number when the Transcript has no
      Deck, and a Slide number listed twice on one node.

    A node of an unknown type is one problem, and nothing else about it is
    checked. A part of the wrong kind is one problem, and what it holds is
    not checked. A `children` part on an exempel or övning is one problem,
    whatever the list holds, and the nodes in it are not checked. Every other
    fault is a problem of its own, so a misspelled key gives one problem for
    the unknown key and one for the missing part. Stamps and Slide numbers
    are checked only on nodes whose parts have the right kind. Any problem
    raises `OutlineStructureError` with all of them.

    An Outline that passes renders every node. Each stamp becomes a Timestamp
    link to the Transcript's Source, shown as `display_stamp` gives it, and
    each Slide number links that Slide to the node. A slide node with no
    Slide numbers is fine, and in a Transcript with no Deck it stands for a
    Slide-sized part of the lecture. Clicking a node shows, in its panel, its
    explanation, then its linked Slides in Slide order, each captioned and
    alt-texted `Slide N`, then the Source link. The page embeds each linked
    Slide's image once, as a base64 `data:image/png` URI, and no Slide that no
    node links. An exempel or övning panel shows, where an explanation would
    be, one line each: the task, then `Steg N: <calculation>` per step,
    counted from 1, with ` (<reason>)` after it when the reason is not empty,
    then `Svar: <answer>` when the answer is not empty. LaTeX shows as
    written. Labels, explanations and every other text show as plain text.

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
    page for the same Transcript. CSS, JavaScript, Outline data and Slide
    images are embedded, so it opens straight from disk without network
    access. Radial rings is the default layout; settings also offers Topic
    circles.

    `cache_dir` defaults to the per-user cache folder for Munin.
    `output_dir` defaults to `mindmaps/` at the repo root, found from this
    file's location, so the server's working directory does not matter.

    Raises `UnknownTranscriptError` when no cached Transcript has this ID,
    before the Outline is read, then `OutlineSyntaxError` or
    `OutlineStructureError` as above. Any of them means nothing is written.
    """
    raise NotImplementedError


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
    raise NotImplementedError


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
        "__DATA__": _script_safe_json(nodes),
        "__PAGE__": _script_safe_json(
            {"title": title, "source_url": source_url, "page_id": page_id, "slides": slide_images}
        ),
        "__TITLE__": escape(title),
        "__SOURCE_LINK__": source_link,
    }
    template = (_ASSETS / "mindmap.html").read_text(encoding="utf-8")
    return re.sub(
        r"__(?:CSS|JS|DATA|PAGE|TITLE|SOURCE_LINK)__",
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
