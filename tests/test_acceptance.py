import asyncio
import base64
import json
from pathlib import Path

import pytest
from mcp import Client
from playwright.sync_api import sync_playwright

from munin.core import (
    DeckError,
    Fragment,
    Slide,
    UnknownTranscriptError,
    UnlinkedSlide,
    Vocabulary,
    read_slides,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
SLIDE_TEXTS = ["Matriser", "Gausselimination", "Determinant"]


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def write_pdf(path: Path, pages: list[str]) -> Path:
    """Write a PDF with one page per string, each page showing its string in Helvetica."""
    page_count = len(pages)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{4 + 2 * i} 0 R".encode() for i in range(page_count))
        + f"] /Count {page_count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, text in enumerate(pages):
        stream = f"BT /F1 36 Tf 72 300 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 640 480] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * index} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    body = b"%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + content + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


@pytest.fixture
def deck(tmp_path: Path) -> Path:
    """A three-page Deck whose Slides read Matriser, Gausselimination and Determinant."""
    return write_pdf(tmp_path / "decks" / "matriser.pdf", SLIDE_TEXTS)


@pytest.fixture
def transcript_id(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


@pytest.fixture
def attach(transcript_id: str, deck: Path, cache_dir: Path):
    """Read `deck` and attach it to `transcript_id`, returning its Slides.

    A function rather than the Slides themselves, so a missing behaviour fails
    the test instead of erroring its setup.
    """
    return lambda: read_slides(transcript_id, deck, cache_dir=cache_dir)


def render(transcript_id: str, outline: str, cache_dir: Path, tmp_path: Path):
    return render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")


def page_text(transcript_id: str, outline: str, cache_dir: Path, tmp_path: Path) -> str:
    return render(transcript_id, outline, cache_dir, tmp_path).page.read_text(encoding="utf-8")


def encoded(slide: Slide) -> str:
    return base64.b64encode(slide.image).decode()


def labels_in(text: str) -> list[str]:
    return [node["label"] for node in json.JSONDecoder().raw_decode(text.split("const DATA = ", 1)[1])[0]]


# read_slides


def test_read_slides_numbers_slides_from_one(attach):
    """Slides are numbered from 1 in page order."""
    slides = attach()
    assert [slide.number for slide in slides] == [1, 2, 3]


def test_read_slides_returns_each_slides_text(attach):
    """Each Slide carries its page's extracted text."""
    slides = attach()
    assert [slide.text.strip() for slide in slides] == SLIDE_TEXTS


def test_read_slides_returns_png_images(attach):
    """Each Slide's image is PNG bytes."""
    slides = attach()
    assert [slide.image[:8] for slide in slides] == [PNG_SIGNATURE] * 3


@pytest.mark.parametrize(
    "contents, reason",
    [(None, "not a file"), (b"not a pdf at all", "not a readable PDF"), ([], "has no pages")],
    ids=["missing", "unreadable", "zero-pages"],
)
def test_read_slides_on_bad_deck_raises_deck_error(
    transcript_id: str, cache_dir: Path, tmp_path: Path, contents, reason: str
):
    """A missing, unreadable or zero-page PDF raises `DeckError` with the matching reason."""
    path = tmp_path / "bad.pdf"
    if isinstance(contents, bytes):
        path.write_bytes(contents)
    elif contents is not None:
        write_pdf(path, contents)
    with pytest.raises(DeckError) as error:
        read_slides(transcript_id, path, cache_dir=cache_dir)
    assert error.value.reason == reason


def test_deck_error_names_the_path_as_given(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """`DeckError.path` is the Deck path as the caller gave it."""
    given = str(tmp_path / "missing.pdf")
    with pytest.raises(DeckError) as error:
        read_slides(transcript_id, given, cache_dir=cache_dir)
    assert error.value.path == given


def test_read_slides_with_unknown_transcript_raises(deck: Path, cache_dir: Path):
    """An unknown Transcript ID raises `UnknownTranscriptError`."""
    with pytest.raises(UnknownTranscriptError):
        read_slides("deadbeef0000", deck, cache_dir=cache_dir)


def test_unknown_transcript_is_checked_before_the_deck(cache_dir: Path, tmp_path: Path):
    """An unknown Transcript ID with a missing Deck raises `UnknownTranscriptError`, not `DeckError`."""
    with pytest.raises(UnknownTranscriptError):
        read_slides("deadbeef0000", tmp_path / "missing.pdf", cache_dir=cache_dir)


def test_failed_read_attaches_nothing(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """After a failed read on a Transcript with no Deck, its slide markers come back as `no_deck`."""
    with pytest.raises(DeckError):
        read_slides(transcript_id, tmp_path / "missing.pdf", cache_dir=cache_dir)
    result = render(transcript_id, "# Matriser\n- Gauss [slide 1]", cache_dir, tmp_path)
    assert [entry.reason for entry in result.unlinked_slides] == ["no_deck"]


def test_failed_read_keeps_the_earlier_deck(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A failed read leaves the Deck attached before, so its Slides still reach the page."""
    slides = attach()
    with pytest.raises(DeckError):
        read_slides(transcript_id, tmp_path / "missing.pdf", cache_dir=cache_dir)
    assert encoded(slides[1]) in page_text(transcript_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


def test_reading_a_new_deck_replaces_the_old_one(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """After a two-page Deck replaces a three-page one, `[slide 3]` is past the end."""
    attach()
    read_slides(transcript_id, write_pdf(tmp_path / "short.pdf", ["Ett", "Två"]), cache_dir=cache_dir)
    result = render(transcript_id, "# Matriser\n- Gauss [slide 3]", cache_dir, tmp_path)
    assert result.unlinked_slides == (UnlinkedSlide("Gauss [slide 3]", "[slide 3]", "past_end"),)


def test_attached_deck_survives_deleting_the_pdf(
    transcript_id: str, deck: Path, attach, cache_dir: Path, tmp_path: Path
):
    """The page shows a Slide even after the PDF it was read from is deleted."""
    slides = attach()
    deck.unlink()
    assert encoded(slides[1]) in page_text(transcript_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


def test_transcribing_again_with_a_vocabulary_keeps_the_deck(
    source: Path, transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A Vocabulary rerun of the Source keeps its Transcript's Deck attached."""
    slides = attach()
    transcribe(source, vocabulary=Vocabulary(["Gausselimination"]), cache_dir=cache_dir, recognize=one_sentence)
    assert encoded(slides[1]) in page_text(transcript_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


# render_mindmap with slide markers


def test_linked_slide_marker_leaves_the_label(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A marker naming one of the Deck's Slides is removed from the node's label."""
    attach()
    text = page_text(transcript_id, "# Matriser\n- Gauss [0:02] [slide 2]", cache_dir, tmp_path)
    assert labels_in(text) == ["Matriser", "Gauss"]


def test_listed_slide_image_is_embedded(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """The page embeds the image of a Slide a node lists."""
    slides = attach()
    assert encoded(slides[1]) in page_text(transcript_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


def test_capitalised_slide_marker_links(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """`[Slide 2]` links Slide 2 the same as `[slide 2]`."""
    slides = attach()
    assert encoded(slides[1]) in page_text(transcript_id, "# Matriser\n- Gauss [Slide 2]", cache_dir, tmp_path)


def test_unlisted_slide_is_not_embedded(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """The page embeds no image of a Slide that no node lists."""
    slides = attach()
    assert encoded(slides[2]) not in page_text(transcript_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


def test_slide_on_two_nodes_is_embedded_once(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A Slide listed on two nodes appears in the page exactly once."""
    slides = attach()
    text = page_text(transcript_id, "# Matriser\n- Gauss [slide 2]\n- Rang [slide 2]", cache_dir, tmp_path)
    assert text.count(encoded(slides[1])) == 1


def test_slide_listed_twice_on_one_node_is_not_reported(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A Slide listed twice on one node links and is not reported."""
    attach()
    result = render(transcript_id, "# Matriser\n- Gauss [slide 2] [slide 2]", cache_dir, tmp_path)
    assert result.unlinked_slides == ()


def test_slide_past_deck_end_is_reported(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A marker past the Deck's last Slide comes back as `past_end` with its label and marker."""
    attach()
    result = render(transcript_id, "# Matriser\n- Gauss [slide 4]", cache_dir, tmp_path)
    assert result.unlinked_slides == (UnlinkedSlide("Gauss [slide 4]", "[slide 4]", "past_end"),)


def test_unlinked_slide_marker_stays_in_the_label(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A marker that does not link stays in the node's label as plain text."""
    attach()
    text = page_text(transcript_id, "# Matriser\n- Gauss [slide 4]", cache_dir, tmp_path)
    assert labels_in(text) == ["Matriser", "Gauss [slide 4]"]


@pytest.mark.parametrize("marker", ["[slide 0]", "[slide x]", "[slide 3-5]", "[slide]", "[Slide -1]"])
def test_malformed_slide_marker_is_reported(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path, marker: str
):
    """A marker that is not `slide` and a positive whole number comes back as `malformed`."""
    attach()
    result = render(transcript_id, f"# Matriser\n- Gauss {marker}", cache_dir, tmp_path)
    assert result.unlinked_slides == (UnlinkedSlide(f"Gauss {marker}", marker, "malformed"),)


def test_slide_marker_without_deck_is_reported_as_no_deck(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """On a Transcript with no Deck, every marker comes back as `no_deck`, whatever its shape."""
    result = render(transcript_id, "# Matriser\n- Gauss [slide 1]\n- Rang [slide x]", cache_dir, tmp_path)
    assert [entry.reason for entry in result.unlinked_slides] == ["no_deck", "no_deck"]


def test_slide_marker_in_prose_is_not_reported(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A marker in a node's explanation prose is neither linked nor reported."""
    attach()
    result = render(transcript_id, "# Matriser\n- Gauss [slide 2]\n  Se även [slide 9].", cache_dir, tmp_path)
    assert result.unlinked_slides == ()


def test_unlinked_slides_follow_outline_order(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """Bad markers come back in Outline order, left to right within a label."""
    attach()
    outline = "# Matriser\n- Gauss [slide 9] [slide x]\n- Rang [slide 0]"
    result = render(transcript_id, outline, cache_dir, tmp_path)
    assert [entry.slide for entry in result.unlinked_slides] == ["[slide 9]", "[slide x]", "[slide 0]"]


def test_good_slide_marker_beside_bad_one_still_links(
    transcript_id: str, attach, cache_dir: Path, tmp_path: Path
):
    """A good marker on the same node as a bad one still embeds its Slide."""
    slides = attach()
    text = page_text(transcript_id, "# Matriser\n- Gauss [slide 2] [slide 9]", cache_dir, tmp_path)
    assert encoded(slides[1]) in text


# The panel in the browser


@pytest.fixture
def browser():
    """A browser per test, since a browser kept for the module holds an event loop the MCP tests' `asyncio.run` refuses."""
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
def outline() -> str:
    return "# Matriser\n- Gauss [slide 3] [slide 1]\n  Radoperationer ger trappform."


@pytest.fixture
def mindmap(transcript_id: str, attach, cache_dir: Path, tmp_path: Path, outline: str):
    """Attach the Deck, render `outline`, and return the page's URL, as a function called inside the test."""

    def url() -> str:
        attach()
        return render(transcript_id, outline, cache_dir, tmp_path).page.as_uri()

    return url


def open_panel(page, url: str, label: str) -> None:
    page.goto(url)
    page.get_by_role("button", name=f"Explore {label}", exact=True).dispatch_event("click")


def panel_images(page):
    return page.locator("#panel").get_by_role("img")


def test_panel_shows_slides_in_slide_order(page, mindmap):
    """A node's Slides show top to bottom in Slide order, whatever order the Outline listed them."""
    open_panel(page, mindmap(), "Gauss")
    images = panel_images(page)
    alts = [images.nth(i).get_attribute("alt") for i in range(images.count())]
    tops = [images.nth(i).bounding_box()["y"] for i in range(images.count())]
    assert [alt for _, alt in sorted(zip(tops, alts))] == ["Slide 1", "Slide 3"]


def test_panel_captions_each_slide(page, mindmap):
    """Each Slide in the panel carries a visible `Slide N` caption."""
    open_panel(page, mindmap(), "Gauss")
    assert page.locator("#panel").get_by_text("Slide 3", exact=True).is_visible()


def test_panel_slides_sit_below_the_explanation(page, mindmap):
    """The slide area starts below the explanation."""
    open_panel(page, mindmap(), "Gauss")
    explanation = page.locator("#explanation").bounding_box()
    assert panel_images(page).first.bounding_box()["y"] >= explanation["y"] + explanation["height"]


def test_panel_slides_sit_above_the_source_link(page, mindmap):
    """The slide area ends above the Source link."""
    open_panel(page, mindmap(), "Gauss")
    last = panel_images(page).last.bounding_box()
    assert last["y"] + last["height"] <= page.locator("#panel-source").bounding_box()["y"]


def test_node_without_slides_shows_no_slide_area(page, mindmap):
    """A node with no Slide numbers shows its panel with no Slides in it."""
    open_panel(page, mindmap(), "Matriser")
    assert panel_images(page).count() == 0


@pytest.mark.parametrize("outline", ["# Matriser\n- Gauss [slide 2] [slide 2]"], ids=["twice"])
def test_slide_listed_twice_on_one_node_shows_once(page, mindmap):
    """A Slide listed twice on one node shows once in its panel."""
    open_panel(page, mindmap(), "Gauss")
    assert panel_images(page).count() == 1


def test_panel_slides_load_without_network(page, mindmap):
    """With every network request blocked, each Slide in the panel still loads from the page itself."""
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith("file:") else route.abort())
    open_panel(page, mindmap(), "Gauss")
    loaded = panel_images(page).evaluate_all("images => images.map(image => image.complete && image.naturalWidth > 0)")
    assert loaded == [True, True]


# The MCP adapter


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def tool_description(server, name: str) -> str:
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    return next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)


def prompt_text(server, arguments: dict) -> str:
    async def run():
        async with Client(server) as client:
            return await client.get_prompt("lecture_to_mindmap", arguments)

    return asyncio.run(run()).messages[0].content.text


def test_mcp_read_slides_returns_a_text_then_an_image_block_per_slide(
    transcript_id: str, deck: Path, cache_dir: Path
):
    """The read_slides tool returns a text block then an image block for each Slide, in Slide order."""
    result = call(create_server(cache_dir=cache_dir), "read_slides", {"transcript_id": transcript_id, "deck": str(deck)})
    assert [block.type for block in result.content] == ["text", "image"] * 3


def test_mcp_read_slides_text_block_names_the_slide_then_its_text(
    transcript_id: str, deck: Path, cache_dir: Path
):
    """Each text block reads `Slide N:` with the Slide's text on the next line."""
    result = call(create_server(cache_dir=cache_dir), "read_slides", {"transcript_id": transcript_id, "deck": str(deck)})
    assert result.content[2].text.startswith("Slide 2:\nGausselimination")


def test_mcp_read_slides_image_block_is_png(transcript_id: str, deck: Path, cache_dir: Path):
    """Each image block is a PNG."""
    result = call(create_server(cache_dir=cache_dir), "read_slides", {"transcript_id": transcript_id, "deck": str(deck)})
    assert result.content[1].mime_type == "image/png"


def test_mcp_read_slides_bad_deck_error_names_the_path(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """A bad Deck comes back as a tool error that names the Deck path."""
    missing = str(tmp_path / "missing.pdf")
    result = call(create_server(cache_dir=cache_dir), "read_slides", {"transcript_id": transcript_id, "deck": missing})
    assert missing in result.content[0].text


def test_mcp_render_mindmap_reports_unlinked_slides(transcript_id: str, cache_dir: Path, tmp_path: Path):
    """The render_mindmap tool returns each unlinked slide marker's label, slide and reason."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path / "out")
    result = call(server, "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser\n- Gauss [slide 1]"})
    assert result.structured_content["unlinked_slides"] == [
        {"label": "Gauss [slide 1]", "slide": "[slide 1]", "reason": "no_deck"}
    ]


def test_mcp_render_description_gives_the_slide_marker_format(cache_dir: Path):
    """The render tool's description tells the LLM to write `[slide N]` markers."""
    assert "[slide N]" in tool_description(create_server(cache_dir=cache_dir), "render_mindmap")


def test_mcp_lecture_prompt_with_deck_carries_the_deck_path(cache_dir: Path):
    """With a Deck, the prompt's text carries the Deck path."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"source": "lecture.m4a", "deck": "/tmp/matriser.pdf"})
    assert "/tmp/matriser.pdf" in text


def test_mcp_lecture_prompt_with_deck_reads_slides_between_transcript_and_render(cache_dir: Path):
    """With a Deck, the prompt names read_slides after get_transcript and before render_mindmap."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"source": "lecture.m4a", "deck": "/tmp/matriser.pdf"})
    positions = [text.find(f"`{tool}`") for tool in ("get_transcript", "read_slides", "render_mindmap")]
    assert positions == sorted(positions)


def test_mcp_lecture_prompt_without_deck_skips_read_slides(cache_dir: Path):
    """With no Deck, the prompt never names read_slides or asks for Slide numbers."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"source": "lecture.m4a"})
    assert "read_slides" not in text and "Slide" not in text


def test_mcp_lecture_prompt_with_deck_asks_to_match_slides(cache_dir: Path):
    """With a Deck, the prompt asks the LLM to match Slides to the part of the Transcript covering them."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"source": "lecture.m4a", "deck": "/tmp/matriser.pdf"})
    assert "Match each Slide to the part of the Transcript" in text


def test_mcp_lecture_prompt_with_deck_asks_for_slide_numbers_on_nodes(cache_dir: Path):
    """With a Deck, the prompt asks the LLM to put the matching Slide numbers on each node."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"source": "lecture.m4a", "deck": "/tmp/matriser.pdf"})
    assert "Slide numbers on each node" in text
