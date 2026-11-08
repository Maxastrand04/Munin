"""Acceptance tests for #56: a standalone Deck renders an English Mindmap when asked."""

import asyncio
import re
from pathlib import Path

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError
from playwright.sync_api import sync_playwright

from munin.core import (
    Fragment,
    LanguageError,
    OutlineStructureError,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
DECK_PATH = "/tmp/matrices.pdf"


def node(kind: str, label: str, *children: dict) -> dict:
    """A node of a type with children, with every part present."""
    return {"type": kind, "label": label, "explanation": "", "stamps": [], "slides": [], "children": list(children)}


def solved(kind: str = "example", label: str = "Row times column", *, steps=(("x = 2 - 1", "subtract 1"), ("x = 1", ""))) -> dict:
    """An example or exercise with a task, steps given as (calculation, reason) pairs, and an answer."""
    return {
        "type": kind,
        "label": label,
        "stamps": [],
        "slides": [],
        "task": "Solve $x + 1 = 2$",
        "steps": [{"calculation": calculation, "reason": reason} for calculation, reason in steps],
        "answer": "$x = 1$",
    }


def under_a_slide(*children: dict) -> dict:
    """The main topic Matrices, topic Rows, slide node Slide 1, and these nodes under it."""
    return node("main-topic", "Matrices", node("topic", "Rows", node("slide", "Slide 1", *children)))


def english_sentence(wav: Path, vocabulary):
    """A recognizer that ignores the audio and yields one English sentence."""
    return [Fragment(1.2, 3.0, "Today we talk about matrices.")]


@pytest.fixture
def deck_id(deck: Path, cache_dir: Path) -> str:
    """The ID of the three-page Deck read on its own."""
    return read_deck(deck, cache_dir=cache_dir).deck_id


def render_deck(deck_id: str, outline: dict, cache_dir: Path, output_dir: Path, **kwargs) -> Path:
    """Render an Outline against a standalone Deck and return the page's path."""
    return render_deck_mindmap(deck_id, outline, cache_dir=cache_dir, output_dir=output_dir, **kwargs).page


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def tool_description(server, name: str) -> str:
    """Return a tool's description with every run of whitespace collapsed to one space."""

    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    description = next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)
    return " ".join(description.split())


def get_prompt(server, name: str, arguments: dict) -> str:
    """Return a prompt's text with every run of whitespace inside a line collapsed to one space."""

    async def run():
        async with Client(server) as client:
            return await client.get_prompt(name, arguments)

    text = asyncio.run(run()).messages[0].content.text
    return "\n".join(" ".join(line.split()) for line in text.splitlines())


def prompt_error(server, name: str, arguments: dict) -> MCPError | None:
    """Return the MCP error that getting the prompt raises, or None when it succeeds."""

    async def run():
        async with Client(server) as client:
            try:
                await client.get_prompt(name, arguments)
            except MCPError as error:
                return error
            return None

    return asyncio.run(run())


def step_naming(text: str, phrase: str) -> str:
    """Return the one prompt line that holds `phrase`."""
    [line] = [line for line in text.splitlines() if phrase in line]
    return line


# Rendering a standalone Deck in a language


@pytest.mark.parametrize("label", ["Example: Rows", "exercise : Rows"])
def test_english_deck_render_bans_the_english_prefix(deck_id: str, cache_dir: Path, tmp_path: Path, label: str):
    """A standalone Deck rendered with `en` fails on a label starting with `Example:` or `Exercise:`, in any case."""
    with pytest.raises(OutlineStructureError):
        render_deck(deck_id, under_a_slide(node("term", label)), cache_dir, tmp_path, language="en")


@pytest.mark.parametrize("label", ["Exempel: Rader", "Övning: Rader"])
def test_english_deck_render_lets_the_swedish_prefix_pass(deck_id: str, cache_dir: Path, tmp_path: Path, label: str):
    """A standalone Deck rendered with `en` bans only the English prefixes, so a label starting with `Exempel:` renders."""
    assert render_deck(deck_id, under_a_slide(node("term", label)), cache_dir, tmp_path, language="en").is_file()


def test_deck_render_with_no_language_still_bans_the_swedish_prefix(deck_id: str, cache_dir: Path, tmp_path: Path):
    """A standalone Deck rendered with no language is Swedish, so a label starting with `Exempel:` fails, as before."""
    with pytest.raises(OutlineStructureError):
        render_deck(deck_id, under_a_slide(node("term", "Exempel: Rader")), cache_dir, tmp_path)


@pytest.mark.parametrize("language", ["de", "EN", ""])
def test_deck_render_rejects_a_language_other_than_sv_or_en(
    deck_id: str, cache_dir: Path, tmp_path: Path, language: str
):
    """A language other than exactly `sv` or `en` raises `LanguageError` naming it."""
    with pytest.raises(LanguageError, match=f"^Language {language} is not sv or en$"):
        render_deck(deck_id, under_a_slide(), cache_dir, tmp_path, language=language)


def test_deck_render_with_a_bad_language_writes_nothing(deck_id: str, cache_dir: Path, tmp_path: Path):
    """A render with a bad language writes no page."""
    output_dir = tmp_path / "out"
    with pytest.raises(LanguageError):
        render_deck(deck_id, under_a_slide(), cache_dir, output_dir, language="de")
    assert not output_dir.exists()


def test_deck_render_checks_the_language_before_the_deck_id(cache_dir: Path, tmp_path: Path):
    """A bad language raises `LanguageError` even when the Deck ID is unknown and the Outline is not JSON."""
    with pytest.raises(LanguageError):
        render_deck_mindmap("deadbeef0000", "# Matrices\n", language="de", cache_dir=cache_dir, output_dir=tmp_path)


# A Deck attached to a Transcript keeps the Transcript's language


def test_english_transcript_with_a_deck_bans_the_english_prefix(
    source: Path, deck: Path, cache_dir: Path, tmp_path: Path
):
    """An English Transcript with an attached Deck renders English, so a label starting with `Example:` fails."""
    transcript_id = transcribe(source, language="en", cache_dir=cache_dir, recognize=english_sentence).transcript_id
    read_slides(transcript_id, deck, cache_dir=cache_dir)
    with pytest.raises(OutlineStructureError):
        render_mindmap(transcript_id, under_a_slide(node("term", "Example: Rows")), cache_dir=cache_dir, output_dir=tmp_path)


# The deck render tool


def test_mcp_deck_render_passes_the_language_to_the_core(deck: Path, cache_dir: Path, tmp_path: Path):
    """The deck render tool given `en` renders English, so a label starting with `Example:` is a tool error."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path)
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    outline = under_a_slide(node("term", "Example: Rows"))
    assert call(server, "render_deck_mindmap", {"deck_id": deck_id, "outline": outline, "language": "en"}).is_error


def test_mcp_deck_render_description_asks_for_the_decks_language(cache_dir: Path):
    """The deck render tool's description asks for the whole Outline in the Deck's language."""
    assert "in the Deck's language" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_asks_for_no_swedish_reason(cache_dir: Path):
    """The deck render tool's description no longer asks for a Swedish step reason."""
    assert "Swedish sentence" not in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


@pytest.mark.parametrize("prefix", ["`Example:`", "`Exercise:`"])
def test_mcp_deck_render_description_says_to_leave_out_english_prefixes(cache_dir: Path, prefix: str):
    """The deck render tool's description names the English prefixes among those to leave out of labels."""
    assert prefix in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_asks_to_pass_the_decks_language(cache_dir: Path):
    """The deck render tool's description asks for the Deck's language as `language`, `sv` or `en`."""
    assert "as `language`, `sv` or `en`" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


# The slides-only prompts


@pytest.mark.parametrize("language", ["sv", "en"])
def test_slides_prompt_renders_with_the_given_language(cache_dir: Path, language: str):
    """With a language, the render step passes it to `render_deck_mindmap`."""
    text = get_prompt(create_server(cache_dir=cache_dir), "slides_to_mindmap", {"deck": DECK_PATH, "language": language})
    assert f"Call `render_deck_mindmap` with the Deck ID, the Outline and language `{language}`." in text


def test_slides_prompt_writes_the_outline_in_the_given_language(cache_dir: Path):
    """With a language, the writing step names that language for the Outline."""
    text = get_prompt(create_server(cache_dir=cache_dir), "slides_to_mindmap", {"deck": DECK_PATH, "language": "en"})
    assert "`en`" in step_naming(text, "Write an Outline")


def test_slides_prompt_without_a_language_writes_in_the_decks_language(cache_dir: Path):
    """With no language, the writing step asks for the whole Outline in the Deck's language."""
    text = get_prompt(create_server(cache_dir=cache_dir), "slides_to_mindmap", {"deck": DECK_PATH})
    assert "the Deck's language" in step_naming(text, "Write an Outline")


def test_slides_prompt_without_a_language_renders_with_the_decks_language(cache_dir: Path):
    """With no language, the render step passes the Deck's language as `language`."""
    text = get_prompt(create_server(cache_dir=cache_dir), "slides_to_mindmap", {"deck": DECK_PATH})
    assert "`language`" in step_naming(text, "Call `render_deck_mindmap`")


def test_slides_prompt_with_an_empty_language_matches_no_language(cache_dir: Path):
    """An empty language counts as none, so the text is the same as with no language."""
    server = create_server(cache_dir=cache_dir)
    with_empty = get_prompt(server, "slides_to_mindmap", {"deck": DECK_PATH, "language": ""})
    assert with_empty == get_prompt(server, "slides_to_mindmap", {"deck": DECK_PATH})


def test_slides_prompt_rejects_a_bad_language(cache_dir: Path):
    """A language other than `sv` or `en` fails with an MCP error carrying the `LanguageError` message."""
    error = prompt_error(create_server(cache_dir=cache_dir), "slides_to_mindmap", {"deck": DECK_PATH, "language": "de"})
    assert "Language de is not sv or en" in str(error)


def test_lecture_prompt_with_only_a_deck_and_a_language_matches_the_slides_prompt(cache_dir: Path):
    """`lecture_to_mindmap` with only a Deck and `en` gives the same text as `slides_to_mindmap` with them."""
    server = create_server(cache_dir=cache_dir)
    arguments = {"deck": DECK_PATH, "language": "en"}
    assert get_prompt(server, "lecture_to_mindmap", arguments) == get_prompt(server, "slides_to_mindmap", arguments)


def test_lecture_prompt_with_a_source_and_deck_renders_with_no_language(cache_dir: Path):
    """With a Source, a Deck and `en`, the `render_mindmap` step passes no language, since the Transcript's applies."""
    arguments = {"source": WATCH_URL, "deck": DECK_PATH, "language": "en"}
    text = get_prompt(create_server(cache_dir=cache_dir), "lecture_to_mindmap", arguments)
    assert "Call `render_mindmap` with the Transcript ID and the Outline." in text


# The English Deck page in a browser


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    yield page
    page.close()


@pytest.fixture
def english_deck_url(deck_id: str, cache_dir: Path, tmp_path: Path):
    """Return a function rendering an Outline against the standalone Deck with `en`, returning the page's URL."""

    def render(outline: dict) -> str:
        return render_deck(deck_id, outline, cache_dir, tmp_path / "out", language="en").as_uri()

    return render


def show_every_node(page, url: str) -> None:
    page.goto(f"{url}?depth=all")


def card_labels(page) -> list[str]:
    return page.locator(".node-label").all_text_contents()


def open_card_panel(page, url: str, label: str) -> None:
    """Open the page with every node shown, then the panel of the node whose card label ends with `label`."""
    show_every_node(page, url)
    page.locator(".node-label").filter(has_text=re.compile(f"{re.escape(label)}$")).dispatch_event("click")


def toggle_summaries(page) -> list[str]:
    """Each toggle's summary text in the open box, whitespace collapsed."""
    return [" ".join(text.split()) for text in page.locator("#panel #worked summary").all_text_contents()]


@pytest.mark.parametrize("kind, prefix", [("example", "Example: "), ("exercise", "Exercise: ")])
def test_english_deck_card_shows_the_english_prefix(page, english_deck_url, kind: str, prefix: str):
    """On a Deck page rendered with `en`, the map card shows `Example: ` or `Exercise: ` before the label."""
    show_every_node(page, english_deck_url(under_a_slide(solved(kind))))
    assert f"{prefix}Row times column" in card_labels(page)


@pytest.mark.parametrize("kind, heading", [("example", "Example 1"), ("exercise", "Exercise 1")])
def test_english_deck_box_heading_names_its_type(page, english_deck_url, kind: str, heading: str):
    """On a Deck page rendered with `en`, the box is headed `Example 1` or `Exercise 1`."""
    open_card_panel(page, english_deck_url(under_a_slide(solved(kind))), "Row times column")
    assert page.locator("#panel #worked").get_by_role("heading").text_content() == heading


@pytest.mark.parametrize("expected", ["Show solution 2 steps", "Show answer"])
def test_english_deck_box_shows_english_toggles(page, english_deck_url, expected: str):
    """On a Deck page rendered with `en`, the box's toggles read `Show solution` with `N steps`, and `Show answer`."""
    open_card_panel(page, english_deck_url(under_a_slide(solved())), "Row times column")
    assert expected in toggle_summaries(page)


def test_english_deck_page_marks_its_content_english(page, english_deck_url):
    """On a Deck page rendered with `en`, every element under the body that carries a `lang` carries `en`."""
    open_card_panel(page, english_deck_url(under_a_slide(solved(), node("term", "Row"))), "Row times column")
    langs = page.locator("body [lang]").evaluate_all("elements => elements.map(element => element.lang)")
    assert set(langs) == {"en"}
