import math
from itertools import combinations
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munin.core import Fragment, render_mindmap, transcribe


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

EXAMPLE_OUTLINE = """# Föreläsning
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

# World positions Radial rings gave RADIAL_OUTLINE before this change.
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
    parents = outline_parents(EXAMPLE_OUTLINE)
    open_topic_circles(page, render_outline(EXAMPLE_OUTLINE))
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


def test_radial_rings_positions_do_not_change(page, render_outline):
    """Radial rings places every node where it placed it before this change."""
    page.goto(f"{render_outline(RADIAL_OUTLINE)}?variant=A&depth=all")
    centres = node_centres(page)
    assert {label: (round(c["x"], 1), round(c["y"], 1)) for label, c in centres.items()} == RADIAL_POSITIONS
