import asyncio
from pathlib import Path

from mcp import Client

from klang_notes.core import Fragment, get_transcript
from klang_notes.mcp_server import create_server


def two_sentences(wav: Path):
    """A recognizer that ignores the audio and yields two sentences."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser."), Fragment(65.7, 68.0, "En matris är en tabell.")]


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
    result = call(server, "transcribe", {"path": str(source)})
    assert set(result.structured_content) == {
        "transcript_id",
        "duration_s",
        "segment_count",
        "transcription_s",
        "cached",
    }


def test_mcp_get_transcript_returns_lines(source: Path, cache_dir: Path):
    """The get_transcript tool returns the same lines as the core."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences)
    transcript_id = call(server, "transcribe", {"path": str(source)}).structured_content["transcript_id"]
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
    result = call(server, "transcribe", {"path": str(tmp_path / "nope.m4a")})
    assert "nope.m4a" in result.content[0].text


def test_mcp_render_mindmap_returns_page_path(source: Path, cache_dir: Path, tmp_path: Path):
    """The render_mindmap tool writes the page and returns its absolute path."""
    output_dir = tmp_path / "out"
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=output_dir)
    transcript_id = call(server, "transcribe", {"path": str(source)}).structured_content["transcript_id"]
    result = call(server, "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser [0:01]"})
    assert result.content[0].text == str(output_dir / f"{transcript_id}.html")
    assert (output_dir / f"{transcript_id}.html").is_file()


def test_mcp_render_mindmap_unknown_id_is_tool_error(cache_dir: Path, tmp_path: Path):
    """An unknown ID given to render_mindmap comes back as an MCP tool error naming it."""
    server = create_server(cache_dir=cache_dir, recognize=two_sentences, output_dir=tmp_path / "out")
    result = call(server, "render_mindmap", {"transcript_id": "deadbeef0000", "outline": "# Matriser"})
    assert result.is_error is True
    assert "deadbeef0000" in result.content[0].text
