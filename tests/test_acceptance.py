"""Acceptance tests for #55: an English Transcript renders an English Mindmap."""

import asyncio
import json
import re
from pathlib import Path

import pytest
from mcp import Client
from playwright.sync_api import sync_playwright

from munin.core import (
    Fragment,
    OutlineStructureError,
    get_outline_schema,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
WORKED_TYPES = ["example", "exercise"]
ENGLISH_PREFIXES = [
    "Example: Rows",
    "EXAMPLE: Rows",
    "example : Rows",
    "  Example : Rows",
    "Exercise: Rows",
    "EXERCISE: Rows",
    "exercise : Rows",
]
SWEDISH_PREFIXES = ["Exempel: Rader", "Övning: Rader"]
SWEDISH_LETTERS = re.compile("[åäöÅÄÖ]")


def one_sentence(wav: Path, vocabulary):
    """A recognizer that ignores the audio and yields one sentence, in whatever language the run asked for."""
    return [Fragment(1.2, 3.0, "Today we talk about matrices.")]


def node(kind: str, label: str, *children: dict) -> dict:
    """A node of a type with children, with every part present."""
    return {"type": kind, "label": label, "explanation": "", "stamps": [], "slides": [], "children": list(children)}


def worked(kind: str = "example", label: str = "Row times column", *, steps=(("x = 2 - 1", "subtract 1"), ("x = 1", "")), answer: str = "$x = 1$") -> dict:
    """An example or exercise node with a task, steps given as (calculation, reason) pairs, and an answer."""
    return {
        "type": kind,
        "label": label,
        "stamps": [],
        "slides": [],
        "task": "Solve $x + 1 = 2$",
        "steps": [{"calculation": calculation, "reason": reason} for calculation, reason in steps],
        "answer": answer,
    }


def lecture(*under_slide: dict) -> dict:
    """The main topic Matrices, topic Rows, slide node Slide, and these nodes under it."""
    return node("main-topic", "Matrices", node("topic", "Rows", node("slide", "Slide", *under_slide)))


def transcript_in(language: str | None, source: Path, cache_dir: Path) -> str:
    """Transcribe the Source in this language, or with none, and return the Transcript ID."""
    return transcribe(source, language=language, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def problem_messages(transcript_id: str, outline: dict, cache_dir: Path, tmp_path: Path) -> list[str]:
    """Render an Outline that must fail the check, and return each problem's message."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    return [problem.message for problem in caught.value.problems]


def tool_description(name: str) -> str:
    """Return a tool's description with every run of whitespace collapsed to one space."""

    async def run():
        async with Client(create_server()) as client:
            return await client.list_tools()

    description = next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)
    return " ".join(description.split())


def lecture_prompt(**arguments: str) -> str:
    """Return the `lecture_to_mindmap` prompt's text with whitespace collapsed."""

    async def run():
        async with Client(create_server()) as client:
            return await client.get_prompt("lecture_to_mindmap", arguments)

    return " ".join(asyncio.run(run()).messages[0].content.text.split())


@pytest.fixture
def english_id(source: Path, cache_dir: Path) -> str:
    return transcript_in("en", source, cache_dir)


@pytest.fixture
def swedish_id(source: Path, cache_dir: Path) -> str:
    return transcript_in("sv", source, cache_dir)


@pytest.fixture
def legacy_id(source: Path, cache_dir: Path) -> str:
    """A Swedish Transcript whose cache entry is rewritten without its `language`, as before lecture languages existed."""
    transcript_id = transcript_in("sv", source, cache_dir)
    for entry in cache_dir.rglob("*.json"):
        stored = json.loads(entry.read_text(encoding="utf-8"))
        if isinstance(stored, dict) and "language" in stored:
            del stored["language"]
            entry.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    return transcript_id


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
def open_panel(page, cache_dir: Path, tmp_path: Path):
    """Render an Outline against a Transcript, show every node, and open the panel of the card whose label ends with `label`."""

    def open_(transcript_id: str, outline: dict, label: str = "Row times column") -> None:
        url = render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").page.as_uri()
        page.goto(f"{url}?depth=all")
        page.locator(".node-label").filter(has_text=re.compile(f"{re.escape(label)}$")).dispatch_event("click")

    return open_


def card_labels(page) -> list[str]:
    return page.locator(".node-label").all_text_contents()


def box(page):
    return page.locator("#panel #worked")


def summaries(page) -> list[str]:
    """Each toggle's summary text in the open box, whitespace collapsed."""
    return [" ".join(text.split()) for text in box(page).locator("summary").all_text_contents()]


def content_langs(page) -> set[str]:
    """The `lang` of every element under `<body>` that carries one."""
    return set(page.locator("body [lang]").evaluate_all("elements => elements.map(element => element.lang)"))


# 1. The LLM is asked for the whole Outline in the lecture's language


def test_schema_description_asks_for_the_lectures_language():
    """The schema's description asks for the Outline in the lecture's language."""
    assert "the lecture's language" in get_outline_schema().schema["description"]


def test_schema_description_names_no_swedish():
    """The schema's description no longer asks for Swedish."""
    assert "Swedish" not in get_outline_schema().schema["description"]


def test_schema_example_sample_is_swedish():
    """The example sample is written in Swedish, so its text holds a Swedish letter."""
    example, _ = get_outline_schema().samples
    assert SWEDISH_LETTERS.search(json.dumps(example, ensure_ascii=False))


def test_schema_exercise_sample_is_english():
    """The exercise sample is written in English, so its text holds no Swedish letter."""
    _, exercise = get_outline_schema().samples
    assert not SWEDISH_LETTERS.search(json.dumps(exercise, ensure_ascii=False))


def test_render_description_asks_for_the_lectures_language():
    """The `render_mindmap` tool description asks for the Outline in the lecture's language."""
    assert "the lecture's language" in tool_description("render_mindmap")


def test_render_description_names_no_swedish():
    """The `render_mindmap` tool description no longer asks for Swedish."""
    assert "Swedish" not in tool_description("render_mindmap")


@pytest.mark.parametrize("prefix", ["`Example:`", "`Exercise:`"])
def test_render_description_says_to_leave_out_english_prefixes(prefix: str):
    """The `render_mindmap` tool description names the English prefixes among those to leave out of labels."""
    assert prefix in tool_description("render_mindmap")


def test_deck_render_description_still_asks_for_swedish():
    """The `render_deck_mindmap` description keeps its Swedish reason, since a Deck's page stays Swedish (guard)."""
    assert "one short Swedish sentence" in tool_description("render_deck_mindmap")


@pytest.mark.parametrize("language", [None, "en", "sv"], ids=["no-language", "en", "sv"])
def test_lecture_prompt_asks_for_the_lectures_language(language: str | None):
    """The lecture prompt asks for the whole Outline in the lecture's language, whether or not a language was given."""
    arguments = {"source": WATCH_URL} | ({"language": language} if language else {})
    assert "the lecture's language" in lecture_prompt(**arguments)


def test_lecture_prompt_points_at_the_language_transcribe_returned():
    """The lecture prompt tells the LLM the lecture's language is the `language` `transcribe` returned."""
    assert "`language` `transcribe` returned" in lecture_prompt(source=WATCH_URL)


# 3. The render reads the language from the Transcript and bans that language's prefixes


@pytest.mark.parametrize("label", ENGLISH_PREFIXES)
def test_english_prefix_fails_an_english_render(label: str, english_id: str, cache_dir: Path, tmp_path: Path):
    """On an English Transcript, a label starting with `Example:` or `Exercise:`, in any case, fails the render."""
    assert problem_messages(english_id, lecture(node("term", label)), cache_dir, tmp_path)


@pytest.mark.parametrize("label, prefix", [("example : Rows", "Example:"), ("EXERCISE: Rows", "Exercise:")])
def test_english_prefix_problem_names_the_prefix(label: str, prefix: str, english_id: str, cache_dir: Path, tmp_path: Path):
    """The problem for a banned English prefix names it capitalized."""
    [message] = problem_messages(english_id, lecture(node("term", label)), cache_dir, tmp_path)
    assert f'"{prefix}"' in message


@pytest.mark.parametrize("label", SWEDISH_PREFIXES)
def test_swedish_prefix_passes_an_english_render(label: str, english_id: str, cache_dir: Path, tmp_path: Path):
    """On an English Transcript, a label starting with `Exempel:` or `Övning:` renders."""
    assert render_mindmap(english_id, lecture(node("term", label)), cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


@pytest.mark.parametrize("label", SWEDISH_PREFIXES)
def test_swedish_prefix_still_fails_a_swedish_render(label: str, swedish_id: str, cache_dir: Path, tmp_path: Path):
    """On a Swedish Transcript, a label starting with `Exempel:` or `Övning:` still fails the render (guard)."""
    assert problem_messages(swedish_id, lecture(node("term", label)), cache_dir, tmp_path)


@pytest.mark.parametrize("label", ["Example: Rows", "Exercise: Rows"])
def test_english_prefix_still_passes_a_swedish_render(label: str, swedish_id: str, cache_dir: Path, tmp_path: Path):
    """On a Swedish Transcript, a label starting with `Example:` or `Exercise:` still renders (guard)."""
    assert render_mindmap(swedish_id, lecture(node("term", label)), cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


# 4. English label prefixes and box headings


@pytest.mark.parametrize("kind, prefix", [("example", "Example: "), ("exercise", "Exercise: ")])
def test_english_card_shows_english_prefix(kind: str, prefix: str, page, open_panel, english_id: str):
    """On an English page, an example's or exercise's map card starts with `Example: ` or `Exercise: `."""
    open_panel(english_id, lecture(worked(kind)))
    assert f"{prefix}Row times column" in card_labels(page)


@pytest.mark.parametrize("kind, prefix", [("example", "Example: "), ("exercise", "Exercise: ")])
def test_english_panel_title_shows_english_prefix(kind: str, prefix: str, page, open_panel, english_id: str):
    """On an English page, an example's or exercise's panel title starts with `Example: ` or `Exercise: `."""
    open_panel(english_id, lecture(worked(kind)))
    assert page.locator("#panel-title").text_content() == f"{prefix}Row times column"


@pytest.mark.parametrize("kind, heading", [("example", "Example 2"), ("exercise", "Exercise 2")])
def test_english_box_heading_counts_its_type(kind: str, heading: str, page, open_panel, english_id: str):
    """On an English page, the second example's box is headed `Example 2`, and the second exercise's `Exercise 2`."""
    open_panel(english_id, lecture(worked(kind, "First"), worked(kind)))
    assert box(page).locator("h3").text_content() == heading


@pytest.mark.parametrize("kind, label", [("example", "Example"), ("exercise", "Exercise")])
def test_english_panel_label_names_the_type(kind: str, label: str, page, open_panel, english_id: str):
    """On an English page, the label above an example's or exercise's box reads `Example` or `Exercise`."""
    open_panel(english_id, lecture(worked(kind)))
    assert page.locator(".explanation-label").text_content() == label


# 5. English toggles and step count


def test_english_box_shows_show_solution_with_step_count(page, open_panel, english_id: str):
    """On an English page, a box with two steps shows the toggle `Show solution` with `2 steps` beside it."""
    open_panel(english_id, lecture(worked()))
    assert "Show solution 2 steps" in summaries(page)


def test_english_box_with_one_step_says_one_step(page, open_panel, english_id: str):
    """On an English page, a box with one step shows `1 step`, not `1 steps`."""
    open_panel(english_id, lecture(worked(steps=(("x = 1", "subtract 1"),))))
    assert "Show solution 1 step" in summaries(page)


def test_english_box_shows_show_answer(page, open_panel, english_id: str):
    """On an English page, a box with an answer shows the toggle `Show answer`."""
    open_panel(english_id, lecture(worked()))
    assert "Show answer" in summaries(page)


def test_english_box_with_no_solution_says_so_in_english(page, open_panel, english_id: str):
    """On an English page, a box with no steps and no answer shows `No solution in the lecture. Try it yourself.`"""
    open_panel(english_id, lecture(worked(steps=(), answer="")))
    assert box(page).locator(".no-solution").text_content() == "No solution in the lecture. Try it yourself."


# 6. The lecture content's lang


def test_english_page_marks_its_lecture_content_english(page, open_panel, english_id: str):
    """On an English page, every element under the body that carries a `lang` carries `en`."""
    open_panel(english_id, lecture(worked(), node("term", "Row")))
    assert content_langs(page) == {"en"}


# A Swedish Transcript renders as it does today


def test_swedish_page_marks_its_lecture_content_swedish(page, open_panel, swedish_id: str):
    """On a Swedish page, every element under the body that carries a `lang` carries `sv` (guard)."""
    open_panel(swedish_id, lecture(worked(), node("term", "Row")))
    assert content_langs(page) == {"sv"}


@pytest.mark.parametrize(
    "expected",
    ["Visa lösning 2 steg", "Visa svar"],
)
def test_swedish_box_keeps_swedish_toggles(expected: str, page, open_panel, swedish_id: str):
    """On a Swedish page, the box's toggles read `Visa lösning` with `N steg`, and `Visa svar` (guard)."""
    open_panel(swedish_id, lecture(worked()))
    assert expected in summaries(page)


@pytest.mark.parametrize("kind, prefix", [("example", "Exempel: "), ("exercise", "Övning: ")])
def test_swedish_card_keeps_swedish_prefix(kind: str, prefix: str, page, open_panel, swedish_id: str):
    """On a Swedish page, an example's or exercise's map card starts with `Exempel: ` or `Övning: ` (guard)."""
    open_panel(swedish_id, lecture(worked(kind)))
    assert f"{prefix}Row times column" in card_labels(page)


# A Transcript cached before the language existed renders as Swedish


def test_legacy_transcript_renders_swedish_prefix(page, open_panel, legacy_id: str):
    """A Transcript cached with no language renders its example as `Exempel: ` (guard)."""
    open_panel(legacy_id, lecture(worked()))
    assert "Exempel: Row times column" in card_labels(page)


def test_legacy_transcript_bans_swedish_prefix(legacy_id: str, cache_dir: Path, tmp_path: Path):
    """A Transcript cached with no language still fails a label starting with `Exempel:` (guard)."""
    assert problem_messages(legacy_id, lecture(node("term", "Exempel: Rader")), cache_dir, tmp_path)


# The fixed page text stays English in both languages


@pytest.mark.parametrize("selector, text", [(".panel-top .eyebrow", "SELECTED IDEA"), (".related h3", "Explore next")])
@pytest.mark.parametrize("language", ["en", "sv"])
def test_fixed_page_text_stays_english(
    selector: str, text: str, language: str, page, open_panel, source: Path, cache_dir: Path
):
    """`SELECTED IDEA` and `Explore next` read the same on an English page and a Swedish one (guard on sv)."""
    open_panel(transcript_in(language, source, cache_dir), lecture(worked()))
    assert page.locator(selector).text_content() == text
