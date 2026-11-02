"""Acceptance tests for #43: typeset LaTeX in panels, box exempel and övning, and fail the render on broken LaTeX."""

import asyncio
import re
import wave
from pathlib import Path

import pytest
from mcp import Client
from playwright.sync_api import sync_playwright

from munin.core import (
    Fragment,
    OutlineStructureError,
    Vocabulary,
    get_outline_schema,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

TEN_MINUTES_S = 600
SAMPLE_RATE = 8_000
SLIDE_PATH = ("Matriser", "Rader", "Slide 1")
BROKEN = "$\\frac{1}{2$"
WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
DECK_PATH = "/tmp/matriser.pdf"
PROMPT_VARIANTS = [(WATCH_URL, None), (WATCH_URL, DECK_PATH), (None, DECK_PATH)]
PROMPT_VARIANT_IDS = ["source", "source-and-deck", "deck-only"]
TRY_YOURSELF = "Ingen lösning i föreläsningen. Försök själv."


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def node(kind: str, label: str, *children: dict, stamps=(), slides=(), explanation: str = "") -> dict:
    """A node of a type with children, with every part present."""
    return {
        "type": kind,
        "label": label,
        "explanation": explanation,
        "stamps": list(stamps),
        "slides": list(slides),
        "children": list(children),
    }


def term(label: str = "Gauss", **parts) -> dict:
    return node("term", label, **parts)


def worked(
    kind: str = "exempel",
    label: str = "Rad gånger kolonn",
    *,
    task: str = "Lös $x + 1 = 2$",
    steps=(("x = 2 - 1", "subtrahera 1"), ("x = 1", "")),
    answer: str = "$x = 1$",
    slides=(),
) -> dict:
    """An exempel or övning node, with every part present."""
    return {
        "type": kind,
        "label": label,
        "stamps": [],
        "slides": list(slides),
        "task": task,
        "steps": [{"calculation": calculation, "reason": reason} for calculation, reason in steps],
        "answer": answer,
    }


def lecture(*under_slide: dict, slides=()) -> dict:
    """The main topic Matriser, one topic Rader, one slide node Slide 1 listing `slides`, and these nodes under it."""
    return node("main-topic", "Matriser", node("topic", "Rader", node("slide", "Slide 1", *under_slide, slides=slides)))


@pytest.fixture
def transcript_id(source: Path, cache_dir: Path) -> str:
    """A Transcript with no Deck."""
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def problems_of(transcript_id: str, outline: dict, cache_dir: Path, tmp_path: Path):
    """Render an Outline that must fail, and return its problems in the order reported."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    return caught.value.problems


def messages_of(transcript_id: str, outline: dict, cache_dir: Path, tmp_path: Path) -> list[str]:
    return [problem.message for problem in problems_of(transcript_id, outline, cache_dir, tmp_path)]


# The render-time LaTeX check.


def test_broken_latex_in_an_explanation_fails_the_render(transcript_id, cache_dir: Path, tmp_path: Path):
    """An explanation holding a `$...$` KaTeX cannot draw fails the render."""
    with pytest.raises(OutlineStructureError):
        render_mindmap(transcript_id, lecture(term(explanation=f"Hälften är {BROKEN}.")), cache_dir=cache_dir, output_dir=tmp_path)


def test_broken_latex_writes_no_page(transcript_id, cache_dir: Path, tmp_path: Path):
    """A render that fails on broken LaTeX writes nothing."""
    with pytest.raises(OutlineStructureError):
        render_mindmap(transcript_id, lecture(term(explanation=BROKEN)), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert not (tmp_path / "out" / f"{transcript_id}.html").exists()


def test_broken_latex_problem_names_its_node_by_label_path(transcript_id, cache_dir: Path, tmp_path: Path):
    """A broken-LaTeX problem's path is the labels from the main topic down to its node."""
    problems = problems_of(transcript_id, lecture(term("Bråk", explanation=BROKEN)), cache_dir, tmp_path)
    assert [problem.path for problem in problems] == [(*SLIDE_PATH, "Bråk")]


@pytest.mark.parametrize(
    "outline, part",
    [
        (lecture(term(explanation=BROKEN)), "explanation"),
        (lecture(worked(task=f"Lös {BROKEN}")), "task"),
        (lecture(worked(answer=BROKEN)), "answer"),
        (lecture(worked(steps=(("x = 1", ""), ("\\frac{1}{2", "")))), "step 2 calculation"),
        (lecture(worked(steps=(("x = 1", ""), ("x = 2", f"dela med {BROKEN}")))), "step 2 reason"),
    ],
    ids=["explanation", "task", "answer", "step-calculation", "step-reason"],
)
def test_broken_latex_problem_names_its_part(transcript_id, cache_dir: Path, tmp_path: Path, outline: dict, part: str):
    """A broken-LaTeX problem's message starts with the part the piece sits in, steps counted from 1."""
    [message] = messages_of(transcript_id, outline, cache_dir, tmp_path)
    assert message.startswith(part)


def test_broken_latex_problem_quotes_the_piece_with_its_dollars(transcript_id, cache_dir: Path, tmp_path: Path):
    """The message holds the broken piece exactly as the part has it, dollars included."""
    [message] = messages_of(transcript_id, lecture(worked(task=f"Lös {BROKEN} nu")), cache_dir, tmp_path)
    assert BROKEN in message


def test_broken_latex_problem_gives_katex_reason(transcript_id, cache_dir: Path, tmp_path: Path):
    """The message ends with KaTeX's own reason, and where in the piece it hit it."""
    [message] = messages_of(transcript_id, lecture(term(explanation=BROKEN)), cache_dir, tmp_path)
    assert message.endswith(": Unexpected end of input in a macro argument, expected '}' at end of input")


def test_whole_calculation_is_the_quoted_piece(transcript_id, cache_dir: Path, tmp_path: Path):
    """A broken calculation is quoted whole, with no dollars added."""
    outline = lecture(worked(steps=(("x = \\frac{1}{2", ""),)))
    [message] = messages_of(transcript_id, outline, cache_dir, tmp_path)
    assert '"x = \\frac{1}{2"' in message


def test_unclosed_dollar_is_broken_to_the_end_of_the_part(transcript_id, cache_dir: Path, tmp_path: Path):
    """A `$` with no closing `$` is one broken piece, from that `$` to the end of the part."""
    [message] = messages_of(transcript_id, lecture(worked(task="Lös $x + 1 nu")), cache_dir, tmp_path)
    assert '"$x + 1 nu"' in message


def test_double_dollar_is_broken(transcript_id, cache_dir: Path, tmp_path: Path):
    """`$$` is broken, since math is never display mode."""
    messages = messages_of(transcript_id, lecture(worked(task="Lös $$x^2 = 4$$")), cache_dir, tmp_path)
    assert any('"$$"' in message for message in messages)


def test_unknown_command_is_broken(transcript_id, cache_dir: Path, tmp_path: Path):
    """A command KaTeX does not know is broken, though its braces balance."""
    messages = messages_of(transcript_id, lecture(term(explanation="Se $\\foo{x}$.")), cache_dir, tmp_path)
    assert messages[0].startswith("explanation")


def test_dollar_in_a_calculation_is_broken(transcript_id, cache_dir: Path, tmp_path: Path):
    """A calculation is LaTeX alone, so a `$` in it is broken."""
    messages = messages_of(transcript_id, lecture(worked(steps=(("$x = 1$", ""),))), cache_dir, tmp_path)
    assert messages[0].startswith("step 1 calculation")


def test_supported_latex_is_not_reported(transcript_id, cache_dir: Path, tmp_path: Path):
    """Only the broken piece is reported, while a matrix KaTeX can draw beside it is not."""
    matrix = term("Matris", explanation="$\\begin{pmatrix} 1 & 2 \\\\ 3 & 4 \\end{pmatrix}$")
    problems = problems_of(transcript_id, lecture(matrix, term("Bråk", explanation=BROKEN)), cache_dir, tmp_path)
    assert [problem.path for problem in problems] == [(*SLIDE_PATH, "Bråk")]


def test_escaped_dollar_does_not_open_math(transcript_id, cache_dir: Path, tmp_path: Path):
    """`\\$` is a literal dollar sign, so the broken piece starts at the next real `$`."""
    [message] = messages_of(transcript_id, lecture(term(explanation=f"Kostar 5 \\$ och {BROKEN}")), cache_dir, tmp_path)
    assert f'"{BROKEN}"' in message


def test_escaped_dollar_inside_math_does_not_close_it(transcript_id, cache_dir: Path, tmp_path: Path):
    """`\\$` inside math stays math, so the piece runs to the next real `$`."""
    piece = "$5\\$ + \\frac{1}{2$"
    [message] = messages_of(transcript_id, lecture(term(explanation=f"Pris {piece}")), cache_dir, tmp_path)
    assert f'"{piece}"' in message


def test_latex_in_a_label_is_not_checked(transcript_id, cache_dir: Path, tmp_path: Path):
    """A label is not checked, so broken LaTeX in one gives no problem."""
    outline = lecture(term(BROKEN), term("Bråk", explanation=BROKEN))
    problems = problems_of(transcript_id, outline, cache_dir, tmp_path)
    assert [problem.path for problem in problems] == [(*SLIDE_PATH, "Bråk")]


def test_two_broken_pieces_in_one_part_are_two_problems(transcript_id, cache_dir: Path, tmp_path: Path):
    """Each broken piece in a part is a problem of its own."""
    messages = messages_of(transcript_id, lecture(term(explanation=f"{BROKEN} och $\\foo$")), cache_dir, tmp_path)
    assert len(messages) == 2


def test_broken_latex_is_listed_with_other_problems(transcript_id, cache_dir: Path, tmp_path: Path):
    """Broken LaTeX is listed in the same error as a malformed stamp, not after a second render."""
    outline = lecture(term("Stamp", stamps=["1:75"]), term("Bråk", explanation=BROKEN))
    problems = problems_of(transcript_id, outline, cache_dir, tmp_path)
    assert [problem.path[-1] for problem in problems] == ["Stamp", "Bråk"]


def test_deck_render_fails_on_broken_latex(deck: Path, cache_dir: Path, tmp_path: Path):
    """A render against a standalone Deck fails on broken LaTeX too."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    with pytest.raises(OutlineStructureError):
        render_deck_mindmap(deck_id, lecture(term(explanation=BROKEN)), cache_dir=cache_dir, output_dir=tmp_path)


# What the schema, the render tools and the prompts ask the LLM for.


def tool_description(server, name: str) -> str:
    """Return a tool's description with every run of whitespace collapsed to one space."""

    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    description = next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)
    return " ".join(description.split())


def prompt_text(server, source: str | None, deck: str | None) -> str:
    arguments = {key: value for key, value in {"source": source, "deck": deck}.items() if value}
    name = "lecture_to_mindmap"

    async def run():
        async with Client(server) as client:
            return await client.get_prompt(name, arguments)

    return asyncio.run(run()).messages[0].content.text


def test_schema_description_puts_reason_math_between_dollars():
    """The schema tells the LLM a step's reason is prose with math between `$...$`."""
    description = get_outline_schema().schema["description"]
    assert re.search(r"reason[^.]*\$\.\.\.\$", description, re.IGNORECASE)


def test_schema_description_forbids_double_dollars():
    """The schema tells the LLM never to write `$$`."""
    assert "$$" in get_outline_schema().schema["description"]


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_render_description_asks_for_math_between_dollars(cache_dir: Path, tool: str):
    """Both render tool descriptions ask for math between `$...$`."""
    assert "$...$" in tool_description(create_server(cache_dir=cache_dir), tool)


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_render_description_forbids_double_dollars(cache_dir: Path, tool: str):
    """Both render tool descriptions say never to write `$$`."""
    assert "$$" in tool_description(create_server(cache_dir=cache_dir), tool)


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_render_description_asks_for_one_calculation_per_step(cache_dir: Path, tool: str):
    """Both render tool descriptions ask for each step to be one calculation."""
    assert "one calculation" in tool_description(create_server(cache_dir=cache_dir), tool)


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_render_description_limits_a_reason_to_one_sentence(cache_dir: Path, tool: str):
    """Both render tool descriptions allow at most one short Swedish sentence per reason."""
    assert "one short Swedish sentence" in tool_description(create_server(cache_dir=cache_dir), tool)


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_render_description_says_to_fix_broken_latex(cache_dir: Path, tool: str):
    """Both render tool descriptions say broken LaTeX is among the problems to fix before rendering again."""
    assert "broken LaTeX" in tool_description(create_server(cache_dir=cache_dir), tool)


@pytest.mark.parametrize("source, deck", PROMPT_VARIANTS, ids=PROMPT_VARIANT_IDS)
def test_prompt_asks_for_latex(cache_dir: Path, source: str | None, deck: str | None):
    """Every variant of the lecture prompt asks for LaTeX for every math expression."""
    assert "LaTeX" in prompt_text(create_server(cache_dir=cache_dir), source, deck)


# The page.


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page(viewport={"width": 1200, "height": 800})
    page.set_default_timeout(5_000)
    yield page
    page.close()


@pytest.fixture
def ten_minute_source(tmp_path: Path) -> Path:
    path = tmp_path / "media" / "ten_minutes.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(bytes(2 * TEN_MINUTES_S * SAMPLE_RATE))
    return path


@pytest.fixture
def render_outline(ten_minute_source: Path, deck: Path, cache_dir: Path, tmp_path: Path):
    """Render an Outline against a 10-minute Source with the three-page Deck attached, and return the page's URL."""
    transcript = transcribe(ten_minute_source, cache_dir=cache_dir, recognize=one_sentence)
    read_slides(transcript.transcript_id, deck, cache_dir=cache_dir)

    def render(outline: dict) -> str:
        return render_mindmap(transcript.transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").page.as_uri()

    return render


def open_panel(page, url: str, label: str) -> None:
    """Open the page with every node shown, then the panel of the node whose card label ends with `label`."""
    page.goto(f"{url}?depth=all")
    page.locator(".node-label").filter(has_text=re.compile(f"{re.escape(label)}$")).dispatch_event("click")


def katex_count(page, selector: str) -> int:
    return page.locator(f"{selector} .katex").count()


def box(page):
    return page.locator("#panel #worked")


def section(page, summary: str):
    return box(page).locator("details", has=page.locator("summary", has_text=summary))


def open_solution(page) -> None:
    section(page, "Visa lösning").locator("summary").click()


def top(locator) -> float:
    return locator.bounding_box()["y"]


def bottom(locator) -> float:
    found = locator.bounding_box()
    return found["y"] + found["height"]


def test_explanation_math_typesets(page, render_outline):
    """The math in an explanation typesets with KaTeX."""
    open_panel(page, render_outline(lecture(term(explanation="Arean är $\\pi r^2$."))), "Gauss")
    assert katex_count(page, "#explanation") == 1


def test_math_typesets_with_no_network(page, render_outline):
    """A page opened with every network request blocked still typesets its math."""
    url = render_outline(lecture(term(explanation="Arean är $\\pi r^2$.")))
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort())
    open_panel(page, url, "Gauss")
    assert katex_count(page, "#explanation") == 1


def test_math_is_always_inline(page, render_outline):
    """Math typesets inline in the line of prose, never as a display block."""
    open_panel(page, render_outline(lecture(term(explanation="Låt $x = 1$ vara givet."))), "Gauss")
    kinds = page.locator("#explanation .katex").evaluate_all(
        "found => found.map(math => math.closest('.katex-display') ? 'display' : 'inline')"
    )
    assert kinds == ["inline"]


def test_long_math_breaks_over_lines(page, render_outline):
    """A sum too long for the panel breaks over more than one line, at its `=` and `+`."""
    long_sum = " + ".join(f"a_{{{n}}}" for n in range(1, 31)) + " = b"
    open_panel(page, render_outline(lecture(term(explanation=f"${long_sum}$"))), "Gauss")
    tops = page.locator("#explanation .katex .base").evaluate_all(
        "found => [...new Set(found.map(base => Math.round(base.getBoundingClientRect().top)))]"
    )
    assert len(tops) > 1


def test_escaped_dollar_shows_a_dollar_sign(page, render_outline):
    """`\\$` shows as a literal dollar sign."""
    open_panel(page, render_outline(lecture(term(explanation="Kostar 5 \\$ styck."))), "Gauss")
    assert page.locator("#explanation").inner_text() == "Kostar 5 $ styck."


def test_label_latex_stays_raw_while_explanation_typesets(page, render_outline):
    """In one panel, LaTeX in the label shows as its source while the explanation's math typesets."""
    open_panel(page, render_outline(lecture(term("$x^2$", explanation="$x^2$"))), "$x^2$")
    assert (katex_count(page, "#panel-title"), katex_count(page, "#explanation")) == (0, 1)


@pytest.mark.parametrize("kind, label", [("exempel", "Exempel"), ("övning", "Övning")])
def test_worked_panel_label_names_its_type(page, render_outline, kind: str, label: str):
    """The label above an exempel's or övning's text reads `Exempel` or `Övning`."""
    open_panel(page, render_outline(lecture(worked(kind))), "Rad gånger kolonn")
    assert page.locator(".explanation-label").text_content() == label


@pytest.mark.parametrize(
    "label, heading", [("Andra", "Exempel 2"), ("Tredje", "Övning 1")], ids=["second-exempel", "first-ovning"]
)
def test_box_heading_counts_exempel_and_ovning_separately(page, render_outline, label: str, heading: str):
    """The box heading counts exempel and övning separately, in Outline order."""
    outline = lecture(worked("exempel", "Första"), worked("exempel", "Andra"), worked("övning", "Tredje"))
    open_panel(page, render_outline(outline), label)
    assert box(page).get_by_role("heading").text_content() == heading


def test_box_shows_the_task_under_its_heading(page, render_outline):
    """The task is the first text in the box after its heading."""
    open_panel(page, render_outline(lecture(worked(task="Lös uppgiften nu"))), "Rad gånger kolonn")
    assert box(page).inner_text().splitlines()[1] == "Lös uppgiften nu"


def test_box_task_math_typesets(page, render_outline):
    """The math in a task typesets."""
    open_panel(page, render_outline(lecture(worked(task="Lös $x + 1 = 2$"))), "Rad gånger kolonn")
    assert box(page).locator(".katex").count() >= 1


def test_long_task_prose_wraps_inside_the_box(page, render_outline):
    """A long task wraps inside the box instead of running off it."""
    task = "Bestäm " + " och ".join(f"värdet av $x_{{{n}}}$" for n in range(1, 25)) + "."
    open_panel(page, render_outline(lecture(worked(task=task))), "Rad gånger kolonn")
    fits = box(page).evaluate_all("found => found.map(box => box.scrollWidth <= box.clientWidth)")
    assert fits == [True]


def test_solution_starts_closed(page, render_outline):
    """The Visa lösning section starts closed."""
    open_panel(page, render_outline(lecture(worked())), "Rad gånger kolonn")
    assert section(page, "Visa lösning").evaluate("details => details.open") is False


def test_solution_toggle_shows_the_step_count(page, render_outline):
    """The Visa lösning toggle shows how many steps the solution has."""
    steps = (("a = 1", ""), ("b = 2", ""), ("c = 3", ""))
    open_panel(page, render_outline(lecture(worked(steps=steps))), "Rad gånger kolonn")
    assert "3" in section(page, "Visa lösning").locator("summary").text_content()


def test_open_solution_numbers_steps_from_one(page, render_outline):
    """Opened, the solution shows one row per step, numbered 1, 2 and on."""
    open_panel(page, render_outline(lecture(worked())), "Rad gånger kolonn")
    open_solution(page)
    numbers = box(page).locator(".step").evaluate_all("rows => rows.map(row => row.innerText.trim().split(/\\s/)[0])")
    assert numbers == ["1", "2"]


def test_step_calculation_typesets_inline(page, render_outline):
    """A step's calculation typesets as inline math."""
    open_panel(page, render_outline(lecture(worked(steps=(("x = \\frac{1}{2}", ""),)))), "Rad gånger kolonn")
    open_solution(page)
    assert box(page).locator(".step-calculation .katex").count() == 1


def test_step_reason_math_typesets(page, render_outline):
    """Math in a step's reason typesets, such as a Greek letter."""
    outline = lecture(worked(steps=(("x = 1", "sätt in $\\alpha$"),)))
    open_panel(page, render_outline(outline), "Rad gånger kolonn")
    open_solution(page)
    assert box(page).locator(".step-reason .katex").count() == 1


def test_step_reason_sits_under_its_calculation(page, render_outline):
    """A step's reason sits under its calculation."""
    open_panel(page, render_outline(lecture(worked(steps=(("x = 1", "subtrahera 1"),)))), "Rad gånger kolonn")
    open_solution(page)
    assert top(box(page).locator(".step-reason")) >= bottom(box(page).locator(".step-calculation"))


def test_answer_starts_closed(page, render_outline):
    """The Visa svar section starts closed."""
    open_panel(page, render_outline(lecture(worked())), "Rad gånger kolonn")
    assert section(page, "Visa svar").evaluate("details => details.open") is False


def test_answer_comes_after_the_solution(page, render_outline):
    """The Visa svar section sits below the Visa lösning section."""
    open_panel(page, render_outline(lecture(worked())), "Rad gånger kolonn")
    assert top(section(page, "Visa svar")) >= bottom(section(page, "Visa lösning"))


def test_box_without_steps_has_no_solution_section(page, render_outline):
    """A box whose node has no steps shows no Visa lösning section."""
    open_panel(page, render_outline(lecture(worked(steps=()))), "Rad gånger kolonn")
    shown = box(page).evaluate_all("found => found.map(box => box.textContent.includes('Visa lösning'))")
    assert shown == [False]


def test_box_without_answer_has_no_answer_section(page, render_outline):
    """A box whose node has an empty answer shows no Visa svar section."""
    open_panel(page, render_outline(lecture(worked(answer=""))), "Rad gånger kolonn")
    shown = box(page).evaluate_all("found => found.map(box => box.textContent.includes('Visa svar'))")
    assert shown == [False]


def test_box_with_neither_says_to_try_yourself(page, render_outline):
    """A box with no steps and no answer shows the try-it-yourself line."""
    open_panel(page, render_outline(lecture(worked(steps=(), answer=""))), "Rad gånger kolonn")
    assert TRY_YOURSELF in box(page).text_content()


def test_box_with_steps_does_not_say_to_try_yourself(page, render_outline):
    """A box that has steps leaves the try-it-yourself line out."""
    open_panel(page, render_outline(lecture(worked(answer=""))), "Rad gånger kolonn")
    shown = box(page).evaluate_all(f"found => found.map(box => box.textContent.includes({TRY_YOURSELF!r}))")
    assert shown == [False]


def test_box_text_is_set_in_katex_main(page, render_outline):
    """Box text is set in KaTeX_Main, so prose and math share one face."""
    open_panel(page, render_outline(lecture(worked())), "Rad gånger kolonn")
    families = box(page).evaluate_all("found => found.map(box => getComputedStyle(box).fontFamily)")
    assert [family.split(",")[0].strip("\"' ") for family in families] == ["KaTeX_Main"]


def test_section_toggles_use_the_app_sans(page, render_outline):
    """The Visa lösning and Visa svar toggles use the app's sans, Inter."""
    open_panel(page, render_outline(lecture(worked())), "Rad gånger kolonn")
    families = box(page).locator("summary").evaluate_all("found => found.map(s => getComputedStyle(s).fontFamily)")
    assert families and all(family.startswith("Inter") for family in families)


def test_slides_sit_below_the_box(page, render_outline):
    """An exempel's Slides sit below its box."""
    open_panel(page, render_outline(lecture(worked(slides=[1]))), "Rad gånger kolonn")
    assert top(page.locator("#slides")) >= bottom(box(page))


def test_source_link_sits_below_the_box(page, render_outline):
    """The Source link sits below the box."""
    open_panel(page, render_outline(lecture(worked())), "Rad gånger kolonn")
    assert top(page.locator("#panel-source")) >= bottom(box(page))
