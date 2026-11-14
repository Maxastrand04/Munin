"""The one module that wraps `mini-racer`: it runs the page's own KaTeX in V8 (ADR-0021, PCR-0004)."""

import base64
import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from py_mini_racer import MiniRacer

_KATEX = Path(__file__).parent / "_vendor" / "katex"
KATEX_OPTIONS = {"throwOnError": True, "displayMode": False, "strict": "ignore"}
"""The options both the LaTeX check and the page pass to KaTeX."""
_CHECK = (
    "function check(expression) {"
    f" try {{ katex.renderToString(expression, {json.dumps(KATEX_OPTIONS)}); return null; }}"
    " catch (error) {"
    " var reason = error.rawMessage || String(error.message);"
    " if (error.position === undefined) return reason;"
    " return reason + (error.position >= expression.length ? ' at end of input' : ' at position ' + (error.position + 1)); } }"
)
_FONT_URLS = re.compile(r'url\(fonts/([^)]+?)\.woff2\) format\("woff2"\)(?:,url\([^)]*\) format\("[^"]*"\))*')


@dataclass(frozen=True)
class BrokenLatex:
    """One piece of prose or one calculation that KaTeX cannot draw.

    `piece` is the broken text exactly as the part holds it, dollars included
    for prose. `reason` says why KaTeX cannot draw it.
    """

    piece: str
    reason: str


def katex_js() -> str:
    """Return the vendored KaTeX script, as the page embeds it."""
    return (_KATEX / "katex.min.js").read_text(encoding="utf-8")


def katex_css() -> str:
    """Return the vendored KaTeX stylesheet with every font embedded as a base64 woff2 data URI, so it needs no network."""

    def embed(match: re.Match) -> str:
        data = base64.b64encode((_KATEX / "fonts" / f"{match[1]}.woff2").read_bytes()).decode()
        return f'url(data:font/woff2;base64,{data}) format("woff2")'

    return _FONT_URLS.sub(embed, (_KATEX / "katex.min.css").read_text(encoding="utf-8"))


def calculation_problems(calculation: str) -> list[BrokenLatex]:
    """Return the calculation as one broken piece when KaTeX cannot draw it whole, else nothing."""
    reason = _reason(calculation)
    return [] if reason is None else [BrokenLatex(calculation, reason)]


@dataclass(frozen=True)
class ProsePiece:
    """One stretch of prose, cut by `prose_pieces`.

    `kind` is `"text"` for plain text, `"math"` for a closed `$...$` piece,
    `"display"` for a `$$`, and `"open"` for a `$` with no closing `$`.
    `text` is the stretch exactly as written, `$` and backslashes included.
    """

    kind: Literal["text", "math", "display", "open"]
    text: str


def prose_pieces(prose: str) -> list[ProsePiece]:
    """Cut prose into pieces in order, so that joining every `text` gives `prose` back.

    A backslash escapes the next character, so `\\$` never opens or closes
    math and stays in the text. A `$` with no closing `$` is one open piece
    from there to the end, and `$$` is one display piece. This is the one
    place that decides where math starts and ends.
    """
    pieces: list[ProsePiece] = []
    text_start = 0
    index = 0
    while index < len(prose):
        char = prose[index]
        if char == "\\":
            index += 2
        elif char != "$":
            index += 1
        else:
            if prose.startswith("$$", index):
                kind, end = "display", index + 2
            elif (closing := _closing_dollar(prose, index + 1)) is None:
                kind, end = "open", len(prose)
            else:
                kind, end = "math", closing + 1
            if index > text_start:
                pieces.append(ProsePiece("text", prose[text_start:index]))
            pieces.append(ProsePiece(kind, prose[index:end]))
            text_start = index = end
    if text_start < len(prose):
        pieces.append(ProsePiece("text", prose[text_start:]))
    return pieces


def prose_problems(prose: str) -> list[BrokenLatex]:
    """Return every broken `$...$` piece of prose in order.

    `$$` is broken since math is never display mode, and a `$` with no
    closing `$` is broken from there to the end.
    """
    found: list[BrokenLatex] = []
    for piece in prose_pieces(prose):
        if piece.kind == "display":
            found.append(BrokenLatex("$$", "$$ is display math, and math is always inline"))
        elif piece.kind == "open":
            found.append(BrokenLatex(piece.text, _reason(piece.text[1:]) or "no closing $"))
        elif piece.kind == "math":
            reason = _reason(piece.text[1:-1])
            if reason is not None:
                found.append(BrokenLatex(piece.text, reason))
    return found


def _closing_dollar(prose: str, start: int) -> int | None:
    index = start
    while index < len(prose):
        if prose[index] == "\\":
            index += 2
        elif prose[index] == "$":
            return index
        else:
            index += 1
    return None


def _reason(expression: str) -> str | None:
    return _engine().call("check", expression)


@lru_cache(maxsize=1)
def _engine() -> MiniRacer:
    """Return the one V8 engine with KaTeX and the check loaded, built on first use.

    It is built on a thread with no event loop, so it runs on a loop of its
    own and outlives any loop running where it was first asked for.
    """
    with ThreadPoolExecutor(max_workers=1) as builder:
        engine = builder.submit(MiniRacer).result()
    engine.eval(katex_js())
    engine.eval(_CHECK)
    return engine
