"""MCP adapter. Maps tool calls onto the core and holds no logic of its own."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import TextContent

from munin.core import (
    Download,
    MuninError,
    Recognize,
    RenderResult,
    TranscribeResult,
    Vocabulary,
    get_transcript,
    read_slides,
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
    """Build the MCP server with four tools and one prompt, passing its arguments to the core.

    `transcribe(source: str, vocabulary: list[str] | None = None, alpha: float = 1.0)`
    takes a local file path, a YouTube URL or a KTH Play video URL, plus
    optional Vocabulary terms and boost strength, and returns the
    `TranscribeResult` fields as an object, with `vocabulary` as `terms` and
    `alpha` or null. The tool always builds a
    `Vocabulary` from `vocabulary` and `alpha`, so an `alpha` outside 0 to 2 is
    a tool error even without terms, and nothing is transcribed or cached.
    Its description tells the LLM that terms are case sensitive, and that it can
    build a Vocabulary from the misspellings it spots in a first pass, then call
    again to replace the cached Transcript under the same ID.
    `get_transcript(transcript_id: str)` returns the `[m:ss] text` lines.
    `render_mindmap(transcript_id: str, outline: str)` returns the `RenderResult`
    fields as an object, `page` as an absolute path string and `unlinked` as a
    list of `label`, `stamp` and `reason` objects, and `unlinked_slides` as a
    list of `label`, `slide` and `reason` objects. Its description gives the
    `[slide N]` marker format next to the stamp format, and asks for an Outline
    of topics, then Slides, then terms under the lecture title, grouped by
    meaning, with each example and exercise written out under an `Övning:` or
    `Exempel:` leaf.
    `read_slides(transcript_id: str, deck: str)` attaches the Deck through the
    core's `read_slides` and returns two content blocks per Slide in Slide
    order: a text block `Slide N:` followed by the Slide's text on the next
    line, then the Slide's image as a PNG image block.
    The `lecture_to_mindmap(source: str, deck: str | None = None)` prompt lists
    the run's steps for one Source and leaves the Outline format to
    `render_mindmap`'s description. With a `deck`, it adds a step between
    `get_transcript` and writing the Outline that calls `read_slides` with the
    Transcript ID and that Deck path, and asks the LLM to match each Slide to
    the part of the Transcript covering the same content. Without one, its
    text is the same as before Decks existed.
    A `MuninError` comes back as an MCP tool error carrying its message.
    """
    server = MCPServer("munin")

    @server.tool(name="transcribe")
    def transcribe_tool(source: str, vocabulary: list[str] | None = None, alpha: float = 1.0) -> TranscribeResult:
        """Transcribe a local audio or video file, a YouTube video URL or a KTH Play video URL, and return its Transcript ID and stats.

        `vocabulary` is an optional list of course terms to spell correctly, and
        `alpha` is the boost strength from 0 to 2, default 1.0. Terms are
        case sensitive, so give each exactly as it should be written. To build a
        Vocabulary, transcribe once without one, spot the misspelled terms in a
        first pass, then call again with the correct spellings. That call
        replaces the cached Transcript under the same Transcript ID. A call
        without a `vocabulary` returns the cached Transcript, boosted or not.
        `vocabulary` in the result is the terms and alpha used, or null.
        """
        with _core_errors_as_tool_errors():
            boost = Vocabulary(vocabulary or [], alpha)
            return transcribe(source, vocabulary=boost, cache_dir=cache_dir, recognize=recognize, download=download)

    @server.tool(name="get_transcript")
    def get_transcript_tool(transcript_id: str) -> str:
        """Read a Transcript back as one `[m:ss] text` line per Segment."""
        with _core_errors_as_tool_errors():
            return get_transcript(transcript_id, cache_dir=cache_dir)

    @server.tool(name="render_mindmap")
    def render_mindmap_tool(transcript_id: str, outline: str) -> RenderResult:
        """Render an Outline whose node labels carry `[m:ss]` or `[h:mm:ss]` stamps into a Mindmap page.

        Write the Outline in this format:

        - Markdown headings (`#` to `####`) or nested list items, with the lecture
          title as the single top node and three levels under it: topics, then
          Slides, then terms, methods and formulas.
        - Group the lecture by meaning, not by time. A topic gathers every part of
          the lecture about it, even parts far apart in time. Aim for 1 to 5 topics.
        - Under each topic, one node per Slide. With no Deck, split the Transcript
          into Slide-sized parts and write one node per part.
        - Under each Slide node, one node per term, method or formula. Word a term
          the same under every Slide node it appears on.
        - Skip content that neither helps the student grasp an idea nor gives
          concrete material. A Slide such as a title page or a schedule gets no node.
        - Add every example and exercise in the lecture as a leaf under the node it
          belongs to, at any level, with a label that starts with `Övning:` or
          `Exempel:`. These count as neither topics nor terms.
        - One stamp at the end of each node label, copied from the
          `get_transcript` line where that part starts, such as
          `### Gausselimination [4:34]`. A topic gets one stamp for each separate
          stretch of the lecture it gathers, such as
          `## Linjära system [4:34] [38:10]`. Never invent or round a stamp.
        - Under each `Övning:` or `Exempel:` node, a prose paragraph that writes
          out the task and its solution steps, so the panel reads on its own
          without the video or the Slide. Write each step as a plain line, such as
          `Steg 1: ...`, never as list items, because a list item becomes a node.
        - Optionally, a short prose paragraph under any other node. It appears in
          that node's explanation panel.

        Returns `page`, the absolute path of the written HTML page, and `unlinked`,
        the stamps left as plain text. Each good stamp becomes a link that opens the
        Transcript's Source at that second. Each `unlinked` entry gives the node
        `label` as written in the Outline, the `stamp`, and a `reason`: `malformed`,
        or `past_end` when the stamp is later than the Source's end. When `unlinked`
        is not empty, fix those stamps in the Outline and render again; the new page
        replaces the old one. The page defaults to Radial rings, with Topic circles
        available in settings.

        When the lecture has a Deck read with `read_slides`, base the topics on its
        Slides. A node label may also carry one `[slide N]` marker for each Slide
        that covers it, such as `### Gausselimination [4:34] [slide 2] [slide 3]`.
        N counts from 1. Clicking the node then shows those Slides in its panel.
        `unlinked_slides` lists the
        markers left as plain text. Each entry gives the node `label`, the `slide`
        marker as written, and a `reason`: `malformed`, `past_end` when N is past the
        Deck's last Slide, or `no_deck` when the Transcript has no Deck. Fix those in
        the Outline and render again.
        """
        with _core_errors_as_tool_errors():
            return render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=output_dir)

    @server.tool(name="read_slides")
    def read_slides_tool(transcript_id: str, deck: str) -> list[TextContent | Image]:
        """Attach a lecture's slide PDF to a Transcript and return every Slide's number, text and image."""
        with _core_errors_as_tool_errors():
            slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
        blocks: list[TextContent | Image] = []
        for slide in slides:
            blocks.append(TextContent(type="text", text=f"Slide {slide.number}:\n{slide.text}"))
            blocks.append(Image(data=slide.image, format="png"))
        return blocks

    @server.prompt(name="lecture_to_mindmap")
    def lecture_to_mindmap_prompt(source: str, deck: str | None = None) -> str:
        """Turn a lecture, given as a YouTube URL, a KTH Play video URL or a local file path, into a Mindmap page."""
        steps = [
            "Call `transcribe` with that Source.",
            "Call `get_transcript` with the returned Transcript ID.",
        ]
        if deck:
            steps.append(
                f"Call `read_slides` with the Transcript ID and this Deck path: {deck}. "
                "Match each Slide to the part of the Transcript that covers the same content."
            )
        steps += [
            "Write an Outline of the lecture in the format the `render_mindmap` tool describes."
            + (" Put the matching Slide numbers on each node." if deck else ""),
            "Call `render_mindmap` with the Transcript ID and the Outline.",
            (
                "Reply with only the page as a `file://` link, such as `file:///path/to/page.html`. "
                "Write nothing else: no Outline, no summary, no list of steps. "
                "If a step fails, reply with only which step failed and the error."
            ),
        ]
        numbered = "\n".join(f"{number}. {step}" for number, step in enumerate(steps, start=1))
        return f"Turn this lecture into a Mindmap: {source}\n\n{numbered}"

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
