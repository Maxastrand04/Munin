"""Acceptance tests for #27: examples and exercises are orange on the Mindmap."""

import colorsys
import re
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from munin.core import Fragment, render_mindmap, transcribe

ORANGE_HUES = (25, 45)
MIN_ORANGE_SATURATION = 0.5
MIN_HUE_GAP = 20
MANY_TOPICS = 40

# Topic A is the first topic, which today gets green, far from orange.
EXAMPLE_OUTLINE = """# Matriser
## A
### Begrepp
### Exempel: Rad gånger kolonn
#### Steg 1
"""


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
def open_mindmap(source: Path, cache_dir: Path, tmp_path: Path, page):
    """Render an Outline, open its page with every node shown, and return the page."""
    transcript = transcribe(
        source,
        cache_dir=cache_dir,
        recognize=lambda wav, vocabulary: [Fragment(0, 1, "En föreläsning.")],
    )

    def open_(outline: str, name: str = "mindmap"):
        url = render_mindmap(
            transcript.transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / name
        ).page.as_uri()
        page.goto(f"{url}?depth=all")
        return page

    return open_


def hue_and_saturation(colour: str) -> tuple[float, float]:
    red, green, blue = (int(part) / 255 for part in re.findall(r"\d+", colour)[:3])
    hue, _, saturation = colorsys.rgb_to_hls(red, green, blue)
    return hue * 360, saturation


def is_orange(colour: str) -> bool:
    hue, saturation = hue_and_saturation(colour)
    return ORANGE_HUES[0] <= hue <= ORANGE_HUES[1] and saturation >= MIN_ORANGE_SATURATION


def hue_gap(first: float, second: float) -> float:
    gap = abs(first - second) % 360
    return min(gap, 360 - gap)


def node_colour(page, label: str) -> str:
    """The colour a node is drawn in, as `rgb(r, g, b)`."""
    return page.locator(".node", has=page.get_by_role("button", name=f"Explore {label}", exact=True)).evaluate(
        "node => {const probe = document.createElement('span');"
        "probe.style.color = getComputedStyle(node.querySelector('.node-shell')).getPropertyValue('--group');"
        "document.body.append(probe); const colour = getComputedStyle(probe).color; probe.remove();"
        "return colour;}"
    )


def edge_colours(page) -> list[str]:
    return page.locator(".edge").evaluate_all("edges => edges.map(edge => getComputedStyle(edge).stroke)")


def select(page, label: str) -> None:
    page.get_by_role("button", name=f"Explore {label}", exact=True).dispatch_event("click")


# An example or exercise node is orange at any level


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
def test_example_or_exercise_node_is_orange(open_mindmap, prefix, outline):
    """A node whose label starts with `Övning:` or `Exempel:` is orange, at whatever level it sits."""
    page = open_mindmap(outline.format(label=f"{prefix} Rad gånger kolonn"))
    assert is_orange(node_colour(page, f"{prefix} Rad gånger kolonn"))


def test_prefix_matches_in_any_case(open_mindmap):
    """A label starting with `exempel:` in lower case is orange too."""
    page = open_mindmap("# Matriser\n## A\n### exempel: Rad gånger kolonn\n")
    assert is_orange(node_colour(page, "exempel: Rad gånger kolonn"))


def test_prefix_after_a_linked_stamp_is_orange(open_mindmap):
    """A label that shows `Övning:` first once its leading linked stamp leaves it is orange."""
    page = open_mindmap("# Matriser\n## A\n### [0:00] Övning: Rad gånger kolonn\n")
    assert is_orange(node_colour(page, "Övning: Rad gånger kolonn"))


def test_prefix_behind_an_unlinked_stamp_keeps_topic_colour(open_mindmap):
    """A label whose malformed stamp stays in front of `Övning:` keeps its topic's colour."""
    page = open_mindmap("# Matriser\n## A\n### [9:99] Övning: Rad gånger kolonn\n")
    assert node_colour(page, "[9:99] Övning: Rad gånger kolonn") == node_colour(page, "A")


@pytest.mark.parametrize(
    "label",
    ["Om Exempel: rad gånger kolonn", "Övning 2: Rad gånger kolonn", "Övningar: Rad gånger kolonn", "Övning Rad"],
    ids=["not-at-start", "numbered", "plural", "no-colon"],
)
def test_other_labels_keep_topic_colour(open_mindmap, label):
    """A label that does not start with exactly `Övning:` or `Exempel:` keeps its topic's colour."""
    page = open_mindmap(f"# Matriser\n## A\n### {label}\n")
    assert node_colour(page, label) == node_colour(page, "A")


def test_main_topic_stays_neutral_with_example_label(open_mindmap):
    """A main topic labelled `Exempel:` keeps the main topic's neutral colours."""
    plain = node_colour(open_mindmap("# Matriser\n## A\n", "plain"), "Matriser")
    page = open_mindmap("# Exempel: Matriser\n## A\n", "example")
    assert node_colour(page, "Exempel: Matriser") == plain


# Everything under an example or exercise is orange


def test_node_under_example_is_orange(open_mindmap):
    """A node under an `Exempel:` node is orange too."""
    page = open_mindmap(EXAMPLE_OUTLINE)
    assert is_orange(node_colour(page, "Steg 1"))


def test_branch_of_example_topic_is_orange(open_mindmap):
    """Every node under a topic labelled `Övning:` is orange."""
    page = open_mindmap("# Matriser\n## Övning: Rad gånger kolonn\n### Steg 1\n#### Steg 2\n")
    assert is_orange(node_colour(page, "Steg 2"))


def test_sibling_of_example_keeps_topic_colour(open_mindmap):
    """A node next to an `Exempel:` node, not under it, keeps its topic's colour."""
    page = open_mindmap(EXAMPLE_OUTLINE)
    assert node_colour(page, "Begrepp") == node_colour(page, "A")


# Edges


def test_edge_into_top_example_keeps_topic_colour(open_mindmap):
    """Only the edge from one orange node to another is orange when the example sits under a topic."""
    page = open_mindmap(EXAMPLE_OUTLINE)
    assert [is_orange(colour) for colour in edge_colours(page)].count(True) == 1


def test_edges_in_example_topic_branch_are_orange(open_mindmap):
    """Every edge in a topic-level `Övning:` branch is orange, the one from the main topic included."""
    page = open_mindmap("# Matriser\n## Övning: Rad gånger kolonn\n### Steg 1\n")
    assert all(is_orange(colour) for colour in edge_colours(page))


# Topics never get orange


def test_example_topic_takes_no_topic_colour(open_mindmap):
    """A topic after a topic-level `Övning:` gets the colour it would have had without it."""
    alone = node_colour(open_mindmap("# Matriser\n## A\n", "alone"), "A")
    page = open_mindmap("# Matriser\n## Övning: Rad gånger kolonn\n## A\n", "after-example")
    assert node_colour(page, "A") == alone


def test_no_topic_hue_comes_near_orange(open_mindmap):
    """With more topics than the palette holds, every topic's hue is at least 20 degrees from the orange."""
    topics = "".join(f"## Topic {number}\n" for number in range(1, MANY_TOPICS + 1))
    page = open_mindmap(f"# Matriser\n{topics}### Exempel: Rad gånger kolonn\n")
    orange, _ = hue_and_saturation(node_colour(page, "Exempel: Rad gånger kolonn"))
    near = [
        f"Topic {number}"
        for number in range(1, MANY_TOPICS + 1)
        if hue_gap(hue_and_saturation(node_colour(page, f"Topic {number}"))[0], orange) < MIN_HUE_GAP
    ]
    assert near == []


# Selecting an example or exercise


def test_selected_example_fill_is_orange(open_mindmap):
    """A selected `Exempel:` node is filled orange."""
    page = open_mindmap(EXAMPLE_OUTLINE)
    select(page, "Exempel: Rad gånger kolonn")
    card = page.locator(".node", has=page.get_by_role("button", name="Explore Exempel: Rad gånger kolonn", exact=True))
    assert is_orange(card.locator(".node-card").evaluate("card => getComputedStyle(card).backgroundColor"))


def test_selected_example_panel_path_is_orange(open_mindmap):
    """The panel path above a selected `Exempel:` node's title is orange."""
    page = open_mindmap(EXAMPLE_OUTLINE)
    select(page, "Exempel: Rad gånger kolonn")
    assert is_orange(page.locator("#panel-path").evaluate("path => getComputedStyle(path).color"))


def test_selected_example_panel_rule_is_orange(open_mindmap):
    """The rule under a selected `Exempel:` node's panel title is orange."""
    page = open_mindmap(EXAMPLE_OUTLINE)
    select(page, "Exempel: Rad gånger kolonn")
    assert is_orange(page.locator(".panel-rule").evaluate("rule => getComputedStyle(rule).borderTopColor"))
