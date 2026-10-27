import colorsys
import math
import re
from itertools import combinations
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munin.core import Fragment, read_slides, render_mindmap, transcribe


NESTED_OUTLINE = """# Lecture
## Group
### A
#### Leaf A
#### B
##### Leaf B
"""
DEMO_OUTLINE = (
    Path(__file__).resolve().parents[1] / "docs/examples/matriser-outline.md"
).read_text(encoding="utf-8")


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
def render_outline(source: Path, cache_dir: Path, tmp_path: Path):
    """Render an Outline into a folder of its own and return the page's URL."""
    transcript = transcribe(
        source,
        cache_dir=cache_dir,
        recognize=lambda wav, vocabulary: [Fragment(0, 1, "En föreläsning.")],
    )

    def render(outline: str, name: str = "mindmap") -> str:
        return render_mindmap(
            transcript.transcript_id,
            outline,
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
#### Steg 1
"""


def is_orange(colour: str) -> bool:
    hue, saturation = hue_and_saturation(colour)
    return ORANGE_HUES[0] <= hue <= ORANGE_HUES[1] and saturation >= MIN_ORANGE_SATURATION


def show_every_node(page, url: str) -> None:
    page.goto(f"{url}?depth=all")


def edge_colours(page) -> list[str]:
    return page.locator(".edge").evaluate_all("edges => edges.map(edge => getComputedStyle(edge).stroke)")


@pytest.mark.parametrize("prefix", ["Övning:", "Exempel:"])
@pytest.mark.parametrize(
    "outline",
    [
        "# Matriser\n## {label}\n## B\n",
        "# Matriser\n## A\n### {label}\n",
        "# Matriser\n## A\n### Slide\n#### {label}\n",
    ],
    ids=["topic", "slide", "term"],
)
def test_example_or_exercise_node_is_orange(page, render_outline, prefix, outline):
    """A node whose label starts with `Övning:` or `Exempel:` is orange, at whatever level it sits."""
    show_every_node(page, render_outline(outline.format(label=f"{prefix} Rad gånger kolonn")))
    assert is_orange(group_colours(page)[f"{prefix} Rad gånger kolonn"])


def test_prefix_matches_in_any_case(page, render_outline):
    """A label starting with `exempel:` in lower case is orange too."""
    show_every_node(page, render_outline("# Matriser\n## A\n### exempel: Rad gånger kolonn\n"))
    assert is_orange(group_colours(page)["exempel: Rad gånger kolonn"])


def test_prefix_after_a_linked_stamp_is_orange(page, render_outline):
    """A label that shows `Övning:` first once its leading linked stamp leaves it is orange."""
    show_every_node(page, render_outline("# Matriser\n## A\n### [0:00] Övning: Rad gånger kolonn\n"))
    assert is_orange(group_colours(page)["Övning: Rad gånger kolonn"])


def test_prefix_behind_an_unlinked_stamp_keeps_topic_colour(page, render_outline):
    """A label whose malformed stamp stays in front of `Övning:` keeps its topic's colour."""
    show_every_node(page, render_outline("# Matriser\n## A\n### [9:99] Övning: Rad gånger kolonn\n"))
    colours = group_colours(page)
    assert colours["[9:99] Övning: Rad gånger kolonn"] == colours["A"]


@pytest.mark.parametrize(
    "label",
    ["Om Exempel: rad gånger kolonn", "Övning 2: Rad gånger kolonn", "Övningar: Rad gånger kolonn", "Övning Rad"],
    ids=["not-at-start", "numbered", "plural", "no-colon"],
)
def test_other_labels_keep_topic_colour(page, render_outline, label):
    """A label that does not start with exactly `Övning:` or `Exempel:` keeps its topic's colour."""
    show_every_node(page, render_outline(f"# Matriser\n## A\n### {label}\n"))
    colours = group_colours(page)
    assert colours[label] == colours["A"]


def test_main_topic_stays_neutral_with_example_label(page, render_outline):
    """A main topic labelled `Exempel:` keeps the main topic's neutral colours."""
    show_every_node(page, render_outline("# Matriser\n## A\n", "plain"))
    plain = group_colours(page)["Matriser"]
    show_every_node(page, render_outline("# Exempel: Matriser\n## A\n", "example"))
    assert group_colours(page)["Exempel: Matriser"] == plain


def test_node_under_example_is_orange(page, render_outline):
    """A node under an `Exempel:` node is orange too."""
    show_every_node(page, render_outline(EXAMPLE_OUTLINE))
    assert is_orange(group_colours(page)["Steg 1"])


def test_branch_of_example_topic_is_orange(page, render_outline):
    """Every node under a topic labelled `Övning:` is orange."""
    show_every_node(page, render_outline("# Matriser\n## Övning: Rad gånger kolonn\n### Steg 1\n#### Steg 2\n"))
    assert is_orange(group_colours(page)["Steg 2"])


def test_sibling_of_example_keeps_topic_colour(page, render_outline):
    """A node next to an `Exempel:` node, not under it, keeps its topic's colour."""
    show_every_node(page, render_outline(EXAMPLE_OUTLINE))
    colours = group_colours(page)
    assert colours["Begrepp"] == colours["A"]


def test_edge_into_top_example_keeps_topic_colour(page, render_outline):
    """Only the edge from one orange node to another is orange when the example sits under a topic."""
    show_every_node(page, render_outline(EXAMPLE_OUTLINE))
    assert [is_orange(colour) for colour in edge_colours(page)].count(True) == 1


def test_edges_in_example_topic_branch_are_orange(page, render_outline):
    """Every edge in a topic-level `Övning:` branch is orange, the one from the main topic included."""
    show_every_node(page, render_outline("# Matriser\n## Övning: Rad gånger kolonn\n### Steg 1\n"))
    assert all(is_orange(colour) for colour in edge_colours(page))


def test_example_topic_takes_no_topic_colour(page, render_outline):
    """A topic after a topic-level `Övning:` gets the colour it would have had without it."""
    show_every_node(page, render_outline("# Matriser\n## A\n", "alone"))
    alone = group_colours(page)["A"]
    show_every_node(page, render_outline("# Matriser\n## Övning: Rad gånger kolonn\n## A\n", "after-example"))
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
    lines.append("#### Exempel: Steg")
    lines.extend(f"##### Steg {n}" for n in range(1, 4))
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
##### Stor 1
##### Stor 2
##### Stor 3
#### Andel B
#### Andel C
"""

MANY_CHILDREN_OUTLINE = "# Föreläsning\n## Ämne\n### Många\n" + "".join(
    f"#### Många {n}\n" for n in range(1, 21)
)

EXAMPLE_ARC_OUTLINE = """# Föreläsning
## Ämne
### Övning: Räkna
#### Steg 1
#### Steg 2
#### Steg 3
### Slide
#### Exempel: Visa
##### Visa 1
##### Visa 2
"""

RADIAL_OUTLINE = """# Lecture
## Group
### A
#### Leaf A
#### B
##### Leaf B
## Other
### C
### D
"""

# World positions Radial rings gives RADIAL_OUTLINE.
RADIAL_POSITIONS = {
    "Lecture": (0.0, 0.0),
    "Group": (520.0, 0.0),
    "A": (1040.0, 0.0),
    "Leaf A": (1046.5, -795.4),
    "B": (1046.5, 795.4),
    "Leaf B": (1357.6, 1031.8),
    "Other": (-520.0, 0.0),
    "C": (-735.4, 558.9),
    "D": (-735.4, -558.9),
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
    for label in parents:
        depth, parent = 0, parents[label]
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
    for polygon in (first, second):
        for a, b in zip(polygon, polygon[1:] + polygon[:1]):
            normal = (b[1] - a[1], a[0] - b[0])
            project = lambda shape: [normal[0] * x + normal[1] * y for x, y in shape]
            if max(project(first)) <= min(project(second)) or max(project(second)) <= min(project(first)):
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
        for a, b in zip(first, first[1:])
        for c, d in zip(second, second[1:])
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
    gaps = {(a, b): offsets[b] - offsets[a] for a, b in zip(ordered, ordered[1:])}
    beside_big = [gap for pair, gap in gaps.items() if "Andel Stor" in pair]
    between_leaves = [gap for pair, gap in gaps.items() if "Andel Stor" not in pair]
    assert min(beside_big) >= 2 * max(between_leaves)


def test_single_child_points_straight_away_from_the_parent(page, render_outline):
    """A deeper topic's only child sits on the line from that topic's parent through the topic."""
    parents = outline_parents(ARC_OUTLINE)
    open_topic_circles(page, render_outline(ARC_OUTLINE))
    offsets = arc_offsets(node_centres(page), parents, "Ensam")
    assert math.degrees(offsets["Enda"]) == pytest.approx(0, abs=1)


@pytest.mark.parametrize("topic", ["Övning: Räkna", "Exempel: Visa"], ids=["exercise-slide", "example-term"])
def test_example_branch_faces_away_from_its_parent(page, render_outline, topic):
    """The children of an example or exercise sit less than 90 degrees from the direction away from its parent."""
    parents = outline_parents(EXAMPLE_ARC_OUTLINE)
    open_topic_circles(page, render_outline(EXAMPLE_ARC_OUTLINE))
    offsets = arc_offsets(node_centres(page), parents, topic)
    assert max(abs(offset) for offset in offsets.values()) < math.pi / 2


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

SLIDES_OUTLINE = "# Matriser\n- Gauss [slide 3] [slide 1]\n  Radoperationer ger trappform."


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


@pytest.mark.parametrize("slides_outline", ["# Matriser\n- Gauss [slide 2] [slide 2]"], ids=["twice"])
def test_slide_listed_twice_on_one_node_shows_once(page, slides_url):
    """A Slide listed twice on one node shows once in its panel."""
    open_panel(page, slides_url, "Gauss")
    assert panel_images(page).count() == 1


def test_panel_slides_load_without_network(page, slides_url):
    """With every network request blocked, each Slide in the panel still loads from the page itself."""
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort())
    open_panel(page, slides_url, "Gauss")
    loaded = panel_images(page).evaluate_all("images => images.map(image => image.complete && image.naturalWidth > 0)")
    assert loaded == [True, True]


# A shared term links to every place it appears

SHARED_OUTLINE = """# Matriser
## A
### Definition
#### Matrisprodukt [0:01]
Rad gånger kolonn.
## B
### Räkning
#### Matrisprodukt [0:03]
Summan av produkterna.
"""


def copy_entries(page) -> list[str]:
    return page.locator("#copies li").all_text_contents()


def copy_links(page):
    return page.locator("#copies").get_by_role("link")


def open_copy(page, url: str, index: int = 0) -> None:
    """Show every node and open the panel of the `index`th node labelled Matrisprodukt."""
    show_every_node(page, url)
    page.get_by_role("button", name="Explore Matrisprodukt", exact=True).nth(index).dispatch_event("click")


def test_shared_term_lists_every_copy_as_topic_and_slide(page, render_outline):
    """A term under two Slide nodes lists both copies in its panel as topic › Slide."""
    open_copy(page, render_outline(SHARED_OUTLINE))
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]


def test_copies_match_ignoring_case_stamps_and_slide_markers(page, render_outline):
    """Labels that differ only in case, stamps and Slide markers count as copies of one term."""
    outline = SHARED_OUTLINE.replace("#### Matrisprodukt [0:03]", "#### matrisprodukt [slide 2] [9:99]")
    open_copy(page, render_outline(outline))
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]


def test_copy_panel_shows_its_own_explanation_beside_the_list(page, render_outline):
    """Clicking the second copy shows that copy's explanation along with the list of copies."""
    open_copy(page, render_outline(SHARED_OUTLINE), 1)
    assert (page.locator("#explanation").text_content(), len(copy_entries(page))) == ("Summan av produkterna.", 2)


def test_each_copy_entry_is_in_its_topics_colour(page, render_outline):
    """Each entry in the list is drawn in its own topic's colour."""
    open_copy(page, render_outline(SHARED_OUTLINE))
    topics = group_colours(page)
    entries = page.locator("#copies li").evaluate_all("items => items.map(item => getComputedStyle(item).color)")
    assert entries == [topics["A"], topics["B"]]


def test_each_copy_entry_links_to_its_copys_stamp(page, render_outline):
    """Each entry links to the second its own copy's stamp names."""
    open_copy(page, render_outline(SHARED_OUTLINE))
    hrefs = copy_links(page).evaluate_all("links => links.map(link => link.href)")
    assert [href.rsplit("#", 1)[1] for href in hrefs] == ["t=1", "t=3"]


def test_clicking_a_copy_entry_opens_the_source_at_its_moment(page, render_outline):
    """Clicking an entry opens the Source at the moment that copy's stamp names."""
    open_copy(page, render_outline(SHARED_OUTLINE))
    with page.expect_popup() as popup:
        copy_links(page).nth(1).click()
    assert popup.value.url.endswith("#t=3")


@pytest.mark.parametrize(
    "outline",
    [
        SHARED_OUTLINE + "## Matrisprodukt\n",
        SHARED_OUTLINE + "### Matrisprodukt\n",
        SHARED_OUTLINE + "### Exempel: Räkna\n#### Matrisprodukt\n",
        SHARED_OUTLINE + "#### Exempel\n##### Matrisprodukt\n",
    ],
    ids=["topic", "slide", "example", "below-term"],
)
def test_only_term_level_nodes_count_as_copies(page, render_outline, outline):
    """A topic, Slide node, example node or node below the term level with the term's label is not listed."""
    open_copy(page, render_outline(outline))
    assert copy_entries(page) == ["A › Definition", "B › Räkning"]


def test_copy_without_linked_stamp_is_listed_without_a_link(page, render_outline):
    """A copy with no stamp appears in the list with its topic and Slide but no link."""
    outline = SHARED_OUTLINE.replace("#### Matrisprodukt [0:03]", "#### Matrisprodukt")
    open_copy(page, render_outline(outline))
    assert (copy_entries(page), copy_links(page).count()) == (["A › Definition", "B › Räkning"], 1)


def test_copy_with_unlinked_stamp_is_listed_without_a_link(page, render_outline):
    """A copy whose only stamp is unlinked appears in the list with no link."""
    outline = SHARED_OUTLINE.replace("#### Matrisprodukt [0:03]", "#### Matrisprodukt [9:99]")
    open_copy(page, render_outline(outline))
    assert (copy_entries(page), copy_links(page).count()) == (["A › Definition", "B › Räkning"], 1)


def test_term_that_appears_once_shows_one_link_and_no_list(page, render_outline):
    """A term with no copies shows the single Source link and no list of copies."""
    open_copy(page, render_outline("# Matriser\n## A\n### Definition\n#### Matrisprodukt [0:01]\n"))
    assert (page.locator("#panel-source").is_visible(), copy_entries(page)) == (True, [])


def test_two_copies_under_one_slide_both_appear(page, render_outline):
    """Two copies under the same Slide node both appear in the list."""
    outline = "# Matriser\n## A\n### Definition\n#### Matrisprodukt [0:01]\n#### Matrisprodukt [0:03]\n"
    open_copy(page, render_outline(outline))
    assert copy_entries(page) == ["A › Definition", "A › Definition"]
