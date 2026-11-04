import asyncio
import colorsys
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
    read_deck,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

WORKED_TYPES = ["example", "exercise"]
OLD_TYPES = ["exempel", "övning"]
TREE_TYPES = ["main-topic", "topic", "slide", "term"]
TREE_LABELS = ["Matriser", "Rader", "Slide 1", "Gauss"]
PREFIXES = [("example", "Exempel: "), ("exercise", "Övning: ")]
LABEL = "Rad gånger kolonn"
UNDER_A_SLIDE = (*TREE_LABELS[:3], LABEL)
ORANGE_HUES = (25, 45)
MIN_ORANGE_SATURATION = 0.5
GAUSS_OUTLINE = Path(__file__).resolve().parents[1] / "docs/examples/gauss-sats-outline.json"


def node(kind: str, label: str, *children: dict) -> dict:
    """A node of a type with children, with every other part empty."""
    return {"type": kind, "label": label, "explanation": "", "stamps": [], "slides": [], "children": list(children)}


def worked(kind: str, label: str = LABEL, **parts) -> dict:
    """A node of a worked type with a task and every other part empty, or as `parts` gives them."""
    return {"type": kind, "label": label, "stamps": [], "slides": [], "task": "Lös uppgiften", "steps": [], "answer": "", **parts}


def under(parent: str, child: dict) -> dict:
    """An Outline running from the main topic down to a node of type `parent`, with `child` under that node."""
    depth = TREE_TYPES.index(parent)
    outline = child
    for kind, label in reversed(list(zip(TREE_TYPES[: depth + 1], TREE_LABELS[: depth + 1]))):
        outline = node(kind, label, outline)
    return outline


def labelled(kind: str, label: str) -> tuple[dict, tuple[str, ...]]:
    """An Outline holding a node of type `kind` with this label, and that node's label path."""
    if kind == "main-topic":
        return node(kind, label), (label,)
    if kind in TREE_TYPES:
        depth = TREE_TYPES.index(kind)
        return under(TREE_TYPES[depth - 1], node(kind, label)), (*TREE_LABELS[:depth], label)
    return under("slide", worked(kind, label)), (*TREE_LABELS[:3], label)


def one_sentence(wav: Path, vocabulary: object) -> list[Fragment]:
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


@pytest.fixture
def transcript_id(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


@pytest.fixture
def render(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """Render an Outline and return the page's path."""
    return lambda outline: render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out").page


@pytest.fixture
def problems(render):
    """Render an Outline that must fail the check, and return each problem as (path, message)."""

    def run(outline: dict) -> list[tuple[tuple[str, ...], str]]:
        with pytest.raises(OutlineStructureError) as caught:
            render(outline)
        return [(problem.path, problem.message) for problem in caught.value.problems]

    return run


# The schema and samples offer the new names


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_schema_offers_the_new_type(kind: str):
    """The Outline schema defines a node type under the new name."""
    assert kind in get_outline_schema().schema["$defs"]


@pytest.mark.parametrize("kind", OLD_TYPES)
def test_schema_no_longer_offers_the_old_type(kind: str):
    """The Outline schema defines no node type under the old name."""
    assert kind not in get_outline_schema().schema["$defs"]


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_schema_gives_the_new_type_the_worked_parts(kind: str):
    """The schema gives a worked type its task, steps and answer, and no explanation or children."""
    required = get_outline_schema().schema["$defs"][kind]["required"]
    assert set(required) == {"type", "label", "stamps", "slides", "task", "steps", "answer"}


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize("parent", TREE_TYPES)
def test_schema_lets_the_new_type_sit_under_every_tree_type(kind: str, parent: str):
    """The schema offers a worked type among the children of each of the four tree types."""
    children = get_outline_schema().schema["$defs"][parent]["properties"]["children"]["items"]["oneOf"]
    assert {"$ref": f"#/$defs/{kind}"} in children


def test_samples_are_an_example_then_an_exercise():
    """The schema's samples are an example node, then an exercise node."""
    assert [sample["type"] for sample in get_outline_schema().samples] == WORKED_TYPES


# The tool descriptions the LLM reads use the new names


def tool_description(server, name: str) -> str:
    """Return a tool's description with every run of whitespace collapsed to one space."""

    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    description = next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)
    return " ".join(description.split())


@pytest.mark.parametrize("tool", ["get_outline_schema", "render_mindmap", "render_deck_mindmap"])
def test_tool_description_drops_the_old_type_names(cache_dir: Path, tool: str):
    """No Outline tool's description names `exempel` or `övning` as a type. The capitalised label prefixes may stay."""
    description = tool_description(create_server(cache_dir=cache_dir), tool)
    assert not re.search(r"\b(exempel|övning)\b", description)


@pytest.mark.parametrize("tool", ["render_mindmap", "render_deck_mindmap"])
def test_render_description_asks_for_the_new_types(cache_dir: Path, tool: str):
    """Both render tools ask for each example and exercise as a node of the new types."""
    assert "as an example or exercise node" in tool_description(create_server(cache_dir=cache_dir), tool)


# The check applies the same parts and nesting rules


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize("parent", TREE_TYPES)
def test_new_type_renders_under_every_tree_type(render, kind: str, parent: str):
    """A worked node renders under a main-topic, topic, slide or term node."""
    assert render(under(parent, worked(kind))).exists()


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_new_type_with_steps_and_answer_renders(render, kind: str):
    """A worked node with steps and an answer renders."""
    steps = [{"calculation": "x = 1", "reason": "subtrahera 1"}]
    assert render(under("slide", worked(kind, steps=steps, answer="$x = 1$"))).exists()


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_new_type_with_an_explanation_is_a_problem(problems, kind: str):
    """A worked node has no explanation part."""
    outline = under("slide", worked(kind, explanation=""))
    assert problems(outline) == [(UNDER_A_SLIDE, f'{kind} nodes have no "explanation" part')]


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize("nested", WORKED_TYPES)
def test_new_type_with_children_is_one_problem(problems, kind: str, nested: str):
    """A worked node has no children part, so a worked node cannot sit under one, and the nodes in it go unchecked."""
    outline = under("slide", worked(kind, children=[worked(nested, "Inre")]))
    assert problems(outline) == [(UNDER_A_SLIDE, f'{kind} nodes have no "children" part')]


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_new_type_missing_its_task_is_a_problem(problems, kind: str):
    """A worked node must carry a task."""
    child = worked(kind)
    del child["task"]
    assert problems(under("slide", child)) == [(UNDER_A_SLIDE, "missing task")]


@pytest.mark.parametrize("kind", WORKED_TYPES)
def test_new_type_with_a_blank_task_is_a_problem(problems, kind: str):
    """A worked node's task must be non-blank."""
    assert problems(under("slide", worked(kind, task="  "))) == [(UNDER_A_SLIDE, "task is blank")]


# The old names and the label prefixes fail the render


@pytest.mark.parametrize("kind", OLD_TYPES)
def test_old_type_fails_the_render_named_by_its_label_path(problems, kind: str):
    """A node of an old type is one unknown-type problem, named by its path of labels."""
    assert problems(under("slide", worked(kind))) == [(UNDER_A_SLIDE, f'unknown type "{kind}"')]


@pytest.mark.parametrize("kind", OLD_TYPES)
def test_old_type_fails_the_deck_render(deck: Path, cache_dir: Path, tmp_path: Path, kind: str):
    """A node of an old type fails a render against a standalone Deck too."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    with pytest.raises(OutlineStructureError) as caught:
        render_deck_mindmap(deck_id, under("slide", worked(kind)), cache_dir=cache_dir, output_dir=tmp_path / "out")
    assert [problem.message for problem in caught.value.problems] == [f'unknown type "{kind}"']


@pytest.mark.parametrize("kind", [*TREE_TYPES, *WORKED_TYPES])
@pytest.mark.parametrize(
    "label, prefix",
    [
        ("Exempel: Gauss", "Exempel:"),
        ("EXEMPEL: Gauss", "Exempel:"),
        ("exempel : Gauss", "Exempel:"),
        ("Övning: Gauss", "Övning:"),
        ("ÖVNING: Gauss", "Övning:"),
        ("övning : Gauss", "Övning:"),
    ],
)
def test_swedish_label_prefix_fails_the_render_on_any_node(problems, kind: str, label: str, prefix: str):
    """A label starting with `Exempel:` or `Övning:`, in any case, fails on any node, and says to use a worked node."""
    outline, path = labelled(kind, label)
    message = f'label starts with "{prefix}"; use an example or exercise node and leave the prefix out, since the page adds it'
    assert problems(outline) == [(path, message)]


@pytest.mark.parametrize("kind", WORKED_TYPES)
@pytest.mark.parametrize("label", ["Example: Gauss", "Exercise: Gauss"])
def test_english_label_prefix_still_passes(render, kind: str, label: str):
    """Only the Swedish prefixes are banned, so a worked node labelled `Example:` or `Exercise:` renders."""
    assert render(under("slide", worked(kind, label))).exists()


# The Outline shipped as an example uses the new names


def test_gauss_example_outline_writes_its_exercises_with_the_new_type():
    """The Gauss example Outline's two worked nodes are of type `exercise`."""

    def types(outline: dict) -> list[str]:
        return [outline["type"]] + [kind for child in outline.get("children", []) for kind in types(child)]

    found = types(json.loads(GAUSS_OUTLINE.read_text(encoding="utf-8")))
    assert [kind for kind in found if kind not in TREE_TYPES] == ["exercise", "exercise"]


# The page looks as it did under the old names


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


def show_every_node(page, path: Path) -> None:
    page.goto(f"{path.as_uri()}?depth=all")


def card_labels(page) -> list[str]:
    return page.locator(".node-label").all_text_contents()


def is_orange(colour: str) -> bool:
    red, green, blue = (int(part) / 255 for part in re.findall(r"\d+", colour)[:3])
    hue, _, saturation = colorsys.rgb_to_hls(red, green, blue)
    return ORANGE_HUES[0] <= hue * 360 <= ORANGE_HUES[1] and saturation >= MIN_ORANGE_SATURATION


def group_colours(page) -> dict[str, str]:
    """Each visible node's group colour as `rgb(r, g, b)`, keyed by label."""
    return dict(
        page.locator(".node").evaluate_all(
            "elements => elements.map(element => {"
            "const probe = document.createElement('span');"
            "probe.style.color = getComputedStyle(element.querySelector('.node-shell'))"
            ".getPropertyValue('--group');"
            "document.body.append(probe);"
            "const colour = getComputedStyle(probe).color; probe.remove();"
            "return [element.querySelector('.node-label').textContent, colour];})"
        )
    )


@pytest.mark.parametrize("kind, prefix", PREFIXES)
def test_page_paints_the_new_type_orange(page, render, kind: str, prefix: str):
    """The page paints a worked node orange."""
    show_every_node(page, render(under("slide", worked(kind))))
    assert is_orange(group_colours(page)[f"{prefix}{LABEL}"])


@pytest.mark.parametrize("kind, prefix", PREFIXES)
def test_page_puts_the_swedish_prefix_on_the_new_type(page, render, kind: str, prefix: str):
    """The page shows `Exempel: ` or `Övning: ` before a worked node's label."""
    show_every_node(page, render(under("slide", worked(kind))))
    assert f"{prefix}{LABEL}" in card_labels(page)


@pytest.mark.parametrize(
    "label, heading",
    [("Första", "Exempel 1"), ("Andra", "Exempel 2"), ("Tredje", "Övning 1")],
    ids=["first-example", "second-example", "first-exercise"],
)
def test_box_heading_stays_swedish_and_counts_each_type_separately(page, render, label: str, heading: str):
    """A worked node's box is headed `Exempel N` or `Övning N`, counting each type separately in Outline order."""
    outline = node(
        "main-topic",
        TREE_LABELS[0],
        node(
            "topic",
            TREE_LABELS[1],
            node(
                "slide",
                TREE_LABELS[2],
                worked("example", "Första"),
                worked("example", "Andra"),
                worked("exercise", "Tredje"),
            ),
        ),
    )
    show_every_node(page, render(outline))
    page.locator(".node-label").filter(has_text=re.compile(f"{label}$")).dispatch_event("click")
    assert page.locator("#panel #worked").get_by_role("heading").text_content() == heading


@pytest.mark.parametrize("kind, title", [("example", "Exempel"), ("exercise", "Övning")])
def test_panel_label_stays_swedish(page, render, kind: str, title: str):
    """A worked node's panel labels its text `Exempel` or `Övning`."""
    show_every_node(page, render(under("slide", worked(kind))))
    page.locator(".node-label").filter(has_text=re.compile(f"{LABEL}$")).dispatch_event("click")
    assert page.locator(".explanation-label").text_content() == title
