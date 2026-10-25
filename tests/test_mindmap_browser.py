import colorsys
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
def mindmap_url(source: Path, cache_dir: Path, tmp_path: Path, outline):
    transcript = transcribe(
        source,
        cache_dir=cache_dir,
        recognize=lambda wav, vocabulary: [Fragment(0, 1, "En föreläsning.")],
    )
    return render_mindmap(
        transcript.transcript_id,
        outline,
        cache_dir=cache_dir,
        output_dir=tmp_path,
    ).page.as_uri()


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
        if min(abs(first - second) % 360, 360 - abs(first - second) % 360) < 20
    ]
    assert close == []


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
