"""The one module that wraps `mini-racer`: it runs the page's own KaTeX in V8 (ADR-0021, PCR-0004)."""

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from py_mini_racer import MiniRacer

_KATEX = Path(__file__).parent / "_vendor" / "katex"
_OPTIONS = "{throwOnError: true, displayMode: false, strict: 'ignore'}"
_CHECK = (
    "function check(expression) {"
    f" try {{ katex.renderToString(expression, {_OPTIONS}); return null; }}"
    " catch (error) {"
    " var reason = error.rawMessage || String(error.message);"
    " if (error.position === undefined) return reason;"
    " return reason + (error.position >= expression.length ? ' at end of input' : ' at position ' + (error.position + 1)); } }"
)
_FONT_URLS = re.compile(r'url\(fonts/([^)]+?)\.woff2\) format\("woff2"\)(?:,url\([^)]*\) format\("[^"]*"\))*')


@dataclass(frozen=True)
class BrokenLatex:
    """One piece of prose or one calculation that KaTeX cannot draw."""

    piece: str
    reason: str


def katex_js() -> str:
    """Return the vendored KaTeX script, as the page embeds it."""
    return (_KATEX / "katex.min.js").read_text(encoding="utf-8")


def katex_css() -> str:
    """Return the vendored KaTeX stylesheet with every font embedded as a base64 woff2 data URI, so it needs no network."""
    import base64

    def embed(match: re.Match) -> str:
        data = base64.b64encode((_KATEX / "fonts" / f"{match[1]}.woff2").read_bytes()).decode()
        return f'url(data:font/woff2;base64,{data}) format("woff2")'

    return _FONT_URLS.sub(embed, (_KATEX / "katex.min.css").read_text(encoding="utf-8"))


def calculation_problems(calculation: str) -> list[BrokenLatex]:
    """Return the calculation as one broken piece when KaTeX cannot draw it whole, else nothing."""
    reason = _reason(calculation)
    return [] if reason is None else [BrokenLatex(calculation, reason)]


def prose_problems(prose: str) -> list[BrokenLatex]:
    """Return every broken `$...$` piece of prose in order.

    A backslash escapes the next character, so `\\$` never opens or closes
    math. A `$` with no closing `$` is broken from there to the end, and `$$`
    is broken since math is never display mode.
    """
    found: list[BrokenLatex] = []
    index = 0
    while index < len(prose):
        char = prose[index]
        if char == "\\":
            index += 2
        elif char != "$":
            index += 1
        elif prose.startswith("$$", index):
            found.append(BrokenLatex("$$", "$$ is display math, and math is always inline"))
            index += 2
        else:
            end = _closing_dollar(prose, index + 1)
            if end is None:
                piece, index = prose[index:], len(prose)
                reason = _reason(piece[1:]) or "no closing $"
            else:
                piece, index = prose[index : end + 1], end + 1
                reason = _reason(piece[1:-1])
            if reason is not None:
                found.append(BrokenLatex(piece, reason))
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
    engine = MiniRacer()
    engine.eval(katex_js())
    engine.eval(_CHECK)
    return engine
