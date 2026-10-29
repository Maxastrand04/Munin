"""Acceptance tests for #42: a structured JSON Outline with typed nodes."""

import asyncio
import base64
import colorsys
import json
import re
import wave
from pathlib import Path

import pytest
from mcp import Client
from playwright.sync_api import sync_playwright

from munin.core import (
    Fragment,
    OutlineStructureError,
    OutlineSyntaxError,
    UnknownDeckError,
    UnknownTranscriptError,
    Vocabulary,
    get_outline_schema,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_OUTLINES = ["matriser-outline.json", "linalg6-matriser-outline.json"]
NODE_TYPES = ["main-topic", "topic", "slide", "term", "exempel", "övning"]
PATH = ("Matriser", "Rader", "Slide 1")
UNKNOWN_ID = "0123456789ab"
ORANGE_HUES = (25, 45)
MIN_ORANGE_SATURATION = 0.5
SAMPLE_RATE = 8_000
TEN_MINUTES_S = 600


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(0.5, 1.0, "Idag ska vi prata om matriser.")]


def transcript_of(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def node(kind: str, label: str, *children: dict, stamps=(), slides=(), explanation: str = "") -> dict:
    """A node of a type with children, in the full shape every part present."""
    return {
        "type": kind,
        "label": label,
        "explanation": explanation,
        "stamps": list(stamps),
        "slides": list(slides),
        "children": list(children),
    }


def worked(
    kind: str,
    label: str,
    *,
    task: str = "Lös x + 1 = 2",
    steps=(("x = 2 - 1", "subtrahera 1"),),
    answer: str = "x = 1",
    stamps=(),
    slides=(),
) -> dict:
    """An exempel or övning node in its full shape."""
    return {
        "type": kind,
        "label": label,
        "stamps": list(stamps),
        "slides": list(slides),
        "task": task,
        "steps": [{"calculation": calculation, "reason": reason} for calculation, reason in steps],
        "answer": answer,
    }


def lecture(*under_slide: dict, slides=()) -> dict:
    """The main topic Matriser, one topic Rader, one slide node Slide 1, and these nodes under it."""
    return node("main-topic", "Matriser", node("topic", "Rader", node("slide", "Slide 1", *under_slide, slides=slides)))


def term(label: str = "Gauss", *children: dict, **parts) -> dict:
    return node("term", label, *children, **parts)


def problem_paths(transcript_id: str, outline, cache_dir: Path, tmp_path: Path) -> list[tuple[str, ...]]:
    """Render an Outline that must fail the check, and return each problem's path in the order reported."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")
    return [problem.path for problem in caught.value.problems]


def encoded(slide) -> str:
    return base64.b64encode(slide.image).decode()


def write_silence(path: Path, seconds: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(bytes(2 * seconds * SAMPLE_RATE))
    return path


@pytest.fixture
def transcript(source: Path, cache_dir: Path) -> str:
    """A Transcript with no Deck."""
    return transcript_of(source, cache_dir)


@pytest.fixture
def five_second_transcript(five_second_source: Path, cache_dir: Path) -> str:
    """A Transcript whose Source lasts exactly 5 seconds, with no Deck."""
    return transcript_of(five_second_source, cache_dir)


@pytest.fixture
def slides_transcript(five_second_source: Path, deck: Path, cache_dir: Path):
    """A 5-second Transcript with the three-Slide Deck attached, and its Slides."""
    transcript_id = transcript_of(five_second_source, cache_dir)
    return transcript_id, read_slides(transcript_id, deck, cache_dir=cache_dir)


@pytest.fixture
def standalone_deck(deck: Path, cache_dir: Path):
    """The three-Slide Deck read on its own."""
    return read_deck(deck, cache_dir=cache_dir)


# The schema tool


def test_outline_schema_is_json_schema_draft_2020_12():
    """`get_outline_schema` returns a JSON Schema of draft 2020-12."""
    assert get_outline_schema().schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


@pytest.mark.parametrize("kind", NODE_TYPES)
def test_outline_schema_names_every_node_type(kind: str):
    """The schema names each of the six node types."""
    assert f'"{kind}"' in json.dumps(get_outline_schema().schema, ensure_ascii=False)


def test_outline_schema_samples_are_an_exempel_then_an_ovning():
    """The samples are an exempel node first and an övning node second."""
    assert [sample["type"] for sample in get_outline_schema().samples] == ["exempel", "övning"]


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_outline_schema_sample_task_carries_latex(index: int):
    """Each sample's task carries LaTeX."""
    assert "\\" in get_outline_schema().samples[index]["task"]


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_outline_schema_sample_steps_carry_latex(index: int):
    """At least one of each sample's steps carries LaTeX in its calculation."""
    assert any("\\" in step["calculation"] for step in get_outline_schema().samples[index]["steps"])


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_outline_schema_sample_answer_carries_latex(index: int):
    """Each sample's answer carries LaTeX."""
    assert "\\" in get_outline_schema().samples[index]["answer"]


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_outline_schema_sample_renders_under_a_slide_node(transcript: str, cache_dir: Path, tmp_path: Path, index: int):
    """Each sample, placed under a slide node, passes the check and renders."""
    sample = get_outline_schema().samples[index]
    page = render_mindmap(transcript, lecture(sample), cache_dir=cache_dir, output_dir=tmp_path).page
    assert page.is_file()


# Rendering a JSON Outline


def test_outline_as_a_dict_renders_a_page(transcript: str, cache_dir: Path, tmp_path: Path):
    """An Outline passed as a dict renders a page."""
    assert render_mindmap(transcript, lecture(term()), cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


def test_outline_as_json_text_renders_a_page(transcript: str, cache_dir: Path, tmp_path: Path):
    """An Outline passed as JSON text renders a page."""
    outline = json.dumps(lecture(term()), ensure_ascii=False)
    assert render_mindmap(transcript, outline, cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


def test_stamp_becomes_a_timestamp_link(five_second_transcript: str, cache_dir: Path, tmp_path: Path):
    """A stamp on a node becomes a Timestamp link to its second in the Source."""
    outline = lecture(term(stamps=["0:03"]))
    page = render_mindmap(five_second_transcript, outline, cache_dir=cache_dir, output_dir=tmp_path).page
    assert re.search(r"file://[^\"'\\\s]*#t=3\b", page.read_text(encoding="utf-8"))


def test_stamp_at_the_source_end_renders(five_second_transcript: str, cache_dir: Path, tmp_path: Path):
    """A stamp exactly at the Source's end passes the check."""
    outline = lecture(term(stamps=["0:05"]))
    assert render_mindmap(five_second_transcript, outline, cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


def test_slide_number_embeds_its_slide(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide number on a node embeds that Slide's image in the page."""
    transcript_id, slides = slides_transcript
    page = render_mindmap(transcript_id, lecture(term(slides=[2])), cache_dir=cache_dir, output_dir=tmp_path).page
    assert encoded(slides[1]) in page.read_text(encoding="utf-8")


def test_slide_node_without_slide_numbers_renders_without_a_deck(transcript: str, cache_dir: Path, tmp_path: Path):
    """In a Transcript with no Deck, a slide node with no Slide numbers stands for a part of the lecture and renders."""
    assert render_mindmap(transcript, lecture(term()), cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


def test_deck_render_embeds_a_numbered_slide(standalone_deck, cache_dir: Path, tmp_path: Path):
    """A Slide number in an Outline rendered against a standalone Deck embeds that Slide."""
    outline = lecture(term(slides=[3]))
    page = render_deck_mindmap(standalone_deck.deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path).page
    assert encoded(standalone_deck.slides[2]) in page.read_text(encoding="utf-8")


@pytest.mark.parametrize("parent", ["main-topic", "topic", "slide", "term"])
def test_exempel_renders_under_every_other_type(transcript: str, cache_dir: Path, tmp_path: Path, parent: str):
    """An exempel may sit under a main-topic, topic, slide or term node."""
    example = worked("exempel", "Rad gånger kolonn")
    outline = {
        "main-topic": node("main-topic", "Matriser", example),
        "topic": node("main-topic", "Matriser", node("topic", "Rader", example)),
        "slide": lecture(example),
        "term": lecture(term("Gauss", example)),
    }[parent]
    assert render_mindmap(transcript, outline, cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


def test_exempel_with_no_steps_and_no_answer_renders(transcript: str, cache_dir: Path, tmp_path: Path):
    """An exempel's steps and answer may be empty."""
    outline = lecture(worked("exempel", "Rad gånger kolonn", steps=(), answer=""))
    assert render_mindmap(transcript, outline, cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


def test_newline_in_an_explanation_renders(transcript: str, cache_dir: Path, tmp_path: Path):
    """An explanation may hold newlines, since it carries prose and no LaTeX."""
    outline = lecture(term(explanation="Första raden.\nAndra raden."))
    assert render_mindmap(transcript, outline, cache_dir=cache_dir, output_dir=tmp_path).page.is_file()


@pytest.mark.parametrize("name", SAMPLE_OUTLINES)
def test_repo_sample_outline_renders(cache_dir: Path, tmp_path: Path, name: str):
    """Each sample Outline in `docs/examples/` is JSON in the new format and renders against a 10-minute Source."""
    source = write_silence(tmp_path / "media" / "ten_minutes.wav", TEN_MINUTES_S)
    outline = (REPO_ROOT / "docs" / "examples" / name).read_text(encoding="utf-8")
    page = render_mindmap(transcript_of(source, cache_dir), outline, cache_dir=cache_dir, output_dir=tmp_path / "out").page
    assert page.is_file()


# Text that is not JSON


def test_text_that_is_not_json_raises_syntax_error(transcript: str, cache_dir: Path, tmp_path: Path):
    """Outline text that is not JSON raises `OutlineSyntaxError`."""
    with pytest.raises(OutlineSyntaxError):
        render_mindmap(transcript, '{"type": "main-topic",', cache_dir=cache_dir, output_dir=tmp_path)


def test_markdown_outline_raises_syntax_error(transcript: str, cache_dir: Path, tmp_path: Path):
    """A Markdown Outline is not JSON, so it raises `OutlineSyntaxError`."""
    with pytest.raises(OutlineSyntaxError):
        render_mindmap(transcript, "# Matriser\n## Rader [0:01]\n", cache_dir=cache_dir, output_dir=tmp_path)


def test_syntax_error_gives_line_and_column(transcript: str, cache_dir: Path, tmp_path: Path):
    """The error gives the line and column where parsing broke, both counted from 1."""
    with pytest.raises(OutlineSyntaxError) as caught:
        render_mindmap(transcript, '{\n  "type": "main-topic",\n  "label": }', cache_dir=cache_dir, output_dir=tmp_path)
    assert (caught.value.line, caught.value.column) == (3, 12)


def test_syntax_error_message_names_the_position(transcript: str, cache_dir: Path, tmp_path: Path):
    """The error's message names the line and column where parsing broke."""
    with pytest.raises(OutlineSyntaxError) as caught:
        render_mindmap(transcript, '{\n  "type": "main-topic",\n  "label": }', cache_dir=cache_dir, output_dir=tmp_path)
    assert "line 3, column 12" in str(caught.value)


def test_syntax_error_message_points_at_the_schema_tool(transcript: str, cache_dir: Path, tmp_path: Path):
    """The error's message tells the LLM to call `get_outline_schema`."""
    with pytest.raises(OutlineSyntaxError) as caught:
        render_mindmap(transcript, "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path)
    assert "get_outline_schema" in str(caught.value)


def test_text_that_is_not_json_writes_nothing(transcript: str, cache_dir: Path, tmp_path: Path):
    """A render that fails on text that is not JSON writes no page."""
    with pytest.raises(OutlineSyntaxError):
        render_mindmap(transcript, "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


# Shape and nesting problems


def test_unknown_type_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path):
    """A node of an unknown type fails the check, named by its label path."""
    outline = lecture(node("definition", "Gauss"))
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_part_of_the_wrong_kind_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path):
    """A part of the wrong kind, such as stamps given as one string, fails the check."""
    outline = lecture({**term(), "stamps": "0:01"})
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


@pytest.mark.parametrize("slide", ["2", 2.5, True], ids=["text", "fraction", "boolean"])
def test_slide_number_that_is_not_an_integer_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path, slide):
    """A Slide number that is not an integer is a part of the wrong kind."""
    outline = lecture(term(slides=[slide]))
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_missing_part_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path):
    """A node missing one of its type's parts, even one that may be empty, fails the check."""
    outline = lecture({key: value for key, value in term().items() if key != "explanation"})
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_part_the_type_does_not_have_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path):
    """An exempel with an explanation fails the check, since exempel nodes have no explanation."""
    outline = lecture({**worked("exempel", "Rad gånger kolonn"), "explanation": ""})
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Rad gånger kolonn")]


def test_misspelled_part_is_a_problem_of_its_own(transcript: str, cache_dir: Path, tmp_path: Path):
    """A term whose explanation key is misspelled fails for the unknown key and for the missing explanation."""
    parts = {key: value for key, value in term().items() if key != "explanation"}
    outline = lecture({**parts, "explenation": "En metod."})
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Gauss"), (*PATH, "Gauss")]


@pytest.mark.parametrize("kind", ["exempel", "övning"])
@pytest.mark.parametrize(
    "children",
    [[], [worked("exempel", "Inre")], [worked("övning", "Inre")], [term("Inre")]],
    ids=["empty", "exempel", "övning", "term"],
)
def test_children_on_an_exempel_or_ovning_is_one_problem(
    transcript: str, cache_dir: Path, tmp_path: Path, kind: str, children: list
):
    """An exempel or övning with a `children` part fails once, whatever the list holds, so nothing nests under one."""
    outline = lecture({**worked(kind, "Rad gånger kolonn"), "children": children})
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Rad gånger kolonn")]


def test_blank_label_is_a_problem_named_by_position(transcript: str, cache_dir: Path, tmp_path: Path):
    """A node with a blank label fails the check, and its path names it by its position among its siblings."""
    outline = lecture(term("Gauss"), term("   "))
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "#2")]


def test_blank_task_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path):
    """An exempel with a blank task fails the check."""
    outline = lecture(worked("exempel", "Rad gånger kolonn", task=" "))
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Rad gånger kolonn")]


def test_blank_calculation_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path):
    """An övning with a step whose calculation is blank fails the check."""
    outline = lecture(worked("övning", "Rad gånger kolonn", steps=(("", "subtrahera 1"),)))
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [(*PATH, "Rad gånger kolonn")]


@pytest.mark.parametrize(
    "outline, path",
    [
        (node("main-topic", "Matriser", node("topic", "Rader", term())), ("Matriser", "Rader", "Gauss")),
        (node("main-topic", "Matriser", node("slide", "Slide 1")), ("Matriser", "Slide 1")),
        (lecture(node("topic", "Kolonner")), (*PATH, "Kolonner")),
        (lecture(term("Gauss", term("Pivot"))), (*PATH, "Gauss", "Pivot")),
        (node("main-topic", "Matriser", node("main-topic", "Vektorer")), ("Matriser", "Vektorer")),
    ],
    ids=["term-under-topic", "slide-under-main-topic", "topic-under-slide", "term-under-term", "nested-main-topic"],
)
def test_node_under_the_wrong_parent_type_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path, outline, path):
    """A node under a parent type the nesting rules do not allow fails the check."""
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [path]


def test_root_of_another_type_is_a_problem_at_the_root(transcript: str, cache_dir: Path, tmp_path: Path):
    """An Outline whose root is a topic fails the check with a problem at the root."""
    assert problem_paths(transcript, node("topic", "Rader"), cache_dir, tmp_path) == [()]


def test_root_that_is_a_list_is_a_problem_at_the_root(transcript: str, cache_dir: Path, tmp_path: Path):
    """An Outline whose root is a list of main topics fails the check with a problem at the root."""
    outline = json.dumps([node("main-topic", "Matriser"), node("main-topic", "Vektorer")])
    assert problem_paths(transcript, outline, cache_dir, tmp_path) == [()]


@pytest.mark.parametrize(
    "outline",
    [
        lecture(term("Gauss\x0celimination")),
        lecture(worked("exempel", "Bråk", task="Förenkla \x0crac{2}{4}")),
        lecture(worked("exempel", "Bråk", steps=(("2 \times 2", ""),))),
        lecture(worked("exempel", "Bråk", steps=(("2 + 2", "\x08eta saknas"),))),
        lecture(worked("exempel", "Bråk", answer="x \neq 0")),
    ],
    ids=["label", "task", "calculation", "reason", "answer"],
)
def test_control_character_outside_an_explanation_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path, outline):
    """A control character, what JSON makes of an unescaped LaTeX backslash, fails the check in any part but an explanation."""
    assert len(problem_paths(transcript, outline, cache_dir, tmp_path)) == 1


# Stamp and Slide number problems


def test_malformed_stamp_is_a_problem(five_second_transcript: str, cache_dir: Path, tmp_path: Path):
    """A malformed stamp fails the check, named by its node's label path."""
    outline = lecture(term(stamps=["1:75"]))
    assert problem_paths(five_second_transcript, outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_stamp_past_the_source_end_is_a_problem(five_second_transcript: str, cache_dir: Path, tmp_path: Path):
    """A stamp later than the Source's end fails the check."""
    outline = lecture(term(stamps=["0:06"]))
    assert problem_paths(five_second_transcript, outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_slide_number_below_one_is_a_problem(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide number of 0 fails the check."""
    outline = lecture(term(slides=[0]))
    assert problem_paths(slides_transcript[0], outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_slide_number_past_the_deck_end_is_a_problem(slides_transcript, cache_dir: Path, tmp_path: Path):
    """A Slide number past the attached Deck's last Slide fails the check."""
    outline = lecture(term(slides=[4]))
    assert problem_paths(slides_transcript[0], outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_slide_number_listed_twice_on_one_node_is_a_problem(slides_transcript, cache_dir: Path, tmp_path: Path):
    """The same Slide number twice on one node fails the check."""
    outline = lecture(term(slides=[2, 2]))
    assert problem_paths(slides_transcript[0], outline, cache_dir, tmp_path) == [(*PATH, "Gauss")]


def test_slide_number_without_a_deck_is_a_problem(transcript: str, cache_dir: Path, tmp_path: Path):
    """Any Slide number fails the check when the Transcript has no Deck."""
    assert problem_paths(transcript, lecture(slides=[1]), cache_dir, tmp_path) == [PATH]


def test_deck_render_stamp_is_a_problem(standalone_deck, cache_dir: Path, tmp_path: Path):
    """Any stamp in an Outline rendered against a standalone Deck fails the check, since there is no Source."""
    with pytest.raises(OutlineStructureError) as caught:
        render_deck_mindmap(
            standalone_deck.deck_id, lecture(term(stamps=["0:01"])), cache_dir=cache_dir, output_dir=tmp_path
        )
    assert [problem.path for problem in caught.value.problems] == [(*PATH, "Gauss")]


def test_deck_render_slide_past_the_deck_end_is_a_problem(standalone_deck, cache_dir: Path, tmp_path: Path):
    """A Slide number past the standalone Deck's last Slide fails the check."""
    with pytest.raises(OutlineStructureError) as caught:
        render_deck_mindmap(standalone_deck.deck_id, lecture(term(slides=[4])), cache_dir=cache_dir, output_dir=tmp_path)
    assert [problem.path for problem in caught.value.problems] == [(*PATH, "Gauss")]


# Every problem, at once


def bad_lecture() -> dict:
    """An Outline with three bad nodes, each wrong in one way: a missing part, a blank task and a malformed stamp."""
    missing = {key: value for key, value in term("Pivot").items() if key != "slides"}
    return lecture(missing, worked("exempel", "Rad gånger kolonn", task=""), term("Gauss", stamps=["1:75"]))


BAD_PATHS = [(*PATH, "Pivot"), (*PATH, "Rad gånger kolonn"), (*PATH, "Gauss")]


def test_every_problem_is_listed(five_second_transcript: str, cache_dir: Path, tmp_path: Path):
    """The check lists every problem it finds, shape and stamp problems together, not just the first."""
    assert sorted(problem_paths(five_second_transcript, bad_lecture(), cache_dir, tmp_path)) == sorted(BAD_PATHS)


def test_problems_follow_outline_order(five_second_transcript: str, cache_dir: Path, tmp_path: Path):
    """Problems come in Outline order."""
    assert problem_paths(five_second_transcript, bad_lecture(), cache_dir, tmp_path) == BAD_PATHS


def test_structure_error_message_names_each_problem_path(five_second_transcript: str, cache_dir: Path, tmp_path: Path):
    """The error's message gives each problem's label path joined by ` › `."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(five_second_transcript, bad_lecture(), cache_dir=cache_dir, output_dir=tmp_path)
    assert all(" › ".join(path) in str(caught.value) for path in BAD_PATHS)


def test_structure_error_message_ends_pointing_at_the_schema_tool(transcript: str, cache_dir: Path, tmp_path: Path):
    """The error's message ends by telling the LLM to call `get_outline_schema`."""
    with pytest.raises(OutlineStructureError) as caught:
        render_mindmap(transcript, lecture(node("definition", "Gauss")), cache_dir=cache_dir, output_dir=tmp_path)
    assert "get_outline_schema" in str(caught.value).splitlines()[-1]


def test_outline_with_problems_writes_nothing(transcript: str, cache_dir: Path, tmp_path: Path):
    """A render that fails the check writes no page."""
    with pytest.raises(OutlineStructureError):
        render_mindmap(transcript, lecture(node("definition", "Gauss")), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_unknown_transcript_is_raised_before_the_outline_is_read(cache_dir: Path, tmp_path: Path):
    """An unknown Transcript ID raises `UnknownTranscriptError` even when the Outline is not JSON."""
    with pytest.raises(UnknownTranscriptError):
        render_mindmap(UNKNOWN_ID, "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path)


def test_unknown_deck_is_raised_before_the_outline_is_read(cache_dir: Path, tmp_path: Path):
    """An unknown Deck ID raises `UnknownDeckError` even when the Outline is not JSON."""
    with pytest.raises(UnknownDeckError):
        render_deck_mindmap(UNKNOWN_ID, "# Matriser\n", cache_dir=cache_dir, output_dir=tmp_path)


# The MCP server


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def tool_description(server, name: str) -> str:
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    return next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)


def prompt_text(server, name: str, arguments: dict) -> str:
    async def run():
        async with Client(server) as client:
            return await client.get_prompt(name, arguments)

    return asyncio.run(run()).messages[0].content.text


PROMPTS = [
    ("lecture_to_mindmap", {"source": "/tmp/lecture.m4a"}),
    ("lecture_to_mindmap", {"source": "/tmp/lecture.m4a", "deck": "/tmp/matriser.pdf"}),
    ("lecture_to_mindmap", {"deck": "/tmp/matriser.pdf"}),
    ("slides_to_mindmap", {"deck": "/tmp/matriser.pdf"}),
]
PROMPT_IDS = ["source", "source-and-deck", "deck-only", "slides-to-mindmap"]


def test_mcp_get_outline_schema_returns_schema_and_samples(cache_dir: Path):
    """The `get_outline_schema` tool returns an object with `schema` and `samples`."""
    result = call(create_server(cache_dir=cache_dir), "get_outline_schema", {})
    assert set(result.structured_content) == {"schema", "samples"}


def test_mcp_render_mindmap_accepts_an_outline_object(transcript: str, cache_dir: Path, tmp_path: Path):
    """The `render_mindmap` tool takes the Outline as a JSON object and writes the page."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path)
    result = call(server, "render_mindmap", {"transcript_id": transcript, "outline": lecture(term())})
    assert Path(result.structured_content["page"]).is_file()


def test_mcp_render_mindmap_accepts_outline_text(transcript: str, cache_dir: Path, tmp_path: Path):
    """The `render_mindmap` tool takes the Outline as JSON text and writes the page."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path)
    result = call(server, "render_mindmap", {"transcript_id": transcript, "outline": json.dumps(lecture(term()))})
    assert Path(result.structured_content["page"]).is_file()


def test_mcp_render_mindmap_returns_only_the_page(transcript: str, cache_dir: Path, tmp_path: Path):
    """The `render_mindmap` tool returns the page and nothing else."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path)
    result = call(server, "render_mindmap", {"transcript_id": transcript, "outline": lecture(term())})
    assert set(result.structured_content) == {"page"}


def test_mcp_render_deck_mindmap_accepts_an_outline_object(standalone_deck, cache_dir: Path, tmp_path: Path):
    """The `render_deck_mindmap` tool takes the Outline as a JSON object and writes the page."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path)
    result = call(server, "render_deck_mindmap", {"deck_id": standalone_deck.deck_id, "outline": lecture(term())})
    assert Path(result.structured_content["page"]).is_file()


def test_mcp_markdown_outline_error_points_at_the_schema_tool(transcript: str, cache_dir: Path, tmp_path: Path):
    """The tool error for a Markdown Outline tells the LLM to call `get_outline_schema`."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path)
    result = call(server, "render_mindmap", {"transcript_id": transcript, "outline": "# Matriser\n## Rader\n"})
    assert "get_outline_schema" in result.content[0].text


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_mcp_render_description_points_at_the_schema_tool(cache_dir: Path, tool: str):
    """Both render tool descriptions tell the LLM to call `get_outline_schema` before writing an Outline."""
    assert "get_outline_schema" in tool_description(create_server(cache_dir=cache_dir), tool)


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_mcp_render_description_describes_no_markdown_format(cache_dir: Path, tool: str):
    """Neither render tool description describes a Markdown Outline any more."""
    assert "Markdown" not in tool_description(create_server(cache_dir=cache_dir), tool)


@pytest.mark.parametrize("name, arguments", PROMPTS, ids=PROMPT_IDS)
def test_mcp_prompt_points_at_the_schema_tool(cache_dir: Path, name: str, arguments: dict):
    """Every prompt variant has the LLM call `get_outline_schema`."""
    assert "get_outline_schema" in prompt_text(create_server(cache_dir=cache_dir), name, arguments)


@pytest.mark.parametrize("name, arguments", PROMPTS, ids=PROMPT_IDS)
def test_mcp_prompt_asks_for_a_json_outline(cache_dir: Path, name: str, arguments: dict):
    """Every prompt variant asks for the Outline as JSON."""
    assert "JSON" in prompt_text(create_server(cache_dir=cache_dir), name, arguments)


# The page


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
def render_url(transcript: str, cache_dir: Path, tmp_path: Path):
    """Render an Outline into a folder of its own and return the page's URL with every node shown."""

    def render(outline: dict, name: str = "mindmap") -> str:
        page = render_mindmap(transcript, outline, cache_dir=cache_dir, output_dir=tmp_path / name).page
        return f"{page.as_uri()}?depth=all"

    return render


def is_orange(colour: str) -> bool:
    red, green, blue = (int(part) / 255 for part in re.findall(r"\d+", colour)[:3])
    hue, _, saturation = colorsys.rgb_to_hls(red, green, blue)
    return ORANGE_HUES[0] <= hue * 360 <= ORANGE_HUES[1] and saturation >= MIN_ORANGE_SATURATION


def group_colours(page) -> dict[str, str]:
    """Each visible node's group colour as `rgb(r, g, b)`, keyed by the label its card shows."""
    return dict(
        page.locator(".node").evaluate_all(
            "elements => elements.map(element => {"
            "const probe = document.createElement('span');"
            "probe.style.color = getComputedStyle(element.querySelector('.node-shell'))"
            ".getPropertyValue('--group');"
            "document.body.append(probe);"
            "const colour = getComputedStyle(probe).color;"
            "probe.remove();"
            "return [element.querySelector('.node-label').textContent, colour];})"
        )
    )


def edge_colours(page) -> list[str]:
    return page.locator(".edge").evaluate_all("edges => edges.map(edge => getComputedStyle(edge).stroke)")


def card_labels(page) -> list[str]:
    return page.locator(".node-label").all_text_contents()


def click_card(page, text: str) -> None:
    """Open the panel of the node whose card label ends with this text."""
    page.locator(".node-label").filter(has_text=re.compile(f"{re.escape(text)}$")).dispatch_event("click")


@pytest.mark.parametrize("kind, prefix", [("exempel", "Exempel: "), ("övning", "Övning: ")])
def test_exempel_and_ovning_are_orange_by_type(page, render_url, kind: str, prefix: str):
    """An exempel or övning node is orange because of its type, though its label has no prefix."""
    page.goto(render_url(lecture(worked(kind, "Rad gånger kolonn"))))
    assert is_orange(group_colours(page)[f"{prefix}Rad gånger kolonn"])


def test_topic_labelled_exempel_is_not_orange(page, render_url):
    """A topic whose label starts with `Exempel:` keeps a topic colour, since only the type makes a node orange."""
    page.goto(render_url(node("main-topic", "Matriser", node("topic", "Exempel: Rader"))))
    assert not is_orange(group_colours(page)["Exempel: Rader"])


def test_edge_into_an_exempel_keeps_its_topic_colour(page, render_url):
    """The edge from a slide node into an exempel is drawn in the topic's colour, not orange."""
    page.goto(render_url(lecture(worked("exempel", "Rad gånger kolonn"))))
    assert not any(is_orange(colour) for colour in edge_colours(page))


def test_edge_from_the_main_topic_into_an_exempel_is_orange(page, render_url):
    """An exempel directly under the main topic has an orange edge, as today."""
    page.goto(render_url(node("main-topic", "Matriser", worked("exempel", "Rad gånger kolonn"))))
    assert all(is_orange(colour) for colour in edge_colours(page))


def test_exempel_under_the_main_topic_takes_no_topic_colour(page, render_url):
    """A topic after an exempel directly under the main topic gets the colour it would have had without it."""
    page.goto(render_url(node("main-topic", "Matriser", node("topic", "Rader")), "alone"))
    alone = group_colours(page)["Rader"]
    after = node("main-topic", "Matriser", worked("exempel", "Rad gånger kolonn"), node("topic", "Rader"))
    page.goto(render_url(after, "after"))
    assert group_colours(page)["Rader"] == alone


@pytest.mark.parametrize("kind, prefix", [("exempel", "Exempel: "), ("övning", "Övning: ")])
def test_map_card_shows_the_type_prefix(page, render_url, kind: str, prefix: str):
    """The map card shows `Exempel: ` or `Övning: ` before the label."""
    page.goto(render_url(lecture(worked(kind, "Rad gånger kolonn"))))
    assert f"{prefix}Rad gånger kolonn" in card_labels(page)


def test_card_aria_label_shows_the_type_prefix(page, render_url):
    """The card's aria-label names the node with its prefix."""
    page.goto(render_url(lecture(worked("exempel", "Rad gånger kolonn"))))
    assert page.get_by_role("button", name="Explore Exempel: Rad gånger kolonn", exact=True).count() == 1


@pytest.mark.parametrize("kind, prefix", [("exempel", "Exempel: "), ("övning", "Övning: ")])
def test_panel_title_shows_the_type_prefix(page, render_url, kind: str, prefix: str):
    """The panel title shows `Exempel: ` or `Övning: ` before the label."""
    page.goto(render_url(lecture(worked(kind, "Rad gånger kolonn"))))
    click_card(page, "Rad gånger kolonn")
    assert page.locator("#panel-title").text_content() == f"{prefix}Rad gånger kolonn"


def test_explore_next_button_shows_the_type_prefix(page, render_url):
    """The Explore next button for an exempel, in its parent's panel, shows the prefix."""
    page.goto(render_url(lecture(worked("exempel", "Rad gånger kolonn"))))
    click_card(page, "Slide 1")
    assert "Exempel: Rad gånger kolonn" in page.locator("#related button").all_text_contents()


def test_exempel_panel_shows_task_steps_and_answer(page, render_url):
    """An exempel's panel shows its task, one `Steg N:` line per step with any reason, then `Svar:` and the answer."""
    example = worked(
        "exempel",
        "Rad gånger kolonn",
        task="Lös x + 1 = 2",
        steps=(("x = 2 - 1", "subtrahera 1"), ("x = 1", "")),
        answer="x = 1",
    )
    page.goto(render_url(lecture(example)))
    click_card(page, "Rad gånger kolonn")
    assert page.locator("#explanation").inner_text().splitlines() == [
        "Lös x + 1 = 2",
        "Steg 1: x = 2 - 1 (subtrahera 1)",
        "Steg 2: x = 1",
        "Svar: x = 1",
    ]


def test_exempel_panel_with_no_steps_or_answer_shows_only_the_task(page, render_url):
    """An exempel with no steps and no answer shows only its task."""
    page.goto(render_url(lecture(worked("exempel", "Rad gånger kolonn", task="Lös x + 1 = 2", steps=(), answer=""))))
    click_card(page, "Rad gånger kolonn")
    assert page.locator("#explanation").inner_text().splitlines() == ["Lös x + 1 = 2"]


def two_slides(first: dict, second: dict, *more_slides: dict) -> dict:
    """Topic A with slide Definition holding `first`, and topic B with slide Räkning holding `second`, then `more_slides`."""
    return node(
        "main-topic",
        "Matriser",
        node("topic", "A", node("slide", "Definition", first)),
        node("topic", "B", node("slide", "Räkning", second), *more_slides),
    )


def copy_entries(page) -> list[str]:
    return page.locator("#copies li").all_text_contents()


def test_term_copies_match_by_label_ignoring_case_and_spaces(page, render_url):
    """Term nodes whose labels differ only in case and runs of whitespace are listed as copies of one term."""
    page.goto(render_url(two_slides(term("Rad gånger kolonn"), term("rad  gånger kolonn"))))
    page.locator(".node-label").filter(has_text=re.compile("^Rad gånger kolonn$")).dispatch_event("click")
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]


def test_only_term_nodes_count_as_copies(page, render_url):
    """A slide node labelled like a term is not listed among the term's copies."""
    outline = two_slides(term("Matrisprodukt"), term("Matrisprodukt"), node("slide", "Matrisprodukt"))
    page.goto(render_url(outline))
    page.locator(".node-label").filter(has_text=re.compile("^Matrisprodukt$")).first.dispatch_event("click")
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]
