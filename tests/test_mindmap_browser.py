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
    ).as_uri()


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
    page.get_by_role("button", name="Reveal children of A", exact=True).click()
    after = {box["label"]: box for box in node_boxes(page)}
    for box in before:
        assert after[box["label"]] == box
