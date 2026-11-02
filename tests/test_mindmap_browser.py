import colorsys
import json
import math
import re
import wave
from itertools import combinations, pairwise
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munin.core import (
    Fragment,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)

NESTED_OUTLINE = """# Lecture
## Group
### A
#### Leaf A
#### B
##### Exempel: Leaf B
"""
DEMO_OUTLINE = json.loads(
    (Path(__file__).resolve().parents[1] / "docs/examples/matriser-outline.json").read_text(encoding="utf-8")
)
TEN_MINUTES_S = 600
SAMPLE_RATE = 8_000
TYPES_BY_DEPTH = ["main-topic", "topic", "slide", "term"]
WORKED_PREFIXES = {"Exempel: ": "exempel", "Övning: ": "övning"}


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


def worked(kind: str, label: str) -> dict:
    """An exempel or övning node with a task and nothing else."""
    return {"type": kind, "label": label, "stamps": [], "slides": [], "task": "Lös uppgiften", "steps": [], "answer": ""}


def term(label: str, **parts) -> dict:
    return node("term", label, **parts)


def outline_from_headings(headings: str) -> dict:
    """A JSON Outline from one `#` heading per line, where one `#` is the main topic and each more is one level down.

    A heading's depth gives its type, main-topic to term. A heading whose label starts with `Exempel: ` or
    `Övning: ` is that type instead, with the prefix left out of its label, since the page adds it back.
    """
    root, stack = None, []
    for line in headings.splitlines():
        level = len(line) - len(line.lstrip("#"))
        label = line[level:].strip()
        prefix = next((prefix for prefix in WORKED_PREFIXES if label.startswith(prefix)), None)
        current = (
            worked(WORKED_PREFIXES[prefix], label.removeprefix(prefix))
            if prefix
            else node(TYPES_BY_DEPTH[level - 1], label)
        )
        del stack[level - 1:]
        if stack:
            stack[-1]["children"].append(current)
        else:
            root = current
        stack.append(current)
    return root


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
def outline():
    return NESTED_OUTLINE


@pytest.fixture
def ten_minute_source(tmp_path: Path) -> Path:
    """A WAV of 10 minutes of silence, long enough for every stamp in the demo Outline."""
    path = tmp_path / "media" / "ten_minutes.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(bytes(2 * TEN_MINUTES_S * SAMPLE_RATE))
    return path


@pytest.fixture
def render_outline(ten_minute_source: Path, cache_dir: Path, tmp_path: Path):
    """Render an Outline against a 10-minute Source into a folder of its own and return the page's URL."""
    transcript = transcribe(
        ten_minute_source,
        cache_dir=cache_dir,
        recognize=lambda wav, vocabulary: [Fragment(0, 1, "En föreläsning.")],
    )

    def render(outline: str | dict, name: str = "mindmap") -> str:
        """Render an Outline given as a dict, or as headings `outline_from_headings` reads."""
        return render_mindmap(
            transcript.transcript_id,
            outline_from_headings(outline) if isinstance(outline, str) else outline,
            cache_dir=cache_dir,
            output_dir=tmp_path / name,
        ).page.as_uri()

    return render


@pytest.fixture
def mindmap_url(render_outline, outline):
    return render_outline(outline)


def overlapping_pairs(boxes: list[dict]) -> list[tuple[str, str]]:
    return [
        (first["label"], second["label"])
        for first, second in combinations(boxes, 2)
        if not (
            first["x"] + first["width"] <= second["x"]
            or second["x"] + second["width"] <= first["x"]
            or first["y"] + first["height"] <= second["y"]
            or second["y"] + second["height"] <= first["y"]
        )
    ]


def node_boxes(page):
    return page.locator(".node").evaluate_all(
        "elements => elements.map(element => {"
        "const {x, y, width, height} = element.getBoundingClientRect();"
        "return {label: element.querySelector('.node-label').textContent,"
        "x, y, width, height};})"
    )


@pytest.mark.parametrize("style", ["C", "A"], ids=["topic-circles", "radial-rings"])
@pytest.mark.parametrize(
    "outline, node_count", [(NESTED_OUTLINE, 6), (DEMO_OUTLINE, 28)],
    ids=["nested", "demo"],
)
def test_show_whole_mindmap_shows_every_node(page, mindmap_url, style, outline, node_count):
    page.goto(f"{mindmap_url}?variant={style}")
    page.get_by_role("button", name="Show whole Mindmap", exact=True).click()
    assert len(node_boxes(page)) == node_count


@pytest.mark.parametrize("style", ["C", "A"], ids=["topic-circles", "radial-rings"])
@pytest.mark.parametrize("outline", [NESTED_OUTLINE, DEMO_OUTLINE], ids=["nested", "demo"])
def test_expanded_nodes_do_not_overlap(page, mindmap_url, style):
    page.goto(f"{mindmap_url}?variant={style}")
    page.get_by_role("button", name="Show whole Mindmap", exact=True).click()
    assert overlapping_pairs(node_boxes(page)) == []


@pytest.mark.parametrize("style", ["C", "A"], ids=["topic-circles", "radial-rings"])
def test_opening_view_centres_main_topic(page, mindmap_url, style):
    page.goto(f"{mindmap_url}?variant={style}")
    canvas = page.locator("#canvas").bounding_box()
    root = next(box for box in node_boxes(page) if box["label"] == "Lecture")
    assert (root["x"] + root["width"] / 2, root["y"] + root["height"] / 2) == pytest.approx(
        (canvas["x"] + canvas["width"] / 2, canvas["y"] + canvas["height"] / 2),
        abs=1,
    )


@pytest.mark.parametrize("style", ["C", "A"], ids=["topic-circles", "radial-rings"])
def test_expanding_branch_keeps_existing_nodes_in_place(page, mindmap_url, style):
    page.goto(f"{mindmap_url}?variant={style}")
    before = node_boxes(page)
    # The opening zoom may leave A off-screen, and scrolling it into view would move every box.
    page.get_by_role("button", name="Reveal children of A", exact=True).dispatch_event("click")
    after = {box["label"]: box for box in node_boxes(page)}
    assert [box["label"] for box in before if after[box["label"]] != box] == []


MIN_DISTINCT_GROUPS = 14
MANY_GROUPS_OUTLINE = "# Lecture\n" + "".join(
    f"## Group {number}\n" for number in range(1, MIN_DISTINCT_GROUPS + 1)
)


MIN_HUE_GAP = 20


def hue_and_saturation(colour: str) -> tuple[float, float]:
    red, green, blue = (int(part) / 255 for part in re.findall(r"\d+", colour)[:3])
    hue, _, saturation = colorsys.rgb_to_hls(red, green, blue)
    return hue * 360, saturation


def hue(colour: str) -> float:
    return hue_and_saturation(colour)[0]


def hue_gap(first: float, second: float) -> float:
    gap = abs(first - second) % 360
    return min(gap, 360 - gap)


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


def group_hues(page) -> list[float]:
    return [hue(colour) for label, colour in group_colours(page).items() if label != "Lecture"]


@pytest.mark.parametrize("outline", [MANY_GROUPS_OUTLINE], ids=["many-groups"])
def test_each_of_fourteen_groups_gets_a_colour(page, mindmap_url):
    page.goto(mindmap_url)
    assert len(group_hues(page)) == MIN_DISTINCT_GROUPS


@pytest.mark.parametrize("outline", [MANY_GROUPS_OUTLINE], ids=["many-groups"])
def test_at_least_fourteen_groups_get_clearly_different_hues(page, mindmap_url):
    """Fourteen groups get hues at least 20 degrees apart around the colour wheel."""
    page.goto(mindmap_url)
    close = [
        (round(first), round(second))
        for first, second in combinations(group_hues(page), 2)
        if hue_gap(first, second) < MIN_HUE_GAP
    ]
    assert close == []


@pytest.mark.parametrize("outline", [MANY_GROUPS_OUTLINE], ids=["many-groups"])
def test_main_topic_colour_differs_from_every_group(page, mindmap_url):
    page.goto(mindmap_url)
    colours = group_colours(page)
    main_topic = colours.pop("Lecture")
    assert main_topic not in colours.values()


# Examples and exercises are orange

ORANGE_HUES = (25, 45)
MIN_ORANGE_SATURATION = 0.5
MANY_TOPICS = 40
# Topic A is the first topic, which gets green, far from orange.
EXAMPLE_OUTLINE = """# Matriser
## A
### Begrepp
### Exempel: Rad gånger kolonn
"""


def is_orange(colour: str) -> bool:
    hue, saturation = hue_and_saturation(colour)
    return ORANGE_HUES[0] <= hue <= ORANGE_HUES[1] and saturation >= MIN_ORANGE_SATURATION


def show_every_node(page, url: str) -> None:
    page.goto(f"{url}?depth=all")


def edge_colours(page) -> list[str]:
    return page.locator(".edge").evaluate_all("edges => edges.map(edge => getComputedStyle(edge).stroke)")


@pytest.mark.parametrize("prefix", ["Övning: ", "Exempel: "])
@pytest.mark.parametrize(
    "outline",
    [
        "# Matriser\n## {label}\n## B\n",
        "# Matriser\n## A\n### {label}\n",
        "# Matriser\n## A\n### Slide\n#### {label}\n",
        "# Matriser\n## A\n### Slide\n#### Term\n##### {label}\n",
    ],
    ids=["main-topic", "topic", "slide", "term"],
)
def test_exempel_or_ovning_is_orange_under_any_parent(page, render_outline, prefix, outline):
    """An exempel or övning node is orange under a main-topic, topic, slide or term node."""
    show_every_node(page, render_outline(outline.format(label=f"{prefix}Rad gånger kolonn")))
    assert is_orange(group_colours(page)[f"{prefix}Rad gånger kolonn"])


def test_term_labelled_exempel_keeps_topic_colour(page, render_outline):
    """A term whose label starts with `Exempel` keeps its topic's colour, since only the type makes a node orange."""
    outline = node("main-topic", "Matriser", node("topic", "A", node("slide", "Slide", term("Exempel på rad"))))
    show_every_node(page, render_outline(outline))
    colours = group_colours(page)
    assert colours["Exempel på rad"] == colours["A"]


def test_main_topic_stays_neutral_with_example_label(page, render_outline):
    """A main topic labelled `Exempel` keeps the main topic's neutral colours."""
    show_every_node(page, render_outline(node("main-topic", "Matriser", node("topic", "A")), "plain"))
    plain = group_colours(page)["Matriser"]
    show_every_node(page, render_outline(node("main-topic", "Exempel på matriser", node("topic", "A")), "example"))
    assert group_colours(page)["Exempel på matriser"] == plain


def test_sibling_of_example_keeps_topic_colour(page, render_outline):
    """A node next to an exempel node keeps its topic's colour."""
    show_every_node(page, render_outline(EXAMPLE_OUTLINE))
    colours = group_colours(page)
    assert colours["Begrepp"] == colours["A"]


def test_topic_labelled_exempel_is_not_orange(page, render_outline):
    """A topic whose label starts with `Exempel` keeps a topic colour, since only the type makes a node orange."""
    show_every_node(page, render_outline(node("main-topic", "Matriser", node("topic", "Exempel på rader"))))
    assert not is_orange(group_colours(page)["Exempel på rader"])


def test_edge_into_an_exempel_keeps_its_topic_colour(page, render_outline):
    """The edge from a slide node into an exempel is drawn in the topic's colour, not orange."""
    outline = node("main-topic", "Matriser", node("topic", "A", node("slide", "Slide", worked("exempel", "Rad"))))
    show_every_node(page, render_outline(outline))
    assert not any(is_orange(colour) for colour in edge_colours(page))


def test_edge_from_the_main_topic_into_an_exempel_is_orange(page, render_outline):
    """An exempel directly under the main topic has an orange edge."""
    show_every_node(page, render_outline(node("main-topic", "Matriser", worked("exempel", "Rad"))))
    assert all(is_orange(colour) for colour in edge_colours(page))


def test_exempel_under_the_main_topic_takes_no_topic_colour(page, render_outline):
    """A topic after an exempel directly under the main topic gets the colour it would have had without it."""
    show_every_node(page, render_outline(node("main-topic", "Matriser", node("topic", "A")), "alone"))
    alone = group_colours(page)["A"]
    after = node("main-topic", "Matriser", worked("exempel", "Rad"), node("topic", "A"))
    show_every_node(page, render_outline(after, "after"))
    assert group_colours(page)["A"] == alone


def test_no_topic_hue_comes_near_orange(page, render_outline):
    """With more topics than the palette holds, every topic's hue is at least 20 degrees from the orange."""
    topics = "".join(f"## Topic {number}\n" for number in range(1, MANY_TOPICS + 1))
    show_every_node(page, render_outline(f"# Matriser\n{topics}### Exempel: Rad gånger kolonn\n"))
    colours = group_colours(page)
    orange = hue(colours["Exempel: Rad gånger kolonn"])
    near = [
        f"Topic {number}"
        for number in range(1, MANY_TOPICS + 1)
        if hue_gap(hue(colours[f"Topic {number}"]), orange) < MIN_HUE_GAP
    ]
    assert near == []


EDGES_CROSSING_NODES = """() => {
  const cards = [...document.querySelectorAll('.node')].map(node => ({
    label: node.querySelector('.node-label').textContent,
    box: node.querySelector('.node-card').getBoundingClientRect(),
  }));
  const inside = ({box}, x, y) => {
    const rx = box.width / 2, ry = box.height / 2;
    return ((x - box.x - rx) / rx) ** 2 + ((y - box.y - ry) / ry) ** 2 < 1;
  };
  const crossings = [];
  document.querySelectorAll('.edge').forEach(edge => {
    const matrix = edge.getScreenCTM(), length = edge.getTotalLength();
    const points = Array.from({length: 101}, (_, i) =>
      edge.getPointAtLength(length * i / 100).matrixTransform(matrix));
    const ends = cards.filter(card =>
      inside(card, points[0].x, points[0].y) || inside(card, points[100].x, points[100].y));
    cards.filter(card => !ends.includes(card)).forEach(card => {
      if (points.some(point => inside(card, point.x, point.y)))
        crossings.push(`${ends.map(end => end.label).join(' to ')} crosses ${card.label}`);
    });
  });
  return crossings;
}"""


@pytest.mark.parametrize("style", ["C", "A"], ids=["topic-circles", "radial-rings"])
@pytest.mark.parametrize("outline", [NESTED_OUTLINE, DEMO_OUTLINE], ids=["nested", "demo"])
def test_edges_do_not_pass_through_other_nodes(page, mindmap_url, style):
    page.goto(f"{mindmap_url}?variant={style}")
    page.get_by_role("button", name="Show whole Mindmap", exact=True).click()
    assert page.evaluate(EDGES_CROSSING_NODES) == []


MIN_READABLE_LABEL_PX = 11


def on_screen_label_sizes(page, depth: int) -> list[dict]:
    """Rendered font size in screen pixels of every visible label at `depth`."""
    return page.locator(f'.node[data-depth="{depth}"] .node-label').evaluate_all(
        "labels => labels.map(label => ({label: label.textContent,"
        "px: parseFloat(getComputedStyle(label).fontSize)"
        " * label.getBoundingClientRect().width / label.offsetWidth}))"
    )


def boxes_outside_canvas(page) -> list[str]:
    canvas = page.locator("#canvas").bounding_box()
    return [
        box["label"]
        for box in node_boxes(page)
        if box["x"] < canvas["x"]
        or box["y"] < canvas["y"]
        or box["x"] + box["width"] > canvas["x"] + canvas["width"]
        or box["y"] + box["height"] > canvas["y"] + canvas["height"]
    ]


def test_mindmap_opens_with_radial_rings_selected(page, mindmap_url):
    page.goto(mindmap_url)
    page.get_by_role("button", name="Mindmap settings").click()
    assert page.get_by_role("radio", name="Radial rings").is_checked()


def test_mindmap_opens_in_radial_rings(page, mindmap_url):
    page.goto(mindmap_url)
    assert page.locator("body").get_attribute("data-variant") == "A"


@pytest.mark.parametrize("outline", [DEMO_OUTLINE], ids=["demo"])
def test_opening_view_shows_every_group(page, mindmap_url):
    page.goto(mindmap_url)
    assert len(on_screen_label_sizes(page, 1)) == 6


@pytest.mark.parametrize("outline", [DEMO_OUTLINE], ids=["demo"])
def test_opening_view_shows_every_group_with_a_readable_label(page, mindmap_url):
    page.goto(mindmap_url)
    assert [size for size in on_screen_label_sizes(page, 1) if size["px"] < MIN_READABLE_LABEL_PX] == []


@pytest.mark.parametrize("outline", [DEMO_OUTLINE], ids=["demo"])
def test_opening_view_shows_every_group_inside_the_canvas(page, mindmap_url):
    page.goto(mindmap_url)
    groups = {size["label"] for size in on_screen_label_sizes(page, 1)}
    assert [label for label in boxes_outside_canvas(page) if label in groups] == []


@pytest.mark.parametrize("style", ["C", "A"], ids=["topic-circles", "radial-rings"])
@pytest.mark.parametrize("outline", [DEMO_OUTLINE], ids=["demo"])
def test_show_whole_mindmap_fits_every_node_on_screen(page, mindmap_url, style):
    page.goto(f"{mindmap_url}?variant={style}")
    page.get_by_role("button", name="Show whole Mindmap", exact=True).click()
    assert boxes_outside_canvas(page) == []


# Topic circles shares rings and arcs by branch size

def tangle_outline() -> str:
    """The shape of the Axiomatiseringar Mindmap, relabelled so every label is unique."""
    slides_per_topic = [[3, 7, 6, 6], [3, 5, 5, 4, 3, 6, 1], [3, 1, 2, 3, 3, 4, 2]]
    lines = ["# Föreläsning"]
    for t, slides in enumerate(slides_per_topic, start=1):
        lines.append(f"## Ämne {t}")
        for s, terms in enumerate(slides, start=1):
            lines.append(f"### Slide {t}.{s}")
            lines.extend(f"#### Term {t}.{s}.{n}" for n in range(1, terms + 1))
    lines.append("#### Steg")
    lines.extend(f"##### Exempel: Steg {n}" for n in range(1, 4))
    return "\n".join(lines) + "\n"


TANGLE_OUTLINE = tangle_outline()

CROWDED_OUTLINE = "# Föreläsning\n" + "".join(
    f"## Ämne {t}\n"
    + "".join(
        f"### Slide {t}.{s}\n" + "".join(f"#### Term {t}.{s}.{n}\n" for n in range(1, 5))
        for s in range(1, 7)
    )
    for t in range(1, 7)
)

RING_SHARES_OUTLINE = """# Föreläsning
## Ämne
### Liten A
### Liten B
### Stor
#### Stor 1
#### Stor 2
#### Stor 3
#### Stor 4
### Liten C
"""

ARC_OUTLINE = """# Föreläsning
## Ämne
### Två
#### Två 1
#### Två 2
### Fem
#### Fem 1
#### Fem 2
#### Fem 3
#### Fem 4
#### Fem 5
### Tre
#### Tre 1
#### Tre 2
#### Tre 3
### Ensam
#### Enda
### Andel
#### Andel A
#### Andel Stor
##### Exempel: Stor 1
##### Exempel: Stor 2
##### Exempel: Stor 3
#### Andel B
#### Andel C
"""

MANY_CHILDREN_OUTLINE = "# Föreläsning\n## Ämne\n### Många\n" + "".join(
    f"#### Många {n}\n" for n in range(1, 21)
)

RADIAL_OUTLINE = """# Lecture
## Group
### A
#### Leaf A
#### B
##### Exempel: Leaf B
## Other
### C
### D
"""

# World positions Radial rings gives RADIAL_OUTLINE.
RADIAL_POSITIONS = {
    "Lecture": (0.0, 0.0),
    "Group": (905.0, 0.0),
    "A": (1675.0, 0.0),
    "Leaf A": (1566.2, -1190.3),
    "B": (1566.2, 1190.3),
    "Exempel: Leaf B": (1877.4, 1426.8),
    "Other": (-905.0, 0.0),
    "C": (-1184.4, 900.1),
    "D": (-1184.4, -900.1),
}


def outline_parents(outline: str) -> dict[str, str | None]:
    """Each heading's parent label, read from the Outline's heading levels."""
    parents, stack = {}, []
    for line in outline.splitlines():
        level = len(line) - len(line.lstrip("#"))
        label = line[level:].strip()
        del stack[level - 1:]
        parents[label] = stack[-1] if stack else None
        stack.append(label)
    return parents


def outline_depths(parents: dict[str, str | None]) -> dict[str, int]:
    depths = {}
    for label, parent in parents.items():
        depth = 0
        while parent is not None:
            depth, parent = depth + 1, parents[parent]
        depths[label] = depth
    return depths


def top_level_topic(parents, label):
    while parents[label] is not None and parents[parents[label]] is not None:
        label = parents[label]
    return label


def node_centres(page) -> dict[str, dict]:
    """Every shown node's centre and size in world coordinates, keyed by label."""
    boxes = page.locator(".node").evaluate_all(
        "nodes => nodes.map(node => ({label: node.querySelector('.node-label').textContent,"
        "x: +node.getAttribute('x'), y: +node.getAttribute('y'),"
        "w: +node.getAttribute('width'), h: +node.getAttribute('height')}))"
    )
    return {
        box["label"]: {"x": box["x"] + box["w"] / 2, "y": box["y"] + box["h"] / 2, "w": box["w"], "h": box["h"]}
        for box in boxes
    }


def edge_paths(page) -> list[list[tuple[float, float]]]:
    """Every shown edge as 21 points along it, in world coordinates."""
    return page.locator(".edge").evaluate_all(
        "edges => edges.map(edge => {const length = edge.getTotalLength();"
        "return Array.from({length: 21}, (_, i) => {"
        "const point = edge.getPointAtLength(length * i / 20); return [point.x, point.y];});})"
    )


def labelled_edges(page) -> dict[str, list[tuple[float, float]]]:
    """Every shown edge keyed by the label of the child it ends at."""
    centres = node_centres(page)
    edges = {}
    for points in edge_paths(page):
        x, y = points[-1]
        child = min(centres, key=lambda label: math.hypot(centres[label]["x"] - x, centres[label]["y"] - y))
        edges[child] = points
    return edges


def open_topic_circles(page, url: str, depth: str = "all") -> None:
    page.goto(f"{url}?variant=C&depth={depth}")


def angle(centres, origin: str, target: str) -> float:
    return math.atan2(centres[target]["y"] - centres[origin]["y"], centres[target]["x"] - centres[origin]["x"])


def away(centres, parents, topic: str) -> float:
    return angle(centres, parents[topic], topic)


def turn(a: float, b: float) -> float:
    """The signed angle from a to b, between -pi and pi."""
    return (b - a + math.pi) % (2 * math.pi) - math.pi


def children(parents, topic: str) -> list[str]:
    return [label for label, parent in parents.items() if parent == topic]


def ring_gaps(centres, topic: str, members: list[str]) -> dict[tuple[str, str], float]:
    """The angle between each pair of neighbouring children round a full ring."""
    ordered = sorted(members, key=lambda label: angle(centres, topic, label))
    return {
        (first, second): (angle(centres, topic, second) - angle(centres, topic, first)) % (2 * math.pi)
        for first, second in zip(ordered, ordered[1:] + ordered[:1])
    }


def arc_offsets(centres, parents, topic: str) -> dict[str, float]:
    """Each child's signed angle from the direction away from the topic's parent."""
    out = away(centres, parents, topic)
    return {label: turn(out, angle(centres, topic, label)) for label in children(parents, topic)}


def convex_hull(points):
    points = sorted(set(points))
    if len(points) < 3:
        return points

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for point in points:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    for point in reversed(points):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def hulls_overlap(first, second) -> bool:
    """Whether two convex polygons share any area, by the separating axis test."""

    def project(normal, shape):
        return [normal[0] * x + normal[1] * y for x, y in shape]

    for polygon in (first, second):
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            normal = (b[1] - a[1], a[0] - b[0])
            on_first, on_second = project(normal, first), project(normal, second)
            if max(on_first) <= min(on_second) or max(on_second) <= min(on_first):
                return False
    return True


def inside_hull(hull, point) -> bool:
    signs = {
        math.copysign(1, (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]))
        for a, b in zip(hull, hull[1:] + hull[:1])
    }
    return len(signs) == 1


def segments_cross(p1, p2, q1, q2) -> bool:
    def side(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    return side(p1, p2, q1) * side(p1, p2, q2) < 0 and side(q1, q2, p1) * side(q1, q2, p2) < 0


def paths_cross(first, second) -> bool:
    return any(
        segments_cross(a, b, c, d)
        for a, b in pairwise(first)
        for c, d in pairwise(second)
    )


def inside_node(node, x, y) -> bool:
    rx, ry = node["w"] / 2, node["h"] / 2
    return ((x - node["x"]) / rx) ** 2 + ((y - node["y"]) / ry) ** 2 < 1


# Top-level topics and their rings


def test_branches_of_top_level_topics_never_meet(page, render_outline):
    """The convex hulls of any two top-level branches share no area, even with six crowded branches."""
    parents = outline_parents(CROWDED_OUTLINE)
    open_topic_circles(page, render_outline(CROWDED_OUTLINE))
    centres = node_centres(page)
    branches = {}
    for label in parents:
        if parents[label] is not None:
            branches.setdefault(top_level_topic(parents, label), []).append((centres[label]["x"], centres[label]["y"]))
    hulls = {topic: convex_hull(points) for topic, points in branches.items()}
    assert [(a, b) for a, b in combinations(hulls, 2) if hulls_overlap(hulls[a], hulls[b])] == []


def test_top_level_topic_is_surrounded_by_its_subtopics(page, render_outline):
    """Each top-level topic with three or more subtopics sits inside the hull of their centres."""
    parents = outline_parents(TANGLE_OUTLINE)
    open_topic_circles(page, render_outline(TANGLE_OUTLINE))
    centres = node_centres(page)
    outside = []
    for topic in children(parents, "Föreläsning"):
        hull = convex_hull([(centres[c]["x"], centres[c]["y"]) for c in children(parents, topic)])
        if not inside_hull(hull, (centres[topic]["x"], centres[topic]["y"])):
            outside.append(topic)
    assert outside == []


def test_edge_into_top_level_topic_misses_its_subtopics(page, render_outline):
    """The edge from the main topic into a top-level topic passes through none of that topic's subtopics."""
    parents = outline_parents(TANGLE_OUTLINE)
    open_topic_circles(page, render_outline(TANGLE_OUTLINE))
    centres, edges = node_centres(page), labelled_edges(page)
    hits = [
        (topic, child)
        for topic in children(parents, "Föreläsning")
        for child in children(parents, topic)
        if any(inside_node(centres[child], x, y) for x, y in edges[topic])
    ]
    assert hits == []


def test_subtopics_of_a_top_level_topic_sit_on_one_circle(page, render_outline):
    """Every subtopic of a top-level topic sits the same distance from it."""
    open_topic_circles(page, render_outline(RING_SHARES_OUTLINE))
    centres = node_centres(page)
    distances = [
        math.hypot(centres[c]["x"] - centres["Ämne"]["x"], centres[c]["y"] - centres["Ämne"]["y"])
        for c in ["Liten A", "Liten B", "Stor", "Liten C"]
    ]
    assert max(distances) - min(distances) == pytest.approx(0, abs=1)


def test_bigger_branch_gets_a_wider_share_of_the_ring(page, render_outline):
    """Both gaps beside a five-node branch on a ring are at least twice any gap between two leaves."""
    open_topic_circles(page, render_outline(RING_SHARES_OUTLINE))
    gaps = ring_gaps(node_centres(page), "Ämne", ["Liten A", "Liten B", "Stor", "Liten C"])
    beside_big = [gap for pair, gap in gaps.items() if "Stor" in pair]
    between_leaves = [gap for pair, gap in gaps.items() if "Stor" not in pair]
    assert min(beside_big) >= 2 * max(between_leaves)


def test_ring_with_bigger_branches_has_a_wider_radius(page, render_outline):
    """Subtopics of a top-level topic with thirty nodes under it sit farther out than those of one with eight."""

    def ring_radius(outline, topic, subtopic, name):
        open_topic_circles(page, render_outline(outline, name))
        centres = node_centres(page)
        return math.hypot(centres[subtopic]["x"] - centres[topic]["x"], centres[subtopic]["y"] - centres[topic]["y"])

    crowded = ring_radius(CROWDED_OUTLINE, "Ämne 1", "Slide 1.1", "crowded")
    sparse = ring_radius(RING_SHARES_OUTLINE, "Ämne", "Liten A", "sparse")
    assert crowded > sparse


# Deeper topics and their arcs


def test_deeper_children_face_away_from_their_topics_parent(page, render_outline):
    """Every child of a topic at depth two or deeper sits less than 90 degrees from the direction away from that topic's parent."""
    parents = outline_parents(TANGLE_OUTLINE)
    depths = outline_depths(parents)
    open_topic_circles(page, render_outline(TANGLE_OUTLINE))
    centres = node_centres(page)
    behind = [
        child
        for topic in parents
        if depths[topic] >= 2
        for child, offset in arc_offsets(centres, parents, topic).items()
        if abs(offset) >= math.pi / 2
    ]
    assert behind == []


def test_arc_is_centred_on_the_direction_away_from_the_parent(page, render_outline):
    """Three equal children sit on an arc whose middle points straight away from their topic's parent."""
    parents = outline_parents(ARC_OUTLINE)
    open_topic_circles(page, render_outline(ARC_OUTLINE))
    offsets = arc_offsets(node_centres(page), parents, "Tre")
    assert math.degrees(sum(offsets.values()) / len(offsets)) == pytest.approx(0, abs=1)


def test_children_on_an_arc_sit_on_one_circle(page, render_outline):
    """Every child on a deeper topic's arc sits the same distance from that topic."""
    open_topic_circles(page, render_outline(ARC_OUTLINE))
    centres = node_centres(page)
    distances = [
        math.hypot(centres[c]["x"] - centres["Fem"]["x"], centres[c]["y"] - centres["Fem"]["y"])
        for c in [f"Fem {n}" for n in range(1, 6)]
    ]
    assert max(distances) - min(distances) == pytest.approx(0, abs=1)


def test_arc_widens_with_more_children(page, render_outline):
    """The arc of a topic with five children spans a wider angle than the arc of a topic with two."""
    parents = outline_parents(ARC_OUTLINE)
    open_topic_circles(page, render_outline(ARC_OUTLINE))
    centres = node_centres(page)

    def span(topic):
        offsets = arc_offsets(centres, parents, topic).values()
        return max(offsets) - min(offsets)

    assert span("Fem") > span("Två")


def test_arc_never_passes_a_half_circle(page, render_outline):
    """Twenty children of one deeper topic all sit less than 90 degrees from the direction away from its parent."""
    parents = outline_parents(MANY_CHILDREN_OUTLINE)
    open_topic_circles(page, render_outline(MANY_CHILDREN_OUTLINE))
    offsets = arc_offsets(node_centres(page), parents, "Många")
    assert max(abs(offset) for offset in offsets.values()) < math.pi / 2


def test_bigger_branch_gets_a_wider_share_of_the_arc(page, render_outline):
    """Both gaps beside a four-node branch on an arc are at least twice the gap between two leaves."""
    parents = outline_parents(ARC_OUTLINE)
    open_topic_circles(page, render_outline(ARC_OUTLINE))
    offsets = arc_offsets(node_centres(page), parents, "Andel")
    ordered = sorted(offsets, key=offsets.get)
    gaps = {(a, b): offsets[b] - offsets[a] for a, b in pairwise(ordered)}
    beside_big = [gap for pair, gap in gaps.items() if "Andel Stor" in pair]
    between_leaves = [gap for pair, gap in gaps.items() if "Andel Stor" not in pair]
    assert min(beside_big) >= 2 * max(between_leaves)


def test_single_child_points_straight_away_from_the_parent(page, render_outline):
    """A deeper topic's only child sits on the line from that topic's parent through the topic."""
    parents = outline_parents(ARC_OUTLINE)
    open_topic_circles(page, render_outline(ARC_OUTLINE))
    offsets = arc_offsets(node_centres(page), parents, "Ensam")
    assert math.degrees(offsets["Enda"]) == pytest.approx(0, abs=1)


# The whole map


def test_no_two_edges_cross_within_a_top_level_branch(page, render_outline):
    """No two edges of one top-level branch cross, unless they meet at a shared node."""
    parents = outline_parents(TANGLE_OUTLINE)
    open_topic_circles(page, render_outline(TANGLE_OUTLINE))
    edges = labelled_edges(page)
    crossings = [
        (a, b)
        for a, b in combinations(edges, 2)
        if top_level_topic(parents, a) == top_level_topic(parents, b)
        and not {a, parents[a]} & {b, parents[b]}
        and paths_cross(edges[a], edges[b])
    ]
    assert crossings == []


def test_every_node_sits_closest_to_its_own_topic(page, render_outline):
    """Each node at depth two or deeper is nearer its parent than any other node at its parent's depth."""
    parents = outline_parents(TANGLE_OUTLINE)
    depths = outline_depths(parents)
    open_topic_circles(page, render_outline(TANGLE_OUTLINE))
    centres = node_centres(page)

    def distance(a, b):
        return math.hypot(centres[a]["x"] - centres[b]["x"], centres[a]["y"] - centres[b]["y"])

    strays = [
        label
        for label in parents
        if depths[label] >= 2
        and any(
            distance(label, other) < distance(label, parents[label])
            for other in parents
            if depths[other] == depths[label] - 1 and other != parents[label]
        )
    ]
    assert strays == []


def test_nodes_do_not_overlap_when_every_level_shows(page, render_outline):
    """No two node boxes overlap on the Axiomatiseringar shape with every level shown."""
    open_topic_circles(page, render_outline(TANGLE_OUTLINE))
    centres = node_centres(page)
    overlapping = [
        (a, b)
        for a, b in combinations(centres, 2)
        if abs(centres[a]["x"] - centres[b]["x"]) < (centres[a]["w"] + centres[b]["w"]) / 2
        and abs(centres[a]["y"] - centres[b]["y"]) < (centres[a]["h"] + centres[b]["h"]) / 2
    ]
    assert overlapping == []


def test_depth_two_view_uses_the_same_positions(page, render_outline):
    """Every node shown at depth two sits where it sits when every level shows."""
    url = render_outline(TANGLE_OUTLINE)
    open_topic_circles(page, url, depth="all")
    everything = node_centres(page)
    open_topic_circles(page, url, depth="2")
    moved = [
        label
        for label, centre in node_centres(page).items()
        if (centre["x"], centre["y"]) != pytest.approx((everything[label]["x"], everything[label]["y"]), abs=0.5)
    ]
    assert moved == []


def test_folding_a_branch_keeps_other_nodes_in_place(page, render_outline):
    """Hiding a Slide's terms with every level shown leaves every other node where it was."""
    open_topic_circles(page, render_outline(TANGLE_OUTLINE))
    before = node_centres(page)
    page.get_by_role("button", name="Hide children of Slide 1.2", exact=True).dispatch_event("click")
    moved = [
        label
        for label, centre in node_centres(page).items()
        if (centre["x"], centre["y"]) != pytest.approx((before[label]["x"], before[label]["y"]), abs=0.5)
    ]
    assert moved == []


def test_radial_rings_places_nodes_at_known_positions(page, render_outline):
    """Radial rings places every node at the position recorded in RADIAL_POSITIONS."""
    page.goto(f"{render_outline(RADIAL_OUTLINE)}?variant=A&depth=all")
    centres = node_centres(page)
    assert {label: (round(c["x"], 1), round(c["y"], 1)) for label, c in centres.items()} == RADIAL_POSITIONS


# Slides in the panel

SLIDES_OUTLINE = node(
    "main-topic", "Matriser", node("topic", "Gauss", slides=[3, 1], explanation="Radoperationer ger trappform.")
)


@pytest.fixture
def slides_outline():
    return SLIDES_OUTLINE


@pytest.fixture
def slides_url(source: Path, deck: Path, cache_dir: Path, tmp_path: Path, slides_outline):
    """The page for `slides_outline` on a Transcript with the three-page Deck attached."""
    transcript = transcribe(
        source,
        cache_dir=cache_dir,
        recognize=lambda wav, vocabulary: [Fragment(0, 1, "En föreläsning.")],
    )
    read_slides(transcript.transcript_id, deck, cache_dir=cache_dir)
    return render_mindmap(
        transcript.transcript_id,
        slides_outline,
        cache_dir=cache_dir,
        output_dir=tmp_path,
    ).page.as_uri()


def open_panel(page, url: str, label: str) -> None:
    page.goto(url)
    page.get_by_role("button", name=f"Explore {label}", exact=True).dispatch_event("click")


def panel_images(page):
    return page.locator("#panel").get_by_role("img")


def test_selected_example_fill_is_orange(page, render_outline):
    """A selected `Exempel:` node is filled orange."""
    open_panel(page, render_outline(EXAMPLE_OUTLINE), "Exempel: Rad gånger kolonn")
    card = page.locator(".node", has=page.get_by_role("button", name="Explore Exempel: Rad gånger kolonn", exact=True))
    assert is_orange(card.locator(".node-card").evaluate("card => getComputedStyle(card).backgroundColor"))


def test_selected_example_panel_path_is_orange(page, render_outline):
    """The panel path above a selected `Exempel:` node's title is orange."""
    open_panel(page, render_outline(EXAMPLE_OUTLINE), "Exempel: Rad gånger kolonn")
    assert is_orange(page.locator("#panel-path").evaluate("path => getComputedStyle(path).color"))


def test_selected_example_panel_rule_is_orange(page, render_outline):
    """The rule under a selected `Exempel:` node's panel title is orange."""
    open_panel(page, render_outline(EXAMPLE_OUTLINE), "Exempel: Rad gånger kolonn")
    assert is_orange(page.locator(".panel-rule").evaluate("rule => getComputedStyle(rule).borderTopColor"))


def under_a_slide(*children: dict) -> dict:
    """The main topic Matriser, topic A, slide node Slide, and these nodes under it."""
    return node("main-topic", "Matriser", node("topic", "A", node("slide", "Slide", *children)))


def worked_under_a_slide(kind: str = "exempel", **parts) -> dict:
    """The main topic Matriser, topic A, slide node Slide, and under it one exempel or övning labelled Rad gånger kolonn."""
    return under_a_slide({**worked(kind, "Rad gånger kolonn"), **parts})


def card_labels(page) -> list[str]:
    return page.locator(".node-label").all_text_contents()


def click_card(page, text: str) -> None:
    """Open the panel of the node whose card label ends with this text."""
    page.locator(".node-label").filter(has_text=re.compile(f"{re.escape(text)}$")).dispatch_event("click")


@pytest.mark.parametrize("kind, prefix", [("exempel", "Exempel: "), ("övning", "Övning: ")])
def test_map_card_shows_the_type_prefix(page, render_outline, kind: str, prefix: str):
    """The map card shows `Exempel: ` or `Övning: ` before the label."""
    show_every_node(page, render_outline(worked_under_a_slide(kind)))
    assert f"{prefix}Rad gånger kolonn" in card_labels(page)


def test_card_aria_label_shows_the_type_prefix(page, render_outline):
    """The card's aria-label names the node with its prefix."""
    show_every_node(page, render_outline(worked_under_a_slide()))
    assert page.get_by_role("button", name="Explore Exempel: Rad gånger kolonn", exact=True).count() == 1


@pytest.mark.parametrize("kind, prefix", [("exempel", "Exempel: "), ("övning", "Övning: ")])
def test_panel_title_shows_the_type_prefix(page, render_outline, kind: str, prefix: str):
    """The panel title shows `Exempel: ` or `Övning: ` before the label."""
    show_every_node(page, render_outline(worked_under_a_slide(kind)))
    click_card(page, "Rad gånger kolonn")
    assert page.locator("#panel-title").text_content() == f"{prefix}Rad gånger kolonn"


def test_explore_next_button_shows_the_type_prefix(page, render_outline):
    """The Explore next button for an exempel, in its parent's panel, shows the prefix."""
    show_every_node(page, render_outline(worked_under_a_slide()))
    click_card(page, "Slide")
    assert "Exempel: Rad gånger kolonn" in page.locator("#related button").all_text_contents()


# Math and the exempel box in the panel

BOX_ORANGE = "rgb(217, 112, 28)"
TRY_YOURSELF = "Ingen lösning i föreläsningen. Försök själv."


def solved(
    kind: str = "exempel",
    label: str = "Rad gånger kolonn",
    *,
    task: str = "Lös $x + 1 = 2$",
    steps=(("x = 2 - 1", "subtrahera 1"), ("x = 1", "")),
    answer: str = "$x = 1$",
    slides=(),
) -> dict:
    """An exempel or övning with a task, steps given as (calculation, reason) pairs, and an answer."""
    return {
        **worked(kind, label),
        "slides": list(slides),
        "task": task,
        "steps": [{"calculation": calculation, "reason": reason} for calculation, reason in steps],
        "answer": answer,
    }


def open_card_panel(page, url: str, label: str) -> None:
    """Open the page with every node shown, then the panel of the node whose card label ends with `label`."""
    show_every_node(page, url)
    click_card(page, label)


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
    open_card_panel(page, render_outline(under_a_slide(term("Gauss", explanation="Arean är $\\pi r^2$."))), "Gauss")
    assert katex_count(page, "#explanation") == 1


def test_math_typesets_with_no_network(page, render_outline):
    """A page opened with every network request blocked still typesets its math."""
    url = render_outline(under_a_slide(term("Gauss", explanation="Arean är $\\pi r^2$.")))
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort())
    open_card_panel(page, url, "Gauss")
    assert katex_count(page, "#explanation") == 1


def test_math_is_always_inline(page, render_outline):
    """Math typesets inline in the line of prose, never as a display block."""
    open_card_panel(page, render_outline(under_a_slide(term("Gauss", explanation="Låt $x = 1$ vara givet."))), "Gauss")
    kinds = page.locator("#explanation .katex").evaluate_all(
        "found => found.map(math => math.closest('.katex-display') ? 'display' : 'inline')"
    )
    assert kinds == ["inline"]


def test_long_math_breaks_over_lines(page, render_outline):
    """A sum too long for the panel breaks over more than one line, at its `=` and `+`."""
    long_sum = " + ".join(f"a_{{{n}}}" for n in range(1, 31)) + " = b"
    open_card_panel(page, render_outline(under_a_slide(term("Gauss", explanation=f"${long_sum}$"))), "Gauss")
    tops = page.locator("#explanation .katex .base").evaluate_all(
        "found => [...new Set(found.map(base => Math.round(base.getBoundingClientRect().top)))]"
    )
    assert len(tops) > 1


def test_escaped_dollar_shows_a_dollar_sign(page, render_outline):
    """`\\$` shows as a literal dollar sign."""
    open_card_panel(page, render_outline(under_a_slide(term("Gauss", explanation="Kostar 5 \\$ styck."))), "Gauss")
    assert page.locator("#explanation").inner_text() == "Kostar 5 $ styck."


def test_label_latex_stays_raw_while_explanation_typesets(page, render_outline):
    """In one panel, LaTeX in the label shows as its source while the explanation's math typesets."""
    open_card_panel(page, render_outline(under_a_slide(term("$x^2$", explanation="$x^2$"))), "$x^2$")
    assert (katex_count(page, "#panel-title"), katex_count(page, "#explanation")) == (0, 1)


@pytest.mark.parametrize("kind, label", [("exempel", "Exempel"), ("övning", "Övning")])
def test_worked_panel_label_names_its_type(page, render_outline, kind: str, label: str):
    """The label above an exempel's or övning's text reads `Exempel` or `Övning`."""
    open_card_panel(page, render_outline(under_a_slide(solved(kind))), "Rad gånger kolonn")
    assert page.locator(".explanation-label").text_content() == label


def test_box_takes_the_explanations_place(page, render_outline):
    """An exempel's panel hides the explanation and shows the box in its place."""
    open_card_panel(page, render_outline(under_a_slide(term("Gauss", explanation="Arean är stor."), solved())), "Gauss")
    click_card(page, "Rad gånger kolonn")
    assert (page.locator("#explanation").is_visible(), box(page).is_visible()) == (False, True)


def test_box_is_a_white_bordered_card(page, render_outline):
    """The box is a white card with a thin border and rounded corners."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    style = box(page).evaluate(
        "box => { const s = getComputedStyle(box);"
        " return [s.backgroundColor, parseFloat(s.borderTopWidth) > 0, parseFloat(s.borderTopLeftRadius) > 0]; }"
    )
    assert style == ["rgb(255, 255, 255)", True, True]


def test_box_heading_is_orange_small_capitals_underlined_in_orange(page, render_outline):
    """The box heading is in small orange capitals with an orange underline."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    style = box(page).get_by_role("heading").evaluate(
        "h => { const s = getComputedStyle(h);"
        " return [s.color, s.borderBottomColor, parseFloat(s.borderBottomWidth) > 0, s.fontVariantCaps]; }"
    )
    assert style == [BOX_ORANGE, BOX_ORANGE, True, "small-caps"]


def test_open_answer_is_tinted_orange(page, render_outline):
    """The Visa svar section is tinted orange once open."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    answer = section(page, "Visa svar")
    answer.locator("summary").click()
    background = answer.evaluate("details => getComputedStyle(details).backgroundColor")
    assert background.startswith("rgba(217, 112, 28,")


def test_step_reason_is_muted_italic(page, render_outline):
    """A step's reason is set in muted italic, apart from its calculation."""
    open_card_panel(page, render_outline(under_a_slide(solved(steps=(("x = 1", "subtrahera 1"),)))), "Rad gånger kolonn")
    open_solution(page)
    style = box(page).locator(".step-reason").evaluate(
        "reason => { const s = getComputedStyle(reason), box = getComputedStyle(reason.closest('#worked'));"
        " return [s.fontStyle, s.color !== box.color]; }"
    )
    assert style == ["italic", True]


@pytest.mark.parametrize(
    "label, heading", [("Andra", "Exempel 2"), ("Tredje", "Övning 1")], ids=["second-exempel", "first-ovning"]
)
def test_box_heading_counts_exempel_and_ovning_separately(page, render_outline, label: str, heading: str):
    """The box heading counts exempel and övning separately, in Outline order."""
    outline = under_a_slide(solved("exempel", "Första"), solved("exempel", "Andra"), solved("övning", "Tredje"))
    open_card_panel(page, render_outline(outline), label)
    assert box(page).get_by_role("heading").text_content() == heading


def test_box_shows_the_task_under_its_heading(page, render_outline):
    """The task is the first text in the box after its heading."""
    open_card_panel(page, render_outline(under_a_slide(solved(task="Lös uppgiften nu"))), "Rad gånger kolonn")
    assert box(page).inner_text().splitlines()[1] == "Lös uppgiften nu"


def test_box_task_math_typesets(page, render_outline):
    """The math in a task typesets."""
    open_card_panel(page, render_outline(under_a_slide(solved(task="Lös $x + 1 = 2$"))), "Rad gånger kolonn")
    assert box(page).locator(".task .katex").count() == 1


def test_long_task_prose_wraps_inside_the_box(page, render_outline):
    """A long task wraps inside the box instead of running off it."""
    task = "Bestäm " + " och ".join(f"värdet av $x_{{{n}}}$" for n in range(1, 25)) + "."
    open_card_panel(page, render_outline(under_a_slide(solved(task=task))), "Rad gånger kolonn")
    fits = box(page).evaluate_all("found => found.map(box => box.scrollWidth <= box.clientWidth)")
    assert fits == [True]


def test_solution_starts_closed(page, render_outline):
    """The Visa lösning section starts closed."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    assert section(page, "Visa lösning").evaluate("details => details.open") is False


def test_solution_toggle_shows_the_step_count(page, render_outline):
    """The Visa lösning toggle shows how many steps the solution has."""
    steps = (("a = 1", ""), ("b = 2", ""), ("c = 3", ""))
    open_card_panel(page, render_outline(under_a_slide(solved(steps=steps))), "Rad gånger kolonn")
    assert "3" in section(page, "Visa lösning").locator("summary").text_content()


def test_open_solution_numbers_steps_from_one(page, render_outline):
    """Opened, the solution shows one row per step, numbered 1, 2 and on."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    open_solution(page)
    numbers = box(page).locator(".step").evaluate_all("rows => rows.map(row => row.innerText.trim().split(/\\s/)[0])")
    assert numbers == ["1", "2"]


def test_step_calculation_typesets_inline(page, render_outline):
    """A step's calculation typesets as inline math."""
    open_card_panel(page, render_outline(under_a_slide(solved(steps=(("x = \\frac{1}{2}", ""),)))), "Rad gånger kolonn")
    open_solution(page)
    assert box(page).locator(".step-calculation .katex").count() == 1


def test_step_reason_math_typesets(page, render_outline):
    """Math in a step's reason typesets, such as a Greek letter."""
    outline = under_a_slide(solved(steps=(("x = 1", "sätt in $\\alpha$"),)))
    open_card_panel(page, render_outline(outline), "Rad gånger kolonn")
    open_solution(page)
    assert box(page).locator(".step-reason .katex").count() == 1


def test_step_reason_sits_under_its_calculation(page, render_outline):
    """A step's reason sits under its calculation."""
    open_card_panel(page, render_outline(under_a_slide(solved(steps=(("x = 1", "subtrahera 1"),)))), "Rad gånger kolonn")
    open_solution(page)
    assert top(box(page).locator(".step-reason")) >= bottom(box(page).locator(".step-calculation"))


def test_answer_starts_closed(page, render_outline):
    """The Visa svar section starts closed."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    assert section(page, "Visa svar").evaluate("details => details.open") is False


def test_answer_comes_after_the_solution(page, render_outline):
    """The Visa svar section sits below the Visa lösning section."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    assert top(section(page, "Visa svar")) >= bottom(section(page, "Visa lösning"))


def test_box_without_steps_has_no_solution_section(page, render_outline):
    """A box whose node has no steps shows no Visa lösning section."""
    open_card_panel(page, render_outline(under_a_slide(solved(steps=()))), "Rad gånger kolonn")
    shown = box(page).evaluate_all("found => found.map(box => box.textContent.includes('Visa lösning'))")
    assert shown == [False]


def test_box_without_answer_has_no_answer_section(page, render_outline):
    """A box whose node has an empty answer shows no Visa svar section."""
    open_card_panel(page, render_outline(under_a_slide(solved(answer=""))), "Rad gånger kolonn")
    shown = box(page).evaluate_all("found => found.map(box => box.textContent.includes('Visa svar'))")
    assert shown == [False]


def test_box_with_neither_says_to_try_yourself(page, render_outline):
    """A box with no steps and no answer shows the try-it-yourself line."""
    open_card_panel(page, render_outline(under_a_slide(solved(steps=(), answer=""))), "Rad gånger kolonn")
    assert TRY_YOURSELF in box(page).text_content()


def test_box_with_steps_does_not_say_to_try_yourself(page, render_outline):
    """A box that has steps leaves the try-it-yourself line out."""
    open_card_panel(page, render_outline(under_a_slide(solved(answer=""))), "Rad gånger kolonn")
    shown = box(page).evaluate_all(f"found => found.map(box => box.textContent.includes({TRY_YOURSELF!r}))")
    assert shown == [False]


def test_box_text_is_set_in_katex_main(page, render_outline):
    """Box text is set in KaTeX_Main, so prose and math share one face."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    families = box(page).evaluate_all("found => found.map(box => getComputedStyle(box).fontFamily)")
    assert [family.split(",")[0].strip("\"' ") for family in families] == ["KaTeX_Main"]


def test_section_toggles_use_the_app_sans(page, render_outline):
    """The Visa lösning and Visa svar toggles use the app's sans, Inter."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    families = box(page).locator("summary").evaluate_all("found => found.map(s => getComputedStyle(s).fontFamily)")
    assert families and all(family.startswith("Inter") for family in families)


@pytest.mark.parametrize("slides_outline", [under_a_slide(solved(slides=[1]))], ids=["exempel-with-a-slide"])
def test_slides_sit_below_the_box(page, slides_url):
    """An exempel's Slides sit below its box."""
    open_card_panel(page, slides_url, "Rad gånger kolonn")
    assert top(page.locator("#slides")) >= bottom(box(page))


def test_source_link_sits_below_the_box(page, render_outline):
    """The Source link sits below the box."""
    open_card_panel(page, render_outline(under_a_slide(solved())), "Rad gånger kolonn")
    assert top(page.locator("#panel-source")) >= bottom(box(page))


def test_panel_shows_slides_in_slide_order(page, slides_url):
    """A node's Slides show top to bottom in Slide order, whatever order the Outline listed them."""
    open_panel(page, slides_url, "Gauss")
    images = panel_images(page)
    alts = [images.nth(i).get_attribute("alt") for i in range(images.count())]
    tops = [images.nth(i).bounding_box()["y"] for i in range(images.count())]
    assert [alt for _, alt in sorted(zip(tops, alts))] == ["Slide 1", "Slide 3"]


def test_panel_captions_each_slide(page, slides_url):
    """Each Slide in the panel carries a visible `Slide N` caption."""
    open_panel(page, slides_url, "Gauss")
    assert page.locator("#panel").get_by_text("Slide 3", exact=True).is_visible()


def test_panel_slides_sit_below_the_explanation(page, slides_url):
    """The slide area starts below the explanation."""
    open_panel(page, slides_url, "Gauss")
    explanation = page.locator("#explanation").bounding_box()
    assert panel_images(page).first.bounding_box()["y"] >= explanation["y"] + explanation["height"]


def test_panel_slides_sit_above_the_source_link(page, slides_url):
    """The slide area ends above the Source link."""
    open_panel(page, slides_url, "Gauss")
    last = panel_images(page).last.bounding_box()
    assert last["y"] + last["height"] <= page.locator("#panel-source").bounding_box()["y"]


def test_node_without_slides_shows_no_slide_area(page, slides_url):
    """A node with no Slide numbers shows its panel with no Slides in it."""
    open_panel(page, slides_url, "Matriser")
    assert panel_images(page).count() == 0


def test_panel_slides_load_without_network(page, slides_url):
    """With every network request blocked, each Slide in the panel still loads from the page itself."""
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort())
    open_panel(page, slides_url, "Gauss")
    loaded = panel_images(page).evaluate_all("images => images.map(image => image.complete && image.naturalWidth > 0)")
    assert loaded == [True, True]


@pytest.fixture
def deck_url(deck: Path, cache_dir: Path, tmp_path: Path):
    """The page for main topic Matriser and topic Gauss on Slide 2, rendered against the three-page Deck read on its own."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    outline = node("main-topic", "Matriser", node("topic", "Gauss", slides=[2]))
    return render_deck_mindmap(deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path).page.as_uri()


def test_deck_page_panel_shows_a_marked_slide(page, deck_url):
    """On a page rendered from a Deck alone, a node's panel shows the Slide it lists."""
    open_panel(page, deck_url, "Gauss")
    assert panel_images(page).evaluate_all("images => images.map(image => image.alt)") == ["Slide 2"]


def test_deck_page_panel_has_no_source_link(page, deck_url):
    """On a page rendered from a Deck alone, a node's panel shows no Source link."""
    open_panel(page, deck_url, "Gauss")
    assert page.locator("#panel-source").is_visible() is False


# A shared term links to every place it appears

def shared_outline(second: dict | None = None, *more_topics: dict) -> dict:
    """Topic A with slide Definition holding Matrisprodukt at 0:01, topic B with slide Räkning holding `second`, then `more_topics`.

    `second` defaults to Matrisprodukt at 0:03.
    """
    first = term("Matrisprodukt", stamps=["0:01"], explanation="Rad gånger kolonn.")
    second = second or term("Matrisprodukt", stamps=["0:03"], explanation="Summan av produkterna.")
    return node(
        "main-topic",
        "Matriser",
        node("topic", "A", node("slide", "Definition", first)),
        node("topic", "B", node("slide", "Räkning", second)),
        *more_topics,
    )


def copy_entries(page) -> list[str]:
    return page.locator("#copies li").all_text_contents()


def copy_links(page):
    return page.locator("#copies").get_by_role("link")


def open_copy(page, url: str, index: int = 0) -> None:
    """Show every node and open the panel of the `index`th node labelled Matrisprodukt."""
    show_every_node(page, url)
    page.get_by_role("button", name="Explore Matrisprodukt", exact=True).nth(index).dispatch_event("click")


def test_shared_term_lists_every_copy_as_topic_and_slide(page, render_outline):
    """A term under two slide nodes lists both copies in its panel as topic › slide."""
    open_copy(page, render_outline(shared_outline()))
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]


def test_copy_panel_shows_its_own_explanation_beside_the_list(page, render_outline):
    """Clicking the second copy shows that copy's explanation along with the list of copies."""
    open_copy(page, render_outline(shared_outline()), 1)
    assert (page.locator("#explanation").text_content(), len(copy_entries(page))) == ("Summan av produkterna.", 2)


def test_each_copy_entry_is_in_its_topics_colour(page, render_outline):
    """Each entry in the list is drawn in its own topic's colour."""
    open_copy(page, render_outline(shared_outline()))
    topics = group_colours(page)
    entries = page.locator("#copies li").evaluate_all("items => items.map(item => getComputedStyle(item).color)")
    assert entries == [topics["A"], topics["B"]]


def test_each_copy_entry_links_to_its_copys_stamp(page, render_outline):
    """Each entry links to the second its own copy's stamp names."""
    open_copy(page, render_outline(shared_outline()))
    hrefs = copy_links(page).evaluate_all("links => links.map(link => link.href)")
    assert [href.rsplit("#", 1)[1] for href in hrefs] == ["t=1", "t=3"]


def test_clicking_a_copy_entry_opens_the_source_at_its_moment(page, render_outline):
    """Clicking an entry opens the Source at the moment that copy's stamp names."""
    open_copy(page, render_outline(shared_outline()))
    with page.expect_popup() as popup:
        copy_links(page).nth(1).click()
    assert popup.value.url.endswith("#t=3")


@pytest.mark.parametrize(
    "more_topics",
    [
        [node("topic", "Matrisprodukt")],
        [node("topic", "C", node("slide", "Övningar", worked("exempel", "Matrisprodukt")))],
        [node("topic", "C", node("slide", "Matrisprodukt"))],
    ],
    ids=["topic", "exempel", "slide"],
)
def test_only_term_nodes_count_as_copies(page, render_outline, more_topics):
    """A topic, exempel or slide node labelled like the term is not listed among its copies."""
    open_copy(page, render_outline(shared_outline(None, *more_topics)))
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]


def test_copies_match_by_label_ignoring_case_and_spaces(page, render_outline):
    """Term nodes whose labels differ only in case and runs of whitespace are listed as copies of one term."""
    outline = node(
        "main-topic",
        "Matriser",
        node("topic", "A", node("slide", "Definition", term("Rad gånger kolonn"))),
        node("topic", "B", node("slide", "Räkning", term("rad  gånger kolonn"))),
    )
    show_every_node(page, render_outline(outline))
    page.locator(".node-label").filter(has_text=re.compile("^Rad gånger kolonn$")).dispatch_event("click")
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]


def test_copy_without_a_stamp_is_listed_without_a_link(page, render_outline):
    """A copy with no stamp appears in the list with its topic and slide but no link."""
    open_copy(page, render_outline(shared_outline(term("Matrisprodukt"))))
    assert (copy_entries(page), copy_links(page).count()) == (["A › Definition", "B › Räkning"], 1)


def test_term_that_appears_once_shows_one_link_and_no_list(page, render_outline):
    """A term with no copies shows the single Source link and no list of copies."""
    once = node("main-topic", "Matriser", node("topic", "A", node("slide", "Definition", term("Matrisprodukt", stamps=["0:01"]))))
    open_copy(page, render_outline(once))
    assert (page.locator("#panel-source").is_visible(), copy_entries(page)) == (True, [])


def test_two_copies_under_one_slide_both_appear(page, render_outline):
    """Two copies under the same slide node both appear in the list."""
    copies = [term("Matrisprodukt", stamps=["0:01"]), term("Matrisprodukt", stamps=["0:03"])]
    outline = node("main-topic", "Matriser", node("topic", "A", node("slide", "Definition", *copies)))
    open_copy(page, render_outline(outline))
    assert copy_entries(page) == ["A › Definition", "A › Definition"]


TEMPLATE_TOKEN_LABEL = "Matriser __CSS__ __JS__"
TEMPLATE_TOKEN_EXPLANATION = "Radoperationer __TITLE__ __DATA__"


@pytest.fixture
def template_token_url(render_outline):
    return render_outline(node("main-topic", TEMPLATE_TOKEN_LABEL, explanation=TEMPLATE_TOKEN_EXPLANATION))


def test_label_with_template_tokens_shows_as_written(page, template_token_url):
    """A label holding the page template's tokens shows on its card exactly as written."""
    page.goto(template_token_url)
    assert page.locator(".node-label").first.text_content() == TEMPLATE_TOKEN_LABEL


def test_explanation_with_template_tokens_shows_as_written(page, template_token_url):
    """An explanation holding the page template's tokens shows in the panel exactly as written."""
    page.goto(template_token_url)
    page.get_by_role("button", name=f"Explore {TEMPLATE_TOKEN_LABEL}", exact=True).click()
    assert page.locator("#explanation").text_content() == TEMPLATE_TOKEN_EXPLANATION
