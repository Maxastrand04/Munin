"""MCP adapter. Maps tool calls onto the core and holds no logic of its own."""

from pathlib import Path

from mcp.server import MCPServer

from klang_notes.core import Recognize


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
    raise NotImplementedError


def main() -> None:
    """Run the server over stdio with the default cache folder and recognizer."""
    raise NotImplementedError
