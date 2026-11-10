import pytest

from munin.core.latex import math_html

KATEX_HTML = 'class="katex"'
DISPLAY_HTML = "katex-display"


def test_math_html_returns_katex_html():
    """`math_html` returns KaTeX's HTML for a piece of LaTeX."""
    assert KATEX_HTML in math_html("\\frac{1}{2}")


def test_math_html_is_inline():
    """`math_html` draws inline math, never display math."""
    assert DISPLAY_HTML not in math_html("\\frac{1}{2}")


def test_math_html_raises_on_latex_katex_cannot_draw():
    """`math_html` raises `ValueError` when KaTeX cannot draw the LaTeX."""
    with pytest.raises(ValueError):
        math_html("\\frac{1}{2")
