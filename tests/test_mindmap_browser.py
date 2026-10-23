import colorsys
import re
from itertools import combinations
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from klang_notes.core import Fragment, render_mindmap, transcribe


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
def mindmap_url(source: Path, cache_dir: Path, tmp_path: Path, outline):
    transcript = transcribe(
        source,
        cache_dir=cache_dir,
        recognize=lambda wav: [Fragment(0, 1, "En föreläsning.")],
    )
    return render_mindmap(
        transcript.transcript_id,
        outline,
        cache_dir=cache_dir,
        output_dir=tmp_path,
    ).page.as_uri()


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
def test_expanded_nodes_do_not_overlap(page, mindmap_url, style, outline, node_count):
    page.goto(f"{mindmap_url}?variant={style}")
    page.get_by_role("button", name="Show whole Mindmap", exact=True).click()
    boxes = node_boxes(page)
    assert len(boxes) == node_count
    for first, second in combinations(boxes, 2):
        assert (
            first["x"] + first["width"] <= second["x"]
            or second["x"] + second["width"] <= first["x"]
            or first["y"] + first["height"] <= second["y"]
            or second["y"] + second["height"] <= first["y"]
        ), f"{first['label']} overlaps {second['label']}"


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
    for box in before:
        assert after[box["label"]] == box


MIN_DISTINCT_GROUPS = 15
MANY_GROUPS_OUTLINE = "# Lecture\n" + "".join(
    f"## Group {number}\n" for number in range(1, MIN_DISTINCT_GROUPS + 1)
)


def hue(colour: str) -> float:
    red, green, blue = (int(part) / 255 for part in re.findall(r"\d+", colour)[:3])
    return colorsys.rgb_to_hls(red, green, blue)[0] * 360


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


@pytest.mark.parametrize("outline", [MANY_GROUPS_OUTLINE], ids=["many-groups"])
def test_at_least_fifteen_groups_get_clearly_different_hues(page, mindmap_url):
    """Fifteen groups get hues at least 20 degrees apart around the colour wheel."""
    page.goto(mindmap_url)
    colours = group_colours(page)
    hues = [hue(colour) for label, colour in colours.items() if label != "Lecture"]
    assert len(hues) == MIN_DISTINCT_GROUPS
    for first, second in combinations(hues, 2):
        gap = abs(first - second) % 360
        assert min(gap, 360 - gap) >= 20, f"hues {first:.0f} and {second:.0f} too close"


@pytest.mark.parametrize("outline", [MANY_GROUPS_OUTLINE], ids=["many-groups"])
def test_main_topic_colour_differs_from_every_group(page, mindmap_url):
    page.goto(mindmap_url)
    colours = group_colours(page)
    main_topic = colours.pop("Lecture")
    assert main_topic not in colours.values()


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


def test_mindmap_opens_in_radial_rings(page, mindmap_url):
    page.goto(mindmap_url)
    page.get_by_role("button", name="Mindmap settings").click()
    assert page.get_by_role("radio", name="Radial rings").is_checked()
    assert page.locator("body").get_attribute("data-variant") == "A"


@pytest.mark.parametrize("outline", [DEMO_OUTLINE], ids=["demo"])
def test_opening_view_shows_every_group_with_a_readable_label(page, mindmap_url):
    page.goto(mindmap_url)
    sizes = on_screen_label_sizes(page, 1)
    assert len(sizes) == 6
    assert [size for size in sizes if size["px"] < MIN_READABLE_LABEL_PX] == []
    assert [
        label for label in boxes_outside_canvas(page)
        if label in {size["label"] for size in sizes}
    ] == []


@pytest.mark.parametrize("style", ["C", "A"], ids=["topic-circles", "radial-rings"])
@pytest.mark.parametrize("outline", [DEMO_OUTLINE], ids=["demo"])
def test_show_whole_mindmap_fits_every_node_on_screen(page, mindmap_url, style):
    page.goto(f"{mindmap_url}?variant={style}")
    page.get_by_role("button", name="Show whole Mindmap", exact=True).click()
    assert boxes_outside_canvas(page) == []
