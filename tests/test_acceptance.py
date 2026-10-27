import asyncio
import base64
import hashlib
from pathlib import Path

import pytest
from mcp import Client
from mcp.shared.exceptions import MCPError
from playwright.sync_api import sync_playwright

from munin.core import (
    DeckError,
    Fragment,
    Slide,
    UnknownDeckError,
    Vocabulary,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)
from munin.mcp_server import create_server

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
DECK_PATH = "/tmp/matriser.pdf"


def one_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def render(deck_id: str, outline: str, cache_dir: Path, tmp_path: Path):
    return render_deck_mindmap(deck_id, outline, cache_dir=cache_dir, output_dir=tmp_path / "out")


def page_text(deck_id: str, outline: str, cache_dir: Path, tmp_path: Path) -> str:
    return render(deck_id, outline, cache_dir, tmp_path).page.read_text(encoding="utf-8")


def encoded(slide: Slide) -> str:
    return base64.b64encode(slide.image).decode()


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def prompt_text(server, arguments: dict) -> str:
    async def run():
        async with Client(server) as client:
            return await client.get_prompt("lecture_to_mindmap", arguments)

    return asyncio.run(run()).messages[0].content.text


def prompt_error(server, arguments: dict) -> MCPError | None:
    """Return the MCP error that getting the prompt raises, or None when it succeeds."""

    async def run():
        async with Client(server) as client:
            try:
                await client.get_prompt("lecture_to_mindmap", arguments)
            except MCPError as error:
                return error
            return None

    return asyncio.run(run())


def tool_description(server, name: str) -> str:
    """Return a tool's description with every run of whitespace collapsed to one space."""

    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    description = next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)
    return " ".join(description.split())


def deck_id_of(result) -> str:
    """Return the Deck ID from a `read_deck` tool result's first block."""
    return result.content[0].text.removeprefix("Deck ID: ").strip()


# Reading a Deck on its own


def test_read_deck_numbers_slides_from_one(deck: Path, cache_dir: Path):
    """A Deck read on its own returns its Slides numbered from 1 in page order."""
    assert [slide.number for slide in read_deck(deck, cache_dir=cache_dir).slides] == [1, 2, 3]


def test_read_deck_slides_carry_their_page_text(deck: Path, cache_dir: Path):
    """Each Slide of a Deck read on its own carries its page's text."""
    slides = read_deck(deck, cache_dir=cache_dir).slides
    assert [slide.text.strip() for slide in slides] == ["Matriser", "Gausselimination", "Determinant"]


def test_read_deck_slide_images_are_png(deck: Path, cache_dir: Path):
    """Each Slide of a Deck read on its own carries its page as PNG bytes."""
    slides = read_deck(deck, cache_dir=cache_dir).slides
    assert [slide.image[:8] for slide in slides] == [PNG_SIGNATURE] * 3


def test_read_deck_image_only_page_still_has_an_image(cache_dir: Path, tmp_path: Path, write_deck):
    """A page with no text still comes back as a Slide with a PNG image."""
    path = write_deck(tmp_path / "bilder.pdf", [""])
    assert read_deck(path, cache_dir=cache_dir).slides[0].image[:8] == PNG_SIGNATURE


def test_read_deck_id_comes_from_the_resolved_path(deck: Path, cache_dir: Path):
    """The Deck ID is the first 12 hex characters of the SHA-256 of the resolved PDF path."""
    expected = hashlib.sha256(str(deck.resolve()).encode()).hexdigest()[:12]
    assert read_deck(deck, cache_dir=cache_dir).deck_id == expected


def test_read_deck_expands_home(cache_dir: Path, tmp_path: Path, write_deck, monkeypatch: pytest.MonkeyPatch):
    """A Deck path starting with `~` is read from the home folder."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    write_deck(tmp_path / "home" / "matriser.pdf", ["Matriser"])
    assert len(read_deck("~/matriser.pdf", cache_dir=cache_dir).slides) == 1


def test_read_deck_moved_pdf_gets_a_new_id(deck: Path, cache_dir: Path, tmp_path: Path):
    """The same PDF at a new path is a new Deck with a different ID."""
    first = read_deck(deck, cache_dir=cache_dir).deck_id
    moved = deck.rename(tmp_path / "flyttad.pdf")
    assert read_deck(moved, cache_dir=cache_dir).deck_id != first


@pytest.mark.parametrize(
    "contents, reason",
    [(None, "not a file"), (b"not a pdf at all", "not a readable PDF"), ([], "has no pages")],
    ids=["missing", "unreadable", "zero-pages"],
)
def test_read_deck_bad_deck_raises_deck_error(cache_dir: Path, tmp_path: Path, write_deck, contents, reason: str):
    """A missing, unreadable or zero-page PDF read on its own raises `DeckError` with the matching reason."""
    path = tmp_path / "bad.pdf"
    if isinstance(contents, bytes):
        path.write_bytes(contents)
    elif contents is not None:
        write_deck(path, contents)
    with pytest.raises(DeckError) as error:
        read_deck(path, cache_dir=cache_dir)
    assert error.value.reason == reason


def test_read_deck_failure_keeps_the_earlier_copy(deck: Path, cache_dir: Path, tmp_path: Path):
    """A failed re-read of a path leaves the copy stored before, so its Slides still reach the page."""
    first = read_deck(deck, cache_dir=cache_dir)
    deck.write_bytes(b"not a pdf at all")
    with pytest.raises(DeckError):
        read_deck(deck, cache_dir=cache_dir)
    assert encoded(first.slides[1]) in page_text(first.deck_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


def test_read_deck_again_replaces_the_copy(deck: Path, cache_dir: Path, tmp_path: Path, write_deck):
    """Re-reading the same path replaces the stored copy, and the next render shows the new Slides."""
    read_deck(deck, cache_dir=cache_dir)
    write_deck(deck, ["Vektorer", "Baser"])
    second = read_deck(deck, cache_dir=cache_dir)
    assert encoded(second.slides[1]) in page_text(second.deck_id, "# Vektorer\n- Bas [slide 2]", cache_dir, tmp_path)


def test_read_deck_leaves_an_attached_copy_alone(
    source: Path, deck: Path, cache_dir: Path, tmp_path: Path, write_deck
):
    """Reading a PDF on its own after changing it leaves the copy attached to a Transcript as it was."""
    transcript_id = transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id
    attached = read_slides(transcript_id, deck, cache_dir=cache_dir)
    write_deck(deck, ["Vektorer", "Baser"])
    read_deck(deck, cache_dir=cache_dir)
    page = render_mindmap(
        transcript_id, "# Matriser\n- Gauss [slide 2]", cache_dir=cache_dir, output_dir=tmp_path / "out"
    ).page
    assert encoded(attached[1]) in page.read_text(encoding="utf-8")


def test_read_slides_leaves_a_standalone_copy_alone(
    source: Path, deck: Path, cache_dir: Path, tmp_path: Path, write_deck
):
    """Attaching a PDF to a Transcript after changing it leaves the copy read on its own as it was."""
    standalone = read_deck(deck, cache_dir=cache_dir)
    write_deck(deck, ["Vektorer", "Baser"])
    transcript_id = transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id
    read_slides(transcript_id, deck, cache_dir=cache_dir)
    page = page_text(standalone.deck_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)
    assert encoded(standalone.slides[1]) in page


# Rendering against a standalone Deck


def test_render_deck_mindmap_shows_a_marked_slide(deck: Path, cache_dir: Path, tmp_path: Path):
    """A good `[slide N]` marker puts that Slide's image on the page."""
    result = read_deck(deck, cache_dir=cache_dir)
    assert encoded(result.slides[1]) in page_text(result.deck_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


def test_render_deck_mindmap_links_good_markers(deck: Path, cache_dir: Path, tmp_path: Path):
    """Good `[slide N]` markers are not reported as unlinked."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    assert render(deck_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path).unlinked_slides == ()


def test_render_deck_mindmap_writes_page_named_by_deck_id(deck: Path, cache_dir: Path, tmp_path: Path):
    """The page is `<deck_id>.html` in the output folder."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    assert render(deck_id, "# Matriser", cache_dir, tmp_path).page == (tmp_path / "out" / f"{deck_id}.html").resolve()


def test_render_deck_mindmap_reports_a_stamp_as_no_source(deck: Path, cache_dir: Path, tmp_path: Path):
    """A well-formed stamp comes back as unlinked with reason `no_source`."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    result = render(deck_id, "# Matriser\n- Gauss [1:00]", cache_dir, tmp_path)
    assert [(entry.stamp, entry.reason) for entry in result.unlinked] == [("[1:00]", "no_source")]


def test_render_deck_mindmap_reports_a_malformed_stamp_as_no_source(deck: Path, cache_dir: Path, tmp_path: Path):
    """A malformed stamp also comes back as `no_source`, not `malformed`."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    result = render(deck_id, "# Matriser\n- Gauss [1:75]", cache_dir, tmp_path)
    assert [entry.reason for entry in result.unlinked] == ["no_source"]


def test_render_deck_mindmap_reports_a_marker_past_the_last_slide(deck: Path, cache_dir: Path, tmp_path: Path):
    """A marker past the Deck's last Slide comes back as unlinked with reason `past_end`."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    result = render(deck_id, "# Matriser\n- Gauss [slide 4]", cache_dir, tmp_path)
    assert [entry.reason for entry in result.unlinked_slides] == ["past_end"]


def test_render_deck_mindmap_reports_a_malformed_marker(deck: Path, cache_dir: Path, tmp_path: Path):
    """A malformed marker comes back as unlinked with reason `malformed`."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    result = render(deck_id, "# Matriser\n- Gauss [slide x]", cache_dir, tmp_path)
    assert [entry.reason for entry in result.unlinked_slides] == ["malformed"]


def test_render_deck_mindmap_accepts_a_slide_node_with_no_marker(deck: Path, cache_dir: Path, tmp_path: Path):
    """A Slide node with no marker renders, with nothing reported."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    result = render(deck_id, "# Matriser\n## Rader\n### Gauss\n#### Pivot", cache_dir, tmp_path)
    assert (result.unlinked, result.unlinked_slides) == ((), ())


def test_render_deck_mindmap_page_has_no_lecture_link(deck: Path, cache_dir: Path, tmp_path: Path):
    """The page's header carries no link to a Source."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    assert 'class="source-link"' not in page_text(deck_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path)


def test_render_deck_mindmap_unknown_id_raises(cache_dir: Path, tmp_path: Path):
    """An ID with no Deck read on its own raises `UnknownDeckError`."""
    with pytest.raises(UnknownDeckError):
        render("deadbeef0000", "# Matriser", cache_dir, tmp_path)


def test_unknown_deck_error_message_names_the_id(cache_dir: Path, tmp_path: Path):
    """The `UnknownDeckError` message reads `No Deck with ID <id>`."""
    with pytest.raises(UnknownDeckError) as error:
        render("deadbeef0000", "# Matriser", cache_dir, tmp_path)
    assert str(error.value) == "No Deck with ID deadbeef0000"


def test_render_deck_mindmap_unknown_id_writes_nothing(cache_dir: Path, tmp_path: Path):
    """An unknown Deck ID writes no page."""
    with pytest.raises(UnknownDeckError):
        render("deadbeef0000", "# Matriser", cache_dir, tmp_path)
    assert not (tmp_path / "out" / "deadbeef0000.html").exists()


def test_render_deck_mindmap_panel_has_no_source_link(deck: Path, cache_dir: Path, tmp_path: Path):
    """A node's panel on a slides-only page shows no Source link."""
    deck_id = read_deck(deck, cache_dir=cache_dir).deck_id
    url = render(deck_id, "# Matriser\n- Gauss [slide 2]", cache_dir, tmp_path).page.as_uri()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1200, "height": 800})
        page.goto(url)
        page.get_by_role("button", name="Explore Gauss", exact=True).dispatch_event("click")
        visible = page.locator("#panel-source").is_visible()
        browser.close()
    assert visible is False


# MCP tools


def test_mcp_read_deck_first_block_gives_the_deck_id(deck: Path, cache_dir: Path):
    """The read_deck tool's first block reads `Deck ID: <id>` with the core's Deck ID."""
    result = call(create_server(cache_dir=cache_dir), "read_deck", {"deck": str(deck)})
    assert result.content[0].text == f"Deck ID: {hashlib.sha256(str(deck.resolve()).encode()).hexdigest()[:12]}"


def test_mcp_read_deck_returns_a_text_then_an_image_block_per_slide(deck: Path, cache_dir: Path):
    """After the Deck ID, the read_deck tool returns a text block then an image block per Slide."""
    result = call(create_server(cache_dir=cache_dir), "read_deck", {"deck": str(deck)})
    assert [block.type for block in result.content[1:]] == ["text", "image"] * 3


def test_mcp_read_deck_text_block_names_the_slide_then_its_text(deck: Path, cache_dir: Path):
    """Each Slide's text block reads `Slide N:` with the Slide's text on the next line."""
    result = call(create_server(cache_dir=cache_dir), "read_deck", {"deck": str(deck)})
    assert result.content[3].text.startswith("Slide 2:\nGausselimination")


def test_mcp_read_deck_bad_deck_error_names_the_path(cache_dir: Path, tmp_path: Path):
    """A bad Deck given to read_deck comes back as a tool error that names the Deck path."""
    missing = str(tmp_path / "missing.pdf")
    result = call(create_server(cache_dir=cache_dir), "read_deck", {"deck": missing})
    assert missing in result.content[0].text


def test_mcp_render_deck_mindmap_writes_page(deck: Path, cache_dir: Path, tmp_path: Path):
    """The render_deck_mindmap tool returns the path of the page it wrote."""
    output_dir = tmp_path / "out"
    server = create_server(cache_dir=cache_dir, output_dir=output_dir)
    deck_id = deck_id_of(call(server, "read_deck", {"deck": str(deck)}))
    result = call(server, "render_deck_mindmap", {"deck_id": deck_id, "outline": "# Matriser\n- Gauss [slide 2]"})
    assert result.structured_content["page"] == str(output_dir / f"{deck_id}.html")


def test_mcp_render_deck_mindmap_reports_unlinked_stamps(deck: Path, cache_dir: Path, tmp_path: Path):
    """The render_deck_mindmap tool returns each stamp's label, stamp and reason `no_source`."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path / "out")
    deck_id = deck_id_of(call(server, "read_deck", {"deck": str(deck)}))
    result = call(server, "render_deck_mindmap", {"deck_id": deck_id, "outline": "# Matriser\n- Gauss [1:00]"})
    assert result.structured_content["unlinked"] == [{"label": "Gauss [1:00]", "stamp": "[1:00]", "reason": "no_source"}]


def test_mcp_render_deck_mindmap_unknown_id_error_names_it(cache_dir: Path, tmp_path: Path):
    """The tool error for an unknown ID given to render_deck_mindmap names the ID."""
    server = create_server(cache_dir=cache_dir, output_dir=tmp_path / "out")
    result = call(server, "render_deck_mindmap", {"deck_id": "deadbeef0000", "outline": "# Matriser"})
    assert "deadbeef0000" in result.content[0].text


# The slides-only Outline format


def test_mcp_deck_render_description_asks_for_term_explanations(cache_dir: Path):
    """The slides-only format asks for an explanation under every term node."""
    assert "under every term" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_sizes_explanations(cache_dir: Path):
    """The slides-only format asks for explanations of one to three sentences."""
    assert "one to three sentences" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_keeps_explanations_on_the_slides(cache_dir: Path):
    """The slides-only format asks explanations to cover only what the Slides cover."""
    assert "only what the Slides cover" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_asks_for_one_to_five_topics(cache_dir: Path):
    """The slides-only format asks for 1 to 5 topics."""
    assert "1 to 5 topics" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_groups_by_meaning(cache_dir: Path):
    """The slides-only format asks for topics grouped by meaning."""
    assert "by meaning" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_gives_the_slide_marker_format(cache_dir: Path):
    """The slides-only format gives the `[slide N]` marker format."""
    assert "[slide N]" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_labels_examples_and_exercises(cache_dir: Path):
    """The slides-only format asks for `Övning:` and `Exempel:` leaves."""
    assert "`Övning:` or `Exempel:`" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_writes_out_examples_and_exercises(cache_dir: Path):
    """The slides-only format asks for each example and exercise to be written out."""
    assert "writes out the task" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_asks_for_no_stamps(cache_dir: Path):
    """The slides-only format tells the LLM to write no stamps."""
    assert "no stamps" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


def test_mcp_deck_render_description_skips_title_and_schedule_slides(cache_dir: Path):
    """The slides-only format skips Slides such as a title page or a schedule."""
    assert "title page or a schedule" in tool_description(create_server(cache_dir=cache_dir), "render_deck_mindmap")


# The lecture prompt


def test_mcp_lecture_prompt_with_only_a_deck_gives_read_deck_the_path(cache_dir: Path):
    """With only a Deck, the step that names read_deck carries the Deck path."""
    lines = prompt_text(create_server(cache_dir=cache_dir), {"deck": DECK_PATH}).splitlines()
    assert any("`read_deck`" in line and DECK_PATH in line for line in lines)


def test_mcp_lecture_prompt_with_only_a_deck_reads_then_renders(cache_dir: Path):
    """With only a Deck, the prompt names read_deck before render_deck_mindmap."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"deck": DECK_PATH})
    positions = [text.index(f"`{tool}`") for tool in ("read_deck", "render_deck_mindmap")]
    assert positions == sorted(positions)


def test_mcp_lecture_prompt_with_only_a_deck_never_transcribes(cache_dir: Path):
    """With only a Deck, the prompt never names transcribe."""
    assert "`transcribe`" not in prompt_text(create_server(cache_dir=cache_dir), {"deck": DECK_PATH})


def test_mcp_lecture_prompt_with_only_a_deck_leaves_format_to_render_tool(cache_dir: Path):
    """With only a Deck, the prompt points at render_deck_mindmap for the Outline format."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"deck": DECK_PATH})
    assert "format the `render_deck_mindmap` tool describes" in text


def test_mcp_lecture_prompt_with_only_a_deck_asks_for_only_a_file_link(cache_dir: Path):
    """With only a Deck, the prompt asks, after rendering, for a reply of only a `file://` link to the page."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"deck": DECK_PATH})
    assert text.index("`render_deck_mindmap`") < text.index("only the page as a `file://` link")


def test_mcp_lecture_prompt_with_only_a_deck_reports_a_failed_step(cache_dir: Path):
    """With only a Deck, the prompt asks, after rendering, for a reply naming the failed step and the error."""
    text = prompt_text(create_server(cache_dir=cache_dir), {"deck": DECK_PATH})
    assert text.index("`render_deck_mindmap`") < text.index(
        "If a step fails, reply with only which step failed and the error"
    )


def test_mcp_lecture_prompt_with_neither_is_an_error(cache_dir: Path):
    """With neither a Source nor a Deck, getting the prompt fails with an MCP error."""
    assert prompt_error(create_server(cache_dir=cache_dir), {}) is not None


def test_mcp_lecture_prompt_with_neither_names_what_is_missing(cache_dir: Path):
    """The error for a prompt with neither a Source nor a Deck reads `Give a Source, a Deck, or both`."""
    error = prompt_error(create_server(cache_dir=cache_dir), {})
    assert getattr(error, "message", None) == "Give a Source, a Deck, or both"

