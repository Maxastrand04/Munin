"""Acceptance tests for #70, the render tool that returns the Drawn Outline."""

import asyncio
import json
from dataclasses import asdict
from pathlib import Path

import pytest
from mcp import Client

from munin.core import (
    DrawnOutline,
    Fragment,
    OutlineStructureError,
    OutlineSyntaxError,
    ProseRun,
    UnknownTranscriptError,
    Vocabulary,
    read_slides,
    render_drawn_outline,
    render_mindmap,
    transcribe,
)
from munin.core.latex import math_html
from munin.mcp_server import create_server

REPO_ROOT = Path(__file__).resolve().parents[1]
KATEX_HTML = 'class="katex"'
DISPLAY_HTML = "katex-display"
BROKEN_LATEX = "$\\frac{1}{2$"


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one Swedish sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def english_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one English sentence."""
    return [Fragment(1.2, 3.0, "Today we talk about matrices.")]


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
    kind: str,
    label: str,
    *,
    task: str = "Lös $x + 1 = 2$",
    steps=(("x = 2 - 1", "subtrahera $1$"),),
    answer: str = "$x = 1$",
) -> dict:
    """An example or exercise node, with every part present."""
    return {
        "type": kind,
        "label": label,
        "stamps": [],
        "slides": [],
        "task": task,
        "steps": [{"calculation": calculation, "reason": reason} for calculation, reason in steps],
        "answer": answer,
    }


def lecture(*under_slide: dict, slides=()) -> dict:
    """The main topic Matriser, one topic Rader, one slide node Slide 1 listing `slides`, and these nodes under it."""
    return node("main-topic", "Matriser", node("topic", "Rader", node("slide", "Slide 1", *under_slide, slides=slides)))


def last_node(drawn: DrawnOutline):
    return drawn.nodes[-1]


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


def files_under(folder: Path) -> set[Path]:
    return {path for path in folder.rglob("*") if path.is_file()}


@pytest.fixture
def transcript_id(source: Path, cache_dir: Path) -> str:
    """A Swedish Transcript with no Deck."""
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


@pytest.fixture
def english_transcript_id(source: Path, cache_dir: Path) -> str:
    """An English Transcript with no Deck."""
    return transcribe(source, language="en", cache_dir=cache_dir, recognize=english_sentence).transcript_id


@pytest.fixture
def deck_transcript_id(transcript_id: str, deck: Path, cache_dir: Path) -> str:
    """A Swedish Transcript with the three-Slide Deck attached."""
    read_slides(transcript_id, deck, cache_dir=cache_dir)
    return transcript_id


# The LaTeX-to-HTML piece


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


# Nodes, parents and links


def test_drawn_outline_lists_every_node_in_outline_order(transcript_id: str, cache_dir: Path):
    """The Drawn Outline holds every Outline node, in Outline order."""
    drawn = render_drawn_outline(transcript_id, lecture(term("Gauss"), term("Rang")), cache_dir=cache_dir)
    assert [n.label for n in drawn.nodes] == ["Matriser", "Rader", "Slide 1", "Gauss", "Rang"]


def test_drawn_node_points_at_its_parent(transcript_id: str, cache_dir: Path):
    """Each node's `parent` is its parent's `id`, and the main topic's is None."""
    drawn = render_drawn_outline(transcript_id, lecture(term("Gauss"), term("Rang")), cache_dir=cache_dir)
    assert [n.parent for n in drawn.nodes] == [None, 0, 1, 2, 2]


def test_drawn_node_keeps_its_type(transcript_id: str, cache_dir: Path):
    """Each node carries its Outline type."""
    drawn = render_drawn_outline(transcript_id, lecture(term()), cache_dir=cache_dir)
    assert [n.type for n in drawn.nodes] == ["main-topic", "topic", "slide", "term"]


def test_stamp_becomes_timestamp_link_to_source(source: Path, transcript_id: str, cache_dir: Path):
    """A stamp becomes a Timestamp link to the Transcript's Source at that second."""
    drawn = render_drawn_outline(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir)
    assert [link.url for link in last_node(drawn).links] == [f"{source.resolve().as_uri()}#t=3"]


def test_timestamp_link_text_is_the_displayed_stamp(transcript_id: str, cache_dir: Path):
    """A Timestamp link's text is the stamp as the page shows it."""
    drawn = render_drawn_outline(transcript_id, lecture(term(stamps=["0:03"])), cache_dir=cache_dir)
    assert [link.text for link in last_node(drawn).links] == ["0:03"]


def test_term_is_the_casefolded_label(transcript_id: str, cache_dir: Path):
    """A node's `term` is its label with whitespace runs made one space and case folded."""
    drawn = render_drawn_outline(transcript_id, lecture(term("Gauss  Elimination")), cache_dir=cache_dir)
    assert last_node(drawn).term == "gauss elimination"


# The page-level data


def test_title_is_the_main_topic_label(transcript_id: str, cache_dir: Path):
    """The Drawn Outline's title is the main topic's label."""
    assert render_drawn_outline(transcript_id, lecture(), cache_dir=cache_dir).title == "Matriser"


def test_source_url_is_the_source_link(source: Path, transcript_id: str, cache_dir: Path):
    """The Drawn Outline's `source_url` is the address the page's Source link opens."""
    assert render_drawn_outline(transcript_id, lecture(), cache_dir=cache_dir).source_url == source.resolve().as_uri()


def test_language_is_the_lecture_language(english_transcript_id: str, cache_dir: Path):
    """An English Transcript gives a Drawn Outline in `en`."""
    assert render_drawn_outline(english_transcript_id, lecture(), cache_dir=cache_dir).language == "en"


def test_legacy_transcript_is_swedish(legacy_transcript_id: str, cache_dir: Path):
    """A Transcript cached before lecture languages existed gives a Drawn Outline in `sv`."""
    assert render_drawn_outline(legacy_transcript_id, lecture(), cache_dir=cache_dir).language == "sv"


# Math as HTML, prose as text


def test_explanation_math_becomes_katex_html(transcript_id: str, cache_dir: Path):
    """A `$...$` piece in an explanation becomes one math run holding `math_html` of the piece between the dollars."""
    drawn = render_drawn_outline(transcript_id, lecture(term(explanation="$x^2$")), cache_dir=cache_dir)
    assert last_node(drawn).explanation == (ProseRun("math", math_html("x^2")),)


def test_explanation_prose_around_math_becomes_text_runs(transcript_id: str, cache_dir: Path):
    """The prose before and after a `$...$` piece comes back as text runs, as written."""
    drawn = render_drawn_outline(transcript_id, lecture(term(explanation="Låt $x$ vara stor")), cache_dir=cache_dir)
    runs = last_node(drawn).explanation
    assert [(r.kind, r.content) for r in runs if r.kind == "text"] == [("text", "Låt "), ("text", " vara stor")]


def test_explanation_runs_follow_the_prose_order(transcript_id: str, cache_dir: Path):
    """An explanation's runs come in the order the prose holds them."""
    drawn = render_drawn_outline(transcript_id, lecture(term(explanation="Låt $x$ vara stor")), cache_dir=cache_dir)
    assert [r.kind for r in last_node(drawn).explanation] == ["text", "math", "text"]


def test_escaped_dollar_in_prose_is_unescaped(transcript_id: str, cache_dir: Path):
    """A `\\$` in prose comes back as a literal `$` in a text run."""
    drawn = render_drawn_outline(transcript_id, lecture(term(explanation="Kostar \\$5")), cache_dir=cache_dir)
    assert last_node(drawn).explanation == (ProseRun("text", "Kostar $5"),)


def test_explanation_line_breaks_are_kept(transcript_id: str, cache_dir: Path):
    """Line breaks in an explanation's prose come back in its text run."""
    drawn = render_drawn_outline(transcript_id, lecture(term(explanation="Rad ett\nRad två")), cache_dir=cache_dir)
    assert last_node(drawn).explanation == (ProseRun("text", "Rad ett\nRad två"),)


def test_empty_explanation_has_no_runs(transcript_id: str, cache_dir: Path):
    """An empty explanation comes back as no runs."""
    drawn = render_drawn_outline(transcript_id, lecture(term(explanation="")), cache_dir=cache_dir)
    assert last_node(drawn).explanation == ()


@pytest.mark.parametrize("part", ["task", "answer"])
def test_box_prose_math_becomes_katex_html(part: str, transcript_id: str, cache_dir: Path):
    """A `$...$` piece in a task or an answer becomes a math run of KaTeX HTML."""
    drawn = render_drawn_outline(transcript_id, lecture(worked("example", "Ekvation", **{part: "$x$"})), cache_dir=cache_dir)
    assert getattr(last_node(drawn).worked, part) == (ProseRun("math", math_html("x")),)


def test_step_reason_math_becomes_katex_html(transcript_id: str, cache_dir: Path):
    """A `$...$` piece in a step's reason becomes a math run of KaTeX HTML."""
    outline = lecture(worked("example", "Ekvation", steps=(("x = 1", "$x$"),)))
    (step,) = last_node(render_drawn_outline(transcript_id, outline, cache_dir=cache_dir)).worked.steps
    assert step.reason == (ProseRun("math", math_html("x")),)


def test_step_calculation_becomes_katex_html(transcript_id: str, cache_dir: Path):
    """A step's calculation becomes KaTeX's HTML for the whole calculation."""
    outline = lecture(worked("example", "Ekvation", steps=(("\\frac{1}{2}", ""),)))
    (step,) = last_node(render_drawn_outline(transcript_id, outline, cache_dir=cache_dir)).worked.steps
    assert KATEX_HTML in step.calculation


def test_step_calculation_is_inline_math(transcript_id: str, cache_dir: Path):
    """A step's calculation is drawn as inline math, as the page draws it."""
    outline = lecture(worked("example", "Ekvation", steps=(("\\frac{1}{2}", ""),)))
    (step,) = last_node(render_drawn_outline(transcript_id, outline, cache_dir=cache_dir)).worked.steps
    assert DISPLAY_HTML not in step.calculation


def test_label_comes_back_as_written(transcript_id: str, cache_dir: Path):
    """A label comes back exactly as the Outline holds it, LaTeX and `\\$` included."""
    drawn = render_drawn_outline(transcript_id, lecture(term("Pris \\$5 och $x$")), cache_dir=cache_dir)
    assert last_node(drawn).label == "Pris \\$5 och $x$"


# Examples and exercises


def test_example_label_has_no_prefix(transcript_id: str, cache_dir: Path):
    """An example's label comes back without the `Exempel: ` prefix the page adds."""
    drawn = render_drawn_outline(transcript_id, lecture(worked("example", "Ekvation")), cache_dir=cache_dir)
    assert last_node(drawn).label == "Ekvation"


def test_node_that_is_not_an_example_has_no_box(transcript_id: str, cache_dir: Path):
    """A node that is neither an example nor an exercise has no box."""
    drawn = render_drawn_outline(transcript_id, lecture(term()), cache_dir=cache_dir)
    assert last_node(drawn).worked is None


@pytest.mark.parametrize(
    ("language_fixture", "heading", "solution_toggle", "answer_toggle"),
    [
        ("transcript_id", "Exempel 1", "Visa lösning", "Visa svar"),
        ("english_transcript_id", "Example 1", "Show solution", "Show answer"),
    ],
    ids=["sv", "en"],
)
def test_box_wording_follows_the_lecture_language(
    language_fixture: str,
    heading: str,
    solution_toggle: str,
    answer_toggle: str,
    request: pytest.FixtureRequest,
    cache_dir: Path,
):
    """A Swedish and an English lecture each get box heading and toggle wording in their own language."""
    transcript = request.getfixturevalue(language_fixture)
    box = last_node(render_drawn_outline(transcript, lecture(worked("example", "Ekvation")), cache_dir=cache_dir)).worked
    assert (box.heading, box.solution_toggle, box.answer_toggle) == (heading, solution_toggle, answer_toggle)


@pytest.mark.parametrize(
    ("language_fixture", "no_solution"),
    [
        ("transcript_id", "Ingen lösning i föreläsningen. Försök själv."),
        ("english_transcript_id", "No solution in the lecture. Try it yourself."),
    ],
    ids=["sv", "en"],
)
def test_no_solution_line_follows_the_lecture_language(
    language_fixture: str, no_solution: str, request: pytest.FixtureRequest, cache_dir: Path
):
    """The box's no-solution line is in the lecture's language."""
    transcript = request.getfixturevalue(language_fixture)
    box = last_node(render_drawn_outline(transcript, lecture(worked("exercise", "Ekvation")), cache_dir=cache_dir)).worked
    assert box.no_solution == no_solution


def test_english_single_step_count_is_singular(english_transcript_id: str, cache_dir: Path):
    """An English box with one step counts it as `1 step`."""
    drawn = render_drawn_outline(english_transcript_id, lecture(worked("example", "Equation")), cache_dir=cache_dir)
    assert last_node(drawn).worked.step_count == "1 step"


def test_box_numbers_count_each_type_separately(transcript_id: str, cache_dir: Path):
    """Examples and exercises are numbered separately, in Outline order, from 1."""
    outline = lecture(worked("example", "A"), worked("exercise", "B"), worked("example", "C"))
    drawn = render_drawn_outline(transcript_id, outline, cache_dir=cache_dir)
    assert [n.worked.heading for n in drawn.nodes if n.worked] == ["Exempel 1", "Övning 1", "Exempel 2"]


def test_box_title_is_the_type_name(transcript_id: str, cache_dir: Path):
    """An exercise's box title is the type name in the page language."""
    drawn = render_drawn_outline(transcript_id, lecture(worked("exercise", "Ekvation")), cache_dir=cache_dir)
    assert last_node(drawn).worked.title == "Övning"


# Slides


def test_transcript_with_deck_gets_slide_numbers(deck_transcript_id: str, cache_dir: Path):
    """A node on a Transcript with a Deck carries its Slide numbers in Slide order."""
    drawn = render_drawn_outline(deck_transcript_id, lecture(term(slides=[3, 1])), cache_dir=cache_dir)
    assert last_node(drawn).slides == (1, 3)


def test_drawn_outline_carries_no_slide_images(deck_transcript_id: str, cache_dir: Path):
    """A Drawn Outline on a Transcript with a Deck holds no Slide image."""
    drawn = render_drawn_outline(deck_transcript_id, lecture(term(slides=[1])), cache_dir=cache_dir)
    assert "data:image" not in json.dumps(asdict(drawn))


# The check and its errors


def test_bad_outline_gets_the_html_renders_problems(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """An Outline with problems raises `OutlineStructureError` with the same problems `render_mindmap` reports."""
    outline = lecture(term("Gauss", stamps=["1:75"], explanation=BROKEN_LATEX), term(""))
    with pytest.raises(OutlineStructureError) as expected:
        render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    with pytest.raises(OutlineStructureError) as caught:
        render_drawn_outline(transcript_id, outline, cache_dir=cache_dir)
    assert caught.value.problems == expected.value.problems


def test_markdown_outline_raises_outline_syntax_error(transcript_id: str, cache_dir: Path):
    """Outline text that is not JSON raises `OutlineSyntaxError`."""
    with pytest.raises(OutlineSyntaxError):
        render_drawn_outline(transcript_id, "# Matriser\n- Rader", cache_dir=cache_dir)


def test_outline_as_json_text_draws_as_the_object_does(transcript_id: str, cache_dir: Path):
    """An Outline given as JSON text gives the same Drawn Outline as the same Outline as an object."""
    outline = lecture(term("Gauss", stamps=["0:03"], explanation="$x$"))
    as_text = render_drawn_outline(transcript_id, json.dumps(outline), cache_dir=cache_dir)
    assert as_text == render_drawn_outline(transcript_id, outline, cache_dir=cache_dir)


def test_unknown_transcript_raises_before_the_outline_is_read(cache_dir: Path):
    """An unknown Transcript ID raises `UnknownTranscriptError`, even with an Outline that is not JSON."""
    with pytest.raises(UnknownTranscriptError):
        render_drawn_outline("0" * 16, "not json", cache_dir=cache_dir)


def test_render_drawn_outline_writes_no_file(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Rendering a Drawn Outline writes no file in the test's folder."""
    before = files_under(tmp_path)
    render_drawn_outline(transcript_id, lecture(term()), cache_dir=cache_dir)
    assert files_under(tmp_path) == before


def test_render_drawn_outline_writes_no_page(transcript_id: str, cache_dir: Path):
    """Rendering a Drawn Outline writes no page to the default output folder."""
    render_drawn_outline(transcript_id, lecture(term()), cache_dir=cache_dir)
    assert not (REPO_ROOT / "mindmaps" / f"{transcript_id}.html").exists()


# The MCP tool


def test_mcp_render_drawn_outline_returns_nodes(source: Path, cache_dir: Path, tmp_path: Path):
    """The `render_drawn_outline` tool returns the Drawn Outline's nodes as JSON."""
    server = create_server(cache_dir=cache_dir, recognize=one_sentence, output_dir=tmp_path / "out")
    transcript = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "render_drawn_outline", {"transcript_id": transcript, "outline": lecture(term())})
    assert [n["label"] for n in result.structured_content["nodes"]] == ["Matriser", "Rader", "Slide 1", "Gauss"]


def test_mcp_render_drawn_outline_returns_runs_as_kind_and_content(source: Path, cache_dir: Path, tmp_path: Path):
    """The tool returns each run as an object with `kind` and `content`."""
    server = create_server(cache_dir=cache_dir, recognize=one_sentence, output_dir=tmp_path / "out")
    transcript = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    outline = lecture(term(explanation="Stor"))
    result = call(server, "render_drawn_outline", {"transcript_id": transcript, "outline": outline})
    assert result.structured_content["nodes"][-1]["explanation"] == [{"kind": "text", "content": "Stor"}]


def test_mcp_render_drawn_outline_bad_outline_is_tool_error(source: Path, cache_dir: Path, tmp_path: Path):
    """An Outline with problems comes back as a tool error naming the problem by its path."""
    server = create_server(cache_dir=cache_dir, recognize=one_sentence, output_dir=tmp_path / "out")
    transcript = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "render_drawn_outline", {"transcript_id": transcript, "outline": lecture(term(stamps=["1:75"]))})
    assert "Matriser › Rader › Slide 1 › Gauss" in result.content[0].text


def test_mcp_render_drawn_outline_description_asks_for_schema_first(cache_dir: Path):
    """The tool's description tells the LLM to call `get_outline_schema` before writing an Outline."""
    description = tool_description(create_server(cache_dir=cache_dir), "render_drawn_outline")
    assert "Call `get_outline_schema` before writing an Outline" in description


def test_mcp_render_drawn_outline_description_carries_render_mindmap_guidance(cache_dir: Path):
    """The tool's description carries `render_mindmap`'s Outline guidance word for word."""
    server = create_server(cache_dir=cache_dir)
    guidance = tool_description(server, "render_mindmap").split("Write the Outline like this:")[1].split("Returns")[0]
    assert guidance in tool_description(server, "render_drawn_outline")
