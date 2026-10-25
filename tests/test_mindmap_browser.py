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
