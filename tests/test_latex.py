import pytest

from munin.core.latex import ProsePiece, math_html, prose_pieces

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


def test_prose_pieces_cut_text_and_closed_math_in_order():
    """Prose is cut into text and closed `$...$` pieces in the order written, `$` kept on the math."""
    assert prose_pieces("Se $x$ och $y$.") == [
        ProsePiece("text", "Se "),
        ProsePiece("math", "$x$"),
        ProsePiece("text", " och "),
        ProsePiece("math", "$y$"),
        ProsePiece("text", "."),
    ]


def test_prose_pieces_keep_an_escaped_dollar_in_the_text():
    """A backslash escapes the next character, so `\\$` stays in the text and never opens math."""
    assert prose_pieces("Kostar \\$5 och $x$") == [
        ProsePiece("text", "Kostar \\$5 och "),
        ProsePiece("math", "$x$"),
    ]


def test_prose_pieces_keep_an_escaped_dollar_inside_math():
    """An escaped dollar inside a piece does not close it."""
    assert prose_pieces("$a \\$ b$") == [ProsePiece("math", "$a \\$ b$")]


def test_prose_pieces_mark_double_dollar_as_display():
    """`$$` is one display piece, whatever follows it."""
    assert prose_pieces("a $$x$$") == [
        ProsePiece("text", "a "),
        ProsePiece("display", "$$"),
        ProsePiece("text", "x"),
        ProsePiece("display", "$$"),
    ]


def test_prose_pieces_mark_a_dollar_with_no_closing_dollar_as_open_to_the_end():
    """A `$` with no closing `$` is one open piece from there to the end."""
    assert prose_pieces("a $x + y") == [
        ProsePiece("text", "a "),
        ProsePiece("open", "$x + y"),
    ]


def test_prose_pieces_join_back_into_the_prose():
    """Joining every piece's text gives the prose back, including a trailing backslash."""
    prose = "a \\$ $x$ $$ b \\"
    assert "".join(piece.text for piece in prose_pieces(prose)) == prose


def test_prose_pieces_of_empty_prose_are_none():
    """Empty prose has no pieces."""
    assert prose_pieces("") == []
