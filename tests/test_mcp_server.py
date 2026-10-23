import asyncio
import hashlib
import shutil
from pathlib import Path

from mcp import Client

from klang_notes.core import Fragment, YouTubeSource, get_transcript
from klang_notes.mcp_server import create_server

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
WATCH_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"


def two_sentences(wav: Path):
    """A recognizer that ignores the audio and yields two sentences."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser."), Fragment(65.7, 68.0, "En matris är en tabell.")]


def fake_download(video: YouTubeSource, workdir: Path) -> Path:
    """A downloader that copies the speech fixture into the work folder instead of fetching anything."""
    audio = workdir / "audio.m4a"
    shutil.copy(SPEECH, audio)
    return audio


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def test_mcp_lists_all_tools(cache_dir: Path):
    """The server exposes `transcribe`, `get_transcript` and `render_mindmap`."""

    async def run():
        async with Client(create_server(cache_dir=cache_dir, recognize=two_sentences)) as client:
            return await client.list_tools()

    names = {tool.name for tool in asyncio.run(run()).tools}
    assert names == {"transcribe", "get_transcript", "render_mindmap"}


def test_mcp_transcribe_returns_result_fields(source: Path, cache_dir: Path):
    """The transcribe tool returns the five TranscribeResult fields."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    result = call(server, "transcribe", {"source": str(source)})
    assert set(result.structured_content) == {
        "transcript_id",
        "duration_s",
        "segment_count",
        "transcription_s",
        "cached",
    }


def test_mcp_transcribe_accepts_youtube_url(cache_dir: Path):
    """The transcribe tool takes a YouTube URL as `source` and returns its Transcript ID."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, download=fake_download)
    result = call(server, "transcribe", {"source": WATCH_URL})
    assert result.structured_content["transcript_id"] == hashlib.sha256(WATCH_URL.encode()).hexdigest()[:12]


def test_mcp_get_transcript_returns_lines(source: Path, cache_dir: Path):
    """The get_transcript tool returns the same lines as the core."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"source": str(source)}).structured_content["transcript_id"]
    result = call(server, "get_transcript", {"transcript_id": transcript_id})
    assert result.content[0].text == get_transcript(transcript_id, cache_dir=cache_dir)


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
