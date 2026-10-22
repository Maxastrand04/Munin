"""MCP adapter. Maps tool calls onto the core and holds no logic of its own."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from klang_notes.core import KlangError, Recognize, TranscribeResult, get_transcript, transcribe


def create_server(
    *,
    cache_dir: Path | None = None,
    recognize: Recognize | None = None,
) -> MCPServer:
    """Build the MCP server with two tools, passing both arguments to the core.

    `transcribe(path: str)` returns the `TranscribeResult` fields as an object.
    `get_transcript(transcript_id: str)` returns the `[m:ss] text` lines.
    A `KlangError` comes back as an MCP tool error carrying its message.
    """
    server = MCPServer("klang-notes")

    @server.tool(name="transcribe")
    def transcribe_tool(path: str) -> TranscribeResult:
        """Transcribe a local audio or video file and return its Transcript ID and stats."""
        with _core_errors_as_tool_errors():
            return transcribe(path, cache_dir=cache_dir, recognize=recognize)

    @server.tool(name="get_transcript")
    def get_transcript_tool(transcript_id: str) -> str:
        """Read a Transcript back as one `[m:ss] text` line per Segment."""
        with _core_errors_as_tool_errors():
            return get_transcript(transcript_id, cache_dir=cache_dir)

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
