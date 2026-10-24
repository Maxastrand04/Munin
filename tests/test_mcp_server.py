import asyncio
import hashlib
import shutil
from pathlib import Path

import pytest
from mcp import Client
from mcp.server import MCPServer

from munin.core import Fragment, Video, Vocabulary, get_transcript, transcribe
from munin import mcp_server
from munin.mcp_server import create_server

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
KTHPLAY_URL = "https://play.kth.se/media/Föreläsning+4A+Matriser/0_1zk8obn5"


def two_sentences(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields two sentences."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser."), Fragment(65.7, 68.0, "En matris är en tabell.")]


def gauss_sentence(wav: Path, vocabulary: Vocabulary | None):
    """A recognizer that ignores the audio and yields one sentence spelling Gausselimination."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om Gausselimination.")]


def recording(received: list):
    """A recognizer that records each Vocabulary it gets in `received` and yields two sentences."""

    def recognize(wav: Path, vocabulary: Vocabulary | None):
        received.append(vocabulary)
        return two_sentences(wav, vocabulary)

    return recognize


def fake_download(video: Video, workdir: Path) -> Path:
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""
    audio = workdir / "audio.m4a"
    shutil.copy(SPEECH, audio)
    return audio


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def prompt_text(server, source: str, deck: str | None = None) -> str:
    arguments = {"source": source} if deck is None else {"source": source, "deck": deck}

    async def run():
        async with Client(server) as client:
            return await client.get_prompt("lecture_to_mindmap", arguments)

    return asyncio.run(run()).messages[0].content.text


def tool_description(server, name: str) -> str:
    async def run():
        async with Client(server) as client:
            return await client.list_tools()

    return next(tool.description for tool in asyncio.run(run()).tools if tool.name == name)


def test_mcp_lists_all_tools(cache_dir: Path):
    """The server exposes `transcribe`, `get_transcript`, `render_mindmap` and `read_slides`."""

    async def run():
        async with Client(create_server(cache_dir=cache_dir, recognize=two_sentences)) as client:
            return await client.list_tools()

    names = {tool.name for tool in asyncio.run(run()).tools}
    assert names == {"transcribe", "get_transcript", "render_mindmap", "read_slides"}


def test_mcp_transcribe_returns_result_fields(source: Path, cache_dir: Path):
    """The transcribe tool returns the TranscribeResult fields."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    result = call(server, "transcribe", {"source": str(source)})
    assert set(result.structured_content) == {
        "transcript_id",
        "duration_s",
        "segment_count",
        "transcription_s",
        "cached",
        "vocabulary",
    }


def test_mcp_transcribe_passes_vocabulary_terms_to_recognizer(source: Path, cache_dir: Path):
    """The transcribe tool's vocabulary terms reach the recognizer unchanged."""
    received = []
    server = create_server(cache_dir=cache_dir, recognize=recording(received))
    call(server, "transcribe", {"source": str(source), "vocabulary": ["SF1624", "Gausselimination"]})
    assert received[0].terms == ("SF1624", "Gausselimination")


def test_mcp_transcribe_passes_alpha_to_recognizer(source: Path, cache_dir: Path):
    """The transcribe tool's alpha reaches the recognizer as the boost strength."""
    received = []
    server = create_server(cache_dir=cache_dir, recognize=recording(received))
    call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"], "alpha": 1.5})
    assert received[0].alpha == 1.5


def test_mcp_transcribe_reports_vocabulary_as_terms_and_alpha(source: Path, cache_dir: Path):
    """The transcribe tool reports the Vocabulary used as an object with terms and alpha."""
    server = create_server(cache_dir=cache_dir, recognize=gauss_sentence)
    result = call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"], "alpha": 1.5})
    assert result.structured_content["vocabulary"] == {"terms": ["Gausselimination"], "alpha": 1.5}


def test_mcp_transcribe_reports_null_vocabulary_without_terms(source: Path, cache_dir: Path):
    """The transcribe tool reports vocabulary null for a run without terms."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    result = call(server, "transcribe", {"source": str(source)})
    assert result.structured_content["vocabulary"] is None


@pytest.mark.parametrize("arguments", [{"vocabulary": ["Gausselimination"], "alpha": 2.5}, {"alpha": -1.0}])
def test_mcp_alpha_out_of_range_is_tool_error(arguments: dict, source: Path, cache_dir: Path):
    """An alpha outside 0 to 2 comes back as a tool error carrying the VocabularyError message, with or without terms."""
    server = create_server(cache_dir=cache_dir, recognize=gauss_sentence)
    result = call(server, "transcribe", {"source": str(source), **arguments})
    assert "outside 0 to 2" in result.content[0].text


def test_mcp_alpha_out_of_range_leaves_cache_unchanged(source: Path, cache_dir: Path):
    """A call rejected for its alpha caches nothing, so the next plain call transcribes fresh."""
    server = create_server(cache_dir=cache_dir, recognize=gauss_sentence)
    call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"], "alpha": 2.5})
    assert call(server, "transcribe", {"source": str(source)}).structured_content["cached"] is False


def test_mcp_transcribe_description_says_terms_are_case_sensitive(cache_dir: Path):
    """The transcribe tool's description tells the LLM that Vocabulary terms are case sensitive."""
    assert "case sensitive" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


def test_mcp_transcribe_description_suggests_a_first_pass(cache_dir: Path):
    """The transcribe tool's description tells the LLM it can build a Vocabulary in a first pass."""
    assert "first pass" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


def test_mcp_transcribe_description_suggests_terms_from_misspellings(cache_dir: Path):
    """The transcribe tool's description tells the LLM to build the Vocabulary from misspellings it spots."""
    assert "misspel" in tool_description(create_server(cache_dir=cache_dir), "transcribe").lower()


def test_mcp_transcribe_accepts_youtube_url(cache_dir: Path):
    """The transcribe tool takes a YouTube URL as `source` and returns its Transcript ID."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, download=fake_download)
    result = call(server, "transcribe", {"source": WATCH_URL})
    assert result.structured_content["transcript_id"] == hashlib.sha256(WATCH_URL.encode()).hexdigest()[:12]



def test_mcp_transcribe_accepts_kthplay_url(cache_dir: Path):
    """The transcribe tool takes a KTH Play link as `source` and returns its Transcript ID."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, download=fake_download)
    result = call(server, "transcribe", {"source": KTHPLAY_URL})
    expected = hashlib.sha256(b"https://play.kth.se/media/t/0_1zk8obn5").hexdigest()[:12]
    assert result.structured_content["transcript_id"] == expected

def test_mcp_get_transcript_returns_lines(source: Path, cache_dir: Path):
    """The get_transcript tool returns the same lines as the core."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "get_transcript", {"transcript_id": transcript_id})
    assert result.content[0].text == get_transcript(transcript_id, cache_dir=cache_dir)


def test_mcp_get_transcript_returns_boosted_lines(source: Path, cache_dir: Path):
    """After a boosted transcribe call, the get_transcript tool returns the boosted Transcript's lines."""
    call(create_server(cache_dir=cache_dir, recognize=two_sentences), "transcribe", {"source": str(source)})
    server = create_server(cache_dir=cache_dir, recognize=gauss_sentence)
    transcribed = call(server, "transcribe", {"source": str(source), "vocabulary": ["Gausselimination"]})
    result = call(server, "get_transcript", {"transcript_id": transcribed.structured_content["transcript_id"]})
    assert result.content[0].text == "[0:01] Idag ska vi prata om Gausselimination."


def test_mcp_unknown_id_is_tool_error(cache_dir: Path):
    """An unknown ID comes back as an MCP tool error."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    result = call(server, "get_transcript", {"transcript_id": "deadbeef0000"})
    assert result.is_error is True


def test_mcp_tool_error_carries_core_message(tmp_path: Path, cache_dir: Path):
    """A core error's message reaches the LLM in the tool error."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    result = call(server, "transcribe", {"source": str(tmp_path / "nope.m4a")})
    assert "nope.m4a" in result.content[0].text


def test_mcp_render_mindmap_returns_page_path(source: Path, cache_dir: Path, tmp_path: Path):
    """The render_mindmap tool returns the page's absolute path."""
    output_dir = tmp_path / "out"
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=output_dir)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser [0:01]"})
    assert result.structured_content["page"] == str(output_dir / f"{transcript_id}.html")


def test_mcp_render_mindmap_writes_page(source: Path, cache_dir: Path, tmp_path: Path):
    """The render_mindmap tool writes the page into the output folder."""
    output_dir = tmp_path / "out"
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=output_dir)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    call(server, "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser [0:01]"})
    assert (output_dir / f"{transcript_id}.html").is_file()


def test_mcp_render_mindmap_unknown_id_is_tool_error(cache_dir: Path, tmp_path: Path):
    """An unknown ID given to render_mindmap comes back as an MCP tool error."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=tmp_path / "out")
    result = call(server, "render_mindmap", {"transcript_id": "deadbeef0000", "outline": "# Matriser"})
    assert result.is_error is True


def test_mcp_render_mindmap_unknown_id_error_names_it(cache_dir: Path, tmp_path: Path):
    """The tool error for an unknown ID given to render_mindmap names the ID."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=tmp_path / "out")
    result = call(server, "render_mindmap", {"transcript_id": "deadbeef0000", "outline": "# Matriser"})
    assert "deadbeef0000" in result.content[0].text


def test_mcp_render_mindmap_reports_unlinked_stamps(source: Path, cache_dir: Path, tmp_path: Path):
    """The render_mindmap tool returns each unlinked stamp's label, stamp and reason."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=tmp_path / "out")
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser\n- Gauss [1:75]"})
    assert result.structured_content["unlinked"] == [{"label": "Gauss [1:75]", "stamp": "[1:75]", "reason": "malformed"}]


def test_mcp_render_mindmap_reports_unlinked_slides(source: Path, cache_dir: Path, tmp_path: Path):
    """The render_mindmap tool returns each unlinked slide marker's label, slide and reason."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=tmp_path / "out")
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser\n- Gauss [slide 1]"})
    assert result.structured_content["unlinked_slides"] == [
        {"label": "Gauss [slide 1]", "slide": "[slide 1]", "reason": "no_deck"}
    ]


def test_mcp_read_slides_returns_a_text_then_an_image_block_per_slide(source: Path, deck: Path, cache_dir: Path):
    """The read_slides tool returns a text block then an image block for each Slide, in Slide order."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "read_slides", {"transcript_id": transcript_id, "deck": str(deck)})
    assert [block.type for block in result.content] == ["text", "image"] * 3


def test_mcp_read_slides_text_block_names_the_slide_then_its_text(source: Path, deck: Path, cache_dir: Path):
    """Each text block reads `Slide N:` with the Slide's text on the next line."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "read_slides", {"transcript_id": transcript_id, "deck": str(deck)})
    assert result.content[2].text.startswith("Slide 2:\nGausselimination")


def test_mcp_read_slides_image_block_is_png(source: Path, deck: Path, cache_dir: Path):
    """Each image block is a PNG."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "read_slides", {"transcript_id": transcript_id, "deck": str(deck)})
    assert result.content[1].mime_type == "image/png"


def test_mcp_read_slides_bad_deck_is_tool_error(source: Path, cache_dir: Path, tmp_path: Path):
    """A bad Deck comes back as an MCP tool error."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "read_slides", {"transcript_id": transcript_id, "deck": str(tmp_path / "missing.pdf")})
    assert result.is_error is True


def test_mcp_read_slides_bad_deck_error_names_the_path(source: Path, cache_dir: Path, tmp_path: Path):
    """A bad Deck comes back as a tool error that names the Deck path."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    missing = str(tmp_path / "missing.pdf")
    result = call(server, "read_slides", {"transcript_id": transcript_id, "deck": missing})
    assert missing in result.content[0].text


def test_mcp_read_slides_unknown_id_is_tool_error(deck: Path, cache_dir: Path):
    """An unknown ID given to read_slides comes back as an MCP tool error."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    result = call(server, "read_slides", {"transcript_id": "deadbeef0000", "deck": str(deck)})
    assert result.is_error is True


def test_mcp_lists_lecture_prompt_with_required_source_and_optional_deck(cache_dir: Path):
    """The server lists `lecture_to_mindmap` with a required `source` and an optional `deck`."""

    async def run():
        async with Client(create_server(cache_dir=cache_dir, recognize=two_sentences)) as client:
            return await client.list_prompts()

    prompts = {prompt.name: prompt for prompt in asyncio.run(run()).prompts}
    assert [(arg.name, arg.required) for arg in prompts["lecture_to_mindmap"].arguments] == [
        ("source", True),
        ("deck", False),
    ]


def test_mcp_lecture_prompt_fills_in_source(cache_dir: Path):
    """The prompt's text carries the Source it was given."""
    assert WATCH_URL in prompt_text(create_server(cache_dir=cache_dir), WATCH_URL)



def test_mcp_lecture_prompt_fills_in_kthplay_url(cache_dir: Path):
    """The prompt's text carries the KTH Play link it was given."""
    assert KTHPLAY_URL in prompt_text(create_server(cache_dir=cache_dir), KTHPLAY_URL)

def test_mcp_lecture_prompt_calls_tools_in_run_order(cache_dir: Path):
    """The prompt names transcribe, then get_transcript, then render_mindmap."""
    text = prompt_text(create_server(cache_dir=cache_dir), WATCH_URL)
    positions = [text.index(f"`{tool}`") for tool in ("transcribe", "get_transcript", "render_mindmap")]
    assert positions == sorted(positions)


def test_mcp_lecture_prompt_asks_for_only_a_file_link(cache_dir: Path):
    """The prompt asks for a reply of only a `file://` link to the page."""
    text = prompt_text(create_server(cache_dir=cache_dir), WATCH_URL)
    assert "only the page as a `file://` link" in text


def test_mcp_lecture_prompt_leaves_format_to_render_tool(cache_dir: Path):
    """The prompt points at render_mindmap for the Outline format."""
    assert "format the `render_mindmap` tool describes" in prompt_text(create_server(cache_dir=cache_dir), WATCH_URL)


def test_mcp_lecture_prompt_carries_no_stamp(cache_dir: Path):
    """The prompt carries no stamp format of its own."""
    assert "[m:ss]" not in prompt_text(create_server(cache_dir=cache_dir), WATCH_URL)


def test_mcp_lecture_prompt_with_deck_carries_the_deck_path(cache_dir: Path):
    """With a Deck, the prompt's text carries the Deck path."""
    assert "/tmp/matriser.pdf" in prompt_text(create_server(cache_dir=cache_dir), WATCH_URL, "/tmp/matriser.pdf")


def test_mcp_lecture_prompt_with_deck_reads_slides_between_transcript_and_render(cache_dir: Path):
    """With a Deck, the prompt names read_slides after get_transcript and before render_mindmap."""
    text = prompt_text(create_server(cache_dir=cache_dir), WATCH_URL, "/tmp/matriser.pdf")
    positions = [text.index(f"`{tool}`") for tool in ("get_transcript", "read_slides", "render_mindmap")]
    assert positions == sorted(positions)


def test_mcp_lecture_prompt_with_deck_asks_to_match_slides(cache_dir: Path):
    """With a Deck, the prompt asks the LLM to match Slides to the part of the Transcript covering them."""
    text = prompt_text(create_server(cache_dir=cache_dir), WATCH_URL, "/tmp/matriser.pdf")
    assert "Match each Slide to the part of the Transcript" in text


def test_mcp_lecture_prompt_with_deck_asks_for_slide_numbers_on_nodes(cache_dir: Path):
    """With a Deck, the prompt asks the LLM to put the matching Slide numbers on each node."""
    text = prompt_text(create_server(cache_dir=cache_dir), WATCH_URL, "/tmp/matriser.pdf")
    assert "Slide numbers on each node" in text


def test_mcp_lecture_prompt_without_deck_skips_read_slides(cache_dir: Path):
    """With no Deck, the prompt never names read_slides."""
    assert "read_slides" not in prompt_text(create_server(cache_dir=cache_dir), WATCH_URL)


def test_mcp_lecture_prompt_without_deck_asks_for_no_slide_numbers(cache_dir: Path):
    """With no Deck, the prompt never mentions Slides."""
    assert "Slide" not in prompt_text(create_server(cache_dir=cache_dir), WATCH_URL)


def test_mcp_render_description_gives_the_slide_marker_format(cache_dir: Path):
    """The render tool's description tells the LLM to write `[slide N]` markers."""
    assert "[slide N]" in tool_description(create_server(cache_dir=cache_dir), "render_mindmap")


def test_mcp_render_description_puts_stamp_at_label_end(cache_dir: Path):
    """The render tool's description asks for one stamp at the end of each node label."""
    assert "One stamp at the end of each node label" in tool_description(create_server(cache_dir=cache_dir), "render_mindmap")


def test_mcp_render_description_asks_for_two_or_three_levels(cache_dir: Path):
    """The render tool's description asks for an Outline two or three levels deep."""
    assert "two or three levels deep" in tool_description(create_server(cache_dir=cache_dir), "render_mindmap")


def test_mcp_main_writes_pages_to_mindmaps_in_working_folder(source: Path, tmp_path: Path, monkeypatch):
    """The server `main` starts writes Mindmap pages into `mindmaps/` in the folder it starts in."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    transcript_id = transcribe(source, recognize=two_sentences).transcript_id
    started = []
    monkeypatch.setattr(MCPServer, "run", lambda server, *args, **kwargs: started.append(server))
    monkeypatch.chdir(tmp_path)
    mcp_server.main()
    call(started[0], "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser [0:01]"})
    assert (tmp_path / "mindmaps" / f"{transcript_id}.html").is_file()
