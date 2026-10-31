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

NODE_TYPES = ["main-topic", "topic", "slide", "term", "exempel", "övning"]


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


@pytest.mark.parametrize("kind", NODE_TYPES)
def test_schema_names_every_node_type(kind: str):
    """The schema names each of the six node types."""
    assert f'"{kind}"' in json.dumps(get_outline_schema().schema, ensure_ascii=False)


def test_samples_are_an_exempel_then_an_ovning():
    """The samples are an exempel node first and an övning node second."""
    assert [sample["type"] for sample in get_outline_schema().samples] == ["exempel", "övning"]


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_sample_task_carries_latex_between_dollars(index: int):
    """Each sample's task is prose with LaTeX between `$...$`."""
    assert re.search(r"\$[^$]*\\[^$]*\$", get_outline_schema().samples[index]["task"])


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_sample_steps_carry_latex(index: int):
    """At least one of each sample's steps carries LaTeX in its calculation."""
    assert any("\\" in step["calculation"] for step in get_outline_schema().samples[index]["steps"])


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_sample_calculations_carry_no_dollars(index: int):
    """A step's calculation is LaTeX alone, so no sample calculation holds a `$`."""
    assert not any("$" in step["calculation"] for step in get_outline_schema().samples[index]["steps"])


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_sample_answer_carries_latex_between_dollars(index: int):
    """Each sample's answer holds LaTeX between `$...$`."""
    assert re.search(r"\$[^$]*\\[^$]*\$", get_outline_schema().samples[index]["answer"])


@pytest.mark.parametrize("index", [0, 1], ids=["exempel", "övning"])
def test_sample_renders_under_a_slide_node(transcript_id: str, cache_dir: Path, tmp_path: Path, index: int):
    """Each sample, placed under a slide node, passes the check and renders."""
    outline = under_a_slide_node(get_outline_schema().samples[index])
    assert render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path).page.is_file()
