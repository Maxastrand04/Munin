"""MCP adapter. Maps tool calls onto the core and holds no logic of its own."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from munin.core import (
    Download,
    MuninError,
    Recognize,
    RenderResult,
    TranscribeResult,
    get_transcript,
    render_mindmap,
    transcribe,
)


def create_server(
    *,
    cache_dir: Path | None = None,
    recognize: Recognize | None = None,
    output_dir: Path | None = None,
    download: Download | None = None,
) -> MCPServer:
    """Build the MCP server with three tools and one prompt, passing its arguments to the core.

    `transcribe(source: str)` takes a local file path or a YouTube URL and
    returns the `TranscribeResult` fields as an object.
    `get_transcript(transcript_id: str)` returns the `[m:ss] text` lines.
    `render_mindmap(transcript_id: str, outline: str)` returns the `RenderResult`
    fields as an object, `page` as an absolute path string and `unlinked` as a
    list of `label`, `stamp` and `reason` objects.
    The `lecture_to_mindmap(source: str)` prompt lists the run's steps for one
    Source and leaves the Outline format to `render_mindmap`'s description.
    A `MuninError` comes back as an MCP tool error carrying its message.
    """
    server = MCPServer("munin")

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
    def render_mindmap_tool(transcript_id: str, outline: str) -> RenderResult:
        """Render an Outline whose node labels carry `[m:ss]` or `[h:mm:ss]` stamps into a Mindmap page.

        Write the Outline in this format:

        - Markdown headings (`#`, `##`, `###`) or nested list items, one node per
          topic, two or three levels deep under a single top node.
        - One stamp at the end of each node label, copied from the
          `get_transcript` line where that topic starts, such as
          `## Gausselimination [4:34]`. Never invent or round a stamp.
        - Optionally, a short prose paragraph under a node. It appears in that
          node's explanation panel.

        Returns `page`, the absolute path of the written HTML page, and `unlinked`,
        the stamps left as plain text. Each good stamp becomes a link that opens the
        Transcript's Source at that second. Each `unlinked` entry gives the node
        `label` as written in the Outline, the `stamp`, and a `reason`: `malformed`,
        or `past_end` when the stamp is later than the Source's end. When `unlinked`
        is not empty, fix those stamps in the Outline and render again; the new page
        replaces the old one. The page defaults to Radial rings, with Topic circles
        available in settings.
        """
        with _core_errors_as_tool_errors():
            return render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=output_dir)

    @server.prompt(name="lecture_to_mindmap")
    def lecture_to_mindmap_prompt(source: str) -> str:
        """Turn a lecture, given as a YouTube URL or local file path, into a Mindmap page."""
        return (
            f"Turn this lecture into a Mindmap: {source}\n\n"
            "1. Call `transcribe` with that Source.\n"
            "2. Call `get_transcript` with the returned Transcript ID.\n"
            "3. Write an Outline of the lecture in the format the `render_mindmap` tool describes.\n"
            "4. Call `render_mindmap` with the Transcript ID and the Outline.\n"
            "5. Reply with only the page as a `file://` link, such as `file:///path/to/page.html`. "
            "Write nothing else: no Outline, no summary, no list of steps. "
            "If a step fails, reply with only which step failed and the error."
        )

    return server


def main() -> None:
    """Run the server over stdio with the default cache folder and recognizer.

    Mindmap pages go to `mindmaps/` in the folder the server starts in, which
    is the client's working folder when the server runs with `uv run --project`.
    """
    create_server(output_dir=Path.cwd() / "mindmaps").run()


@contextmanager
def _core_errors_as_tool_errors() -> Iterator[None]:
    try:
        yield
    except MuninError as error:
        raise ToolError(str(error)) from error
