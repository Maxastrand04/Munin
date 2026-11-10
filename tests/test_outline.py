import json
import re
from pathlib import Path

import pytest

from munin.core import (
    Fragment,
    Vocabulary,
    get_outline_schema,
    render_mindmap,
    transcribe,
)

TREE_TYPES = ["main-topic", "topic", "slide", "term"]
WORKED_TYPES = ["example", "exercise"]
SWEDISH_LETTERS = re.compile("[åäöÅÄÖ]")


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


@pytest.fixture
def transcript_id(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def node(kind: str, label: str, *children: dict) -> dict:
    """A node of a type with children, with every other part empty."""
    return {"type": kind, "label": label, "explanation": "", "stamps": [], "slides": [], "children": list(children)}


def under_a_slide_node(child: dict) -> dict:
    """The main topic Matriser, one topic Rader, one slide node Slide 1, and `child` under it."""
    return node("main-topic", "Matriser", node("topic", "Rader", node("slide", "Slide 1", child)))


def test_schema_is_json_schema_draft_2020_12():
    """The schema is a JSON Schema of draft 2020-12."""
    assert get_outline_schema().schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_schema_description_puts_reason_math_between_dollars():
    """The schema's description says a step's reason is prose with math between `$...$`."""
    assert re.search(r"reason[^.]*\$\.\.\.\$", get_outline_schema().schema["description"], re.IGNORECASE)


def test_schema_description_keeps_a_step_to_one_object():
    """The schema's description asks for a step about one object (#67)."""
    assert "one object" in get_outline_schema().schema["description"]


def test_schema_description_never_repeats_a_fact():
    """The schema's description asks for no fact written twice (#67)."""
    assert "no fact twice" in get_outline_schema().schema["description"]


def test_schema_description_keeps_steps_in_source_order():
    """The schema's description asks for steps in the order the source gives them (#67)."""
    assert "in the order the source gives them" in get_outline_schema().schema["description"]


def test_schema_description_forbids_double_dollars():
    """The schema's description tells the LLM never to write `$$`."""
    assert "$$" in get_outline_schema().schema["description"]


def test_schema_description_asks_for_the_lectures_language():
    """The schema's description asks for the Outline in the lecture's language."""
    assert "the lecture's language" in get_outline_schema().schema["description"]


def test_schema_description_names_no_swedish():
    """The schema's description does not ask for Swedish."""
    assert "Swedish" not in get_outline_schema().schema["description"]


@pytest.mark.parametrize("kind", [*TREE_TYPES, *WORKED_TYPES])
def test_schema_defines_every_node_type(kind: str):
    """The schema defines each of the six node types."""
    assert kind in get_outline_schema().schema["$defs"]


@pytest.mark.parametrize("kind", ["exempel", "övning"])
def test_schema_defines_no_swedish_node_type(kind: str):
    """The schema defines no node type under a Swedish name."""
    assert kind not in get_outline_schema().schema["$defs"]


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_schema_gives_an_example_or_exercise_its_parts(kind: str):
    """The schema gives an example or exercise its task, steps and answer, and no explanation or children."""
    required = get_outline_schema().schema["$defs"][kind]["required"]
    assert set(required) == {"type", "label", "stamps", "slides", "task", "steps", "answer"}


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize("parent", TREE_TYPES)
def test_schema_lets_an_example_or_exercise_sit_under_every_other_type(kind: str, parent: str):
    """The schema offers an example or exercise among the children of each of the four other types."""
    children = get_outline_schema().schema["$defs"][parent]["properties"]["children"]["items"]["oneOf"]
    assert {"$ref": f"#/$defs/{kind}"} in children


def test_samples_are_an_example_then_an_exercise():
    """The samples are an example node first and an exercise node second."""
    assert [sample["type"] for sample in get_outline_schema().samples] == WORKED_TYPES


def test_example_sample_is_written_in_swedish():
    """The example sample is written in Swedish, so its text holds a Swedish letter."""
    example, _ = get_outline_schema().samples
    assert SWEDISH_LETTERS.search(json.dumps(example, ensure_ascii=False))


def test_exercise_sample_is_written_in_english():
    """The exercise sample is written in English, so its text holds no Swedish letter."""
    _, exercise = get_outline_schema().samples
    assert not SWEDISH_LETTERS.search(json.dumps(exercise, ensure_ascii=False))


@pytest.mark.parametrize("index", [0, 1], ids=["example", "exercise"])
def test_sample_task_carries_latex_between_dollars(index: int):
    """Each sample's task is prose with LaTeX between `$...$`."""
    assert re.search(r"\$[^$]*\\[^$]*\$", get_outline_schema().samples[index]["task"])


@pytest.mark.parametrize("index", [0, 1], ids=["example", "exercise"])
def test_sample_steps_carry_latex(index: int):
    """At least one of each sample's steps carries LaTeX in its calculation."""
    assert any("\\" in step["calculation"] for step in get_outline_schema().samples[index]["steps"])


@pytest.mark.parametrize("index", [0, 1], ids=["example", "exercise"])
def test_sample_calculations_carry_no_dollars(index: int):
    """A step's calculation is LaTeX alone, so no sample calculation holds a `$`."""
    assert not any("$" in step["calculation"] for step in get_outline_schema().samples[index]["steps"])


@pytest.mark.parametrize("index", [0, 1], ids=["example", "exercise"])
def test_sample_answer_carries_latex_between_dollars(index: int):
    """Each sample's answer holds LaTeX between `$...$`."""
    assert re.search(r"\$[^$]*\\[^$]*\$", get_outline_schema().samples[index]["answer"])


@pytest.mark.parametrize("index", [0, 1], ids=["example", "exercise"])
def test_sample_renders_under_a_slide_node(transcript_id: str, cache_dir: Path, tmp_path: Path, index: int):
    """Each sample, placed under a slide node, passes the check and renders."""
    outline = under_a_slide_node(get_outline_schema().samples[index])
    assert render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path).page.is_file()
