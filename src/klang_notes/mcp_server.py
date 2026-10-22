"""MCP adapter. Maps tool calls onto the core and holds no logic of its own."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from klang_notes.core import (
    KlangError,
    Recognize,
    TranscribeResult,
    get_transcript,
    render_mindmap,
    transcribe,
)
from klang_notes.core.youtube import Download


def create_server(
    *,
    cache_dir: Path | None = None,
    recognize: Recognize | None = None,
    output_dir: Path | None = None,
    download: Download | None = None,
) -> MCPServer:
    """Build the MCP server with three tools, passing its arguments to the core.

    `transcribe(source: str)` takes a local file path or a YouTube URL and returns the `TranscribeResult` fields as an object.
    `get_transcript(transcript_id: str)` returns the `[m:ss] text` lines.
    `render_mindmap(transcript_id: str, outline: str)` returns the page's absolute path.
    A `KlangError` comes back as an MCP tool error carrying its message.
    """
    server = MCPServer("klang-notes")

    @server.tool(name="transcribe")
    def transcribe_tool(source: str) -> TranscribeResult:
        """Transcribe a local audio or video file, or a YouTube video URL, and return its Transcript ID and stats."""
        with _core_errors_as_tool_errors():
            return transcribe(source, cache_dir=cache_dir, recognize=recognize, download=download)

    @server.tool(name="get_transcript")
    def get_transcript_tool(transcript_id: str) -> str:
        """Read a Transcript back as one `[m:ss] text` line per Segment."""
        with _core_errors_as_tool_errors():
            return get_transcript(transcript_id, cache_dir=cache_dir)

    @server.tool(name="render_mindmap")
    def render_mindmap_tool(transcript_id: str, outline: str) -> str:
        """Render an Outline whose node labels carry `[m:ss]` stamps into a Mindmap page.

        Returns the absolute path of the written HTML page. Each stamp becomes a
        link that opens the Transcript's Source at that second.
        """
        with _core_errors_as_tool_errors():
            return str(render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=output_dir))

    return server


def main() -> None:
    """Run the server over stdio with the default cache folder and recognizer."""
    create_server().run()


@contextmanager
def _core_errors_as_tool_errors() -> Iterator[None]:
    try:
        yield
    except KlangError as error:
        raise ToolError(str(error)) from error
