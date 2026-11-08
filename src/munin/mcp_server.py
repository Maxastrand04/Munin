"""MCP adapter. Maps tool calls onto the core and holds no logic of its own."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, TextContent

from munin.core import (
    Download,
    Language,
    LanguageError,
    MuninError,
    OutlineSchema,
    Recognize,
    RenderResult,
    Slide,
    TranscribeResult,
    Vocabulary,
    get_outline_schema,
    get_transcript,
    parse_language,
    read_deck,
    read_slides,
    render_deck_mindmap,
    render_mindmap,
    transcribe,
)

_REPLY_STEP = (
    "Reply with only the page as a `file://` link, such as `file:///path/to/page.html`. "
    "Write nothing else: no Outline, no summary, no list of steps. "
    "If a step fails, reply with only which step failed and the error."
)


def create_server(
    *,
    cache_dir: Path | None = None,
    recognize: Recognize | None = None,
    output_dir: Path | None = None,
    download: Download | None = None,
) -> MCPServer:
    """Build the MCP server with seven tools and two prompts, passing its arguments to the core.

    `transcribe(source: str, vocabulary: list[str] | None = None, alpha: float = 1.0, language: Language | None = None)`
    takes a local file path, a YouTube URL or a KTH Play video URL, plus
    optional Vocabulary terms and boost strength, and the lecture's language,
    and returns the `TranscribeResult` fields as an object, with `vocabulary` as
    `terms` and `alpha` or null, and `language` as `sv` or `en`. The tool always
    builds a `Vocabulary` from `vocabulary` and `alpha`, so an `alpha` outside 0
    to 2 is a tool error even without terms, and nothing is transcribed or cached.
    The tool's schema lists `sv` and `en` as `language`'s only values, so any
    other value is a tool error before the core runs.
    Its description tells the LLM that terms are case sensitive, and that it can
    build a Vocabulary from the misspellings it spots in a first pass, then call
    again to replace the cached Transcript under the same ID. It also says
    `language` is the language the lecture is spoken in, `sv` or `en`, that a
    call with none and nothing cached runs Swedish, that a different language
    replaces the cached Transcript under the same ID, and that Vocabulary terms
    do not work on English lectures yet.
    `get_transcript(transcript_id: str)` returns the `[m:ss] text` lines.
    `get_outline_schema()` takes no arguments and returns the core's
    `OutlineSchema` fields as an object, `schema` and `samples`. Its
    description tells the LLM to call it before writing an Outline.
    `render_mindmap(transcript_id: str, outline: dict | str)` takes the
    Outline as a JSON object, or as text, which reaches the core as written so
    a Markdown Outline gets the core's `OutlineSyntaxError` message. It
    returns the `RenderResult` fields as an object, `page` as an absolute path
    string and nothing else. Its description tells the LLM to call
    `get_outline_schema` before writing an Outline, describes no Markdown
    format, and keeps its content guidance: an Outline of topics, then
    slides, then terms under the lecture title, grouped by meaning, one stamp
    per stretch of the lecture copied from `get_transcript`, and every
    example and exercise written out as an example or exercise node, a Slide
    that is only one example or exercise included, with no `Exempel:`,
    `Övning:`, `Example:` or `Exercise:` in any label. It asks for the whole
    Outline, every step's reason included, in the lecture's language, the
    `language` `transcribe` returned, and names neither Swedish nor English.
    It asks for LaTeX for every math expression,
    between `$...$` in explanations, tasks, answers and step reasons, never
    `$$`, and with no `$` in a step's calculation, and for each step to be
    one calculation with at most one short sentence on why. When a
    render fails, it says to fix every problem listed, broken LaTeX
    included, and render again.
    `read_slides(transcript_id: str, deck: str)` attaches the Deck through the
    core's `read_slides` and returns two content blocks per Slide in Slide
    order: a text block `Slide N:` followed by the Slide's text on the next
    line, then the Slide's image as a PNG image block.
    `read_deck(deck: str)` reads a Deck on its own through the core's
    `read_deck` and returns a text block `Deck ID: <id>` first, then the same
    two blocks per Slide that `read_slides` returns.
    `render_deck_mindmap(deck_id: str, outline: dict | str, language: Language | None = None)`
    takes the Outline as `render_mindmap` does, passes `language` to the
    core, and returns the `RenderResult` fields as `render_mindmap` does. The
    tool's schema lists `sv` and `en` as `language`'s only values, so any
    other value is a tool error before the core runs. Its description tells
    the LLM to call `get_outline_schema` before writing an Outline, describes
    no Markdown format, and keeps the slides-only content guidance: 1 to 5
    topics grouped by meaning, one slide node per Slide carrying its Slide
    number, title and schedule Slides skipped, terms worded the same
    everywhere, every example and exercise written out as an example or
    exercise node the same way, every node's `stamps` left empty, and an
    explanation of one to three sentences on every term node that gives
    context and covers only what the Slides cover. It asks for LaTeX and
    steps as `render_mindmap`'s does, a step's reason included, at most one
    short sentence, and names `Exempel:`, `Övning:`, `Example:` and
    `Exercise:` as prefixes to leave out of every label. It asks for the
    whole Outline, every step's reason included, in the Deck's language,
    judged from its Slides, and for that language as `language`, `sv` or
    `en`. It says a render with no `language` is a Swedish page. It says
    to fix every problem listed, broken LaTeX included, and render again.
    The `lecture_to_mindmap(source: str | None = None, deck: str | None = None, language: str | None = None)`
    prompt takes a Source, a Deck, or both, and a language. An empty
    `language` counts as none. Any other value but `sv` or `en` fails with an
    MCP error carrying the `LanguageError` message. With a Source and a
    `language`, the `transcribe` step asks for that language, as in "Call
    `transcribe` with that Source and language `en`." With a Source, it lists the run's
    steps for that Source, asks for the Outline as JSON, and has the LLM call
    `get_outline_schema` before writing it, asks for the whole Outline in the
    lecture's language, the `language` `transcribe` returned, with or without
    a `language` argument, asks for LaTeX for every math
    expression, and leaves the rest of the content guidance to
    `render_mindmap`'s description. With a `deck` as well, it adds a step between
    `get_transcript` and writing the Outline that calls `read_slides` with the
    Transcript ID and that Deck path, and asks the LLM to match each Slide to
    the part of the Transcript covering the same content. Its `render_mindmap`
    step never passes a language, since a Deck attached to a Transcript takes
    the Transcript's. Without a Deck, its text is the same as before Decks
    existed. With only a `deck`, it lists the
    slides-only steps: call `read_deck` with that Deck path, call
    `get_outline_schema`, write a JSON Outline from the Slides as
    `render_deck_mindmap` describes, with LaTeX for every math expression, call
    `render_deck_mindmap` with the Deck ID, the Outline and a language, and
    reply with only the page as a `file://` link, or with which step failed
    and the error. With a `language` as well, the writing step asks for the
    whole Outline in that language, naming it as `sv` or `en`, and the render
    step passes it, as in "Call `render_deck_mindmap` with the Deck ID, the
    Outline and language `en`." With no `language`, the writing step asks for
    the whole Outline in the Deck's language, judged from its Slides, and the
    render step passes that language as `language`, `sv` or `en`. It never
    names `transcribe`. With neither a Source nor a Deck, getting the prompt
    fails with an MCP error whose message is "Give a Source, a Deck, or
    both", whether or not a `language` is given, and no step runs.
    The `slides_to_mindmap(deck: str, language: str | None = None)` prompt
    takes a Deck and an optional language, and gives the same text as
    `lecture_to_mindmap` with only that `deck` and `language`, bad `language`
    errors included. It exists because a client that fills prompt arguments
    by position, such as a slash command, always puts the first argument in
    `source`, and it puts `deck` first and `language` second.
    A `MuninError` comes back as an MCP tool error carrying its message.
    """
    server = MCPServer("munin")

    @server.tool(name="transcribe")
    def transcribe_tool(
        source: str, vocabulary: list[str] | None = None, alpha: float = 1.0, language: Language | None = None
    ) -> TranscribeResult:
        """Transcribe a local audio or video file, a YouTube video URL or a KTH Play video URL, and return its Transcript ID and stats.

        `vocabulary` is an optional list of course terms to spell correctly, and
        `alpha` is the boost strength from 0 to 2, default 1.0. Terms are
        case sensitive, so give each exactly as it should be written. To build a
        Vocabulary, transcribe once without one, spot the misspelled terms in a
        first pass, then call again with the correct spellings. That call
        replaces the cached Transcript under the same Transcript ID. A call
        without a `vocabulary` returns the cached Transcript, boosted or not.
        `vocabulary` in the result is the terms and alpha used, or null.

        `language` is the language the lecture is spoken in, `sv` or `en`. With
        no `language` and nothing cached, the lecture runs as Swedish. A
        `language` other than the cached Transcript's replaces it under the same
        Transcript ID, and `language` in the result says which language it is.
        Vocabulary terms do not work on English lectures yet, so give none with `en`.
        """
        with _core_errors_as_tool_errors():
            boost = Vocabulary(vocabulary or [], alpha)
            return transcribe(
                source, language=language, vocabulary=boost, cache_dir=cache_dir, recognize=recognize, download=download
            )

    @server.tool(name="get_transcript")
    def get_transcript_tool(transcript_id: str) -> str:
        """Read a Transcript back as one `[m:ss] text` line per Segment."""
        with _core_errors_as_tool_errors():
            return get_transcript(transcript_id, cache_dir=cache_dir)

    @server.tool(name="get_outline_schema")
    def get_outline_schema_tool() -> OutlineSchema:
        """Return the JSON Schema an Outline must follow, plus a sample example node and exercise node. Call this before writing an Outline."""
        return get_outline_schema()

    @server.tool(name="render_mindmap")
    def render_mindmap_tool(transcript_id: str, outline: dict | str) -> RenderResult:
        """Render a JSON Outline of a lecture into a Mindmap page.

        Call `get_outline_schema` before writing an Outline. It gives the
        node types, the parts every node carries and a sample example and
        exercise. Pass the Outline as a JSON object.

        Write the Outline like this:

        - The lecture title as the one main-topic node, with three levels
          under it: topic nodes, then slide nodes, then term nodes for terms,
          methods and formulas.
        - Group the lecture by meaning, not by time. A topic gathers every part of
          the lecture about it, even parts far apart in time. Aim for 1 to 5 topics.
        - Under each topic, one slide node per Slide. With no Deck, split the
          Transcript into Slide-sized parts and write one slide node per part.
          A Slide that is only one example or exercise gets an example or exercise
          node under its topic in place of a slide node.
        - Under each slide node, one term node per term, method or formula. Word
          a term the same under every slide node it appears on.
        - Skip content that neither helps the student grasp an idea nor gives
          concrete material. A Slide such as a title page or a schedule gets no node.
        - Write every example and exercise in the lecture as an example or exercise
          node under the node it belongs to, at any level. Give it the task, its
          solution steps and the answer, so the panel reads on its own without
          the video or the Slide. Leave `Exempel:`, `Övning:`, `Example:` and
          `Exercise:` out of every label, a slide node's too, since the page adds
          its prefix.
        - Put one stamp in each node's `stamps`, copied from the `get_transcript`
          line where that part starts, such as `"4:34"`. A topic gets one stamp
          for each separate stretch of the lecture it gathers. Never invent or
          round a stamp.
        - Optionally, a short `explanation` on any node that has one. It appears
          in that node's panel.
        - Write every math expression as LaTeX, always inline and never `$$`.
          In an explanation, a task, an answer and a step's reason, put each
          piece of math between `$...$` and write the rest as plain prose, with
          `\\$` for a literal dollar sign. Write a step's calculation as LaTeX
          alone, with no `$`. Make each step one calculation, with at most one
          short sentence on why in its reason.
        - Write the whole Outline, every node's text and every step's reason
          included, in the lecture's language, the `language` `transcribe` returned.

        When the lecture has a Deck read with `read_slides`, base the topics on its
        Slides, and list in a node's `slides` each Slide that covers it, counted
        from 1. Clicking the node then shows those Slides in its panel. With no
        Deck, leave every `slides` empty.

        Returns `page`, the absolute path of the written HTML page. Each stamp
        becomes a link that opens the Transcript's Source at that second. When
        the Outline breaks the schema, a stamp or Slide number cannot be
        linked, or a piece of LaTeX cannot be drawn, nothing is written and the error lists every problem by its
        path of labels, broken LaTeX included. Fix every problem listed and render again; the new page
        replaces the old one. The page defaults to Radial rings, with Topic
        circles available in settings.
        """
        with _core_errors_as_tool_errors():
            return render_mindmap(transcript_id, outline, cache_dir=cache_dir, output_dir=output_dir)

    @server.tool(name="read_slides")
    def read_slides_tool(transcript_id: str, deck: str) -> list[TextContent | Image]:
        """Attach a lecture's slide PDF to a Transcript and return every Slide's number, text and image."""
        with _core_errors_as_tool_errors():
            slides = read_slides(transcript_id, deck, cache_dir=cache_dir)
        return _slide_blocks(slides)

    @server.tool(name="read_deck")
    def read_deck_tool(deck: str) -> list[TextContent | Image]:
        """Read a lecture's slide PDF on its own, with no recording, and return its Deck ID and every Slide's number, text and image."""
        with _core_errors_as_tool_errors():
            result = read_deck(deck, cache_dir=cache_dir)
        return [TextContent(type="text", text=f"Deck ID: {result.deck_id}"), *_slide_blocks(result.slides)]

    @server.tool(name="render_deck_mindmap")
    def render_deck_mindmap_tool(deck_id: str, outline: dict | str, language: Language | None = None) -> RenderResult:
        """Render a JSON Outline written from a Deck read with `read_deck` into a Mindmap page.

        Call `get_outline_schema` before writing an Outline. It gives the
        node types, the parts every node carries and a sample example and
        exercise. Pass the Outline as a JSON object.

        Write the Outline like this:

        - The lecture title as the one main-topic node, with three levels
          under it: topic nodes, then slide nodes, then term nodes for terms,
          methods and formulas.
        - Group the lecture by meaning, not by Slide order. A topic gathers every
          Slide about it, even Slides far apart in the Deck. Aim for 1 to 5 topics.
        - Under each topic, one slide node per Slide, listing its Slide number in
          `slides`, counted from 1. A node that two Slides cover lists both.
          A Slide that is only one example or exercise gets an example or exercise
          node under its topic in place of a slide node.
        - Under each slide node, one term node per term, method or formula. Word
          a term the same under every slide node it appears on.
        - Skip content that neither helps the student grasp an idea nor gives
          concrete material. A Slide such as a title page or a schedule gets no node.
        - Write every example and exercise on the Slides as an example or exercise
          node under the node it belongs to, at any level. Give it the task, its
          solution steps and the answer, so the panel reads on its own without
          the Slide. Leave `Exempel:`, `Övning:`, `Example:` and `Exercise:` out
          of every label, a slide node's too, since the page adds its prefix.
        - Give every term node an `explanation` of one to three sentences that
          explains the term and gives context, covering only what the Slides cover.
        - Optionally, a short `explanation` on any other node that has one. It
          appears in that node's panel.
        - There is no recording, so leave every node's `stamps` empty.
        - Write every math expression as LaTeX, always inline and never `$$`.
          In an explanation, a task, an answer and a step's reason, put each
          piece of math between `$...$` and write the rest as plain prose, with
          `\\$` for a literal dollar sign. Write a step's calculation as LaTeX
          alone, with no `$`. Make each step one calculation, with at most one
          short sentence on why in its reason.
        - Write the whole Outline, every node's text and every step's reason
          included, in the Deck's language, judged from its Slides. Pass that
          language as `language`, `sv` or `en`. A render with no `language` is
          a Swedish page.

        Returns `page`, the absolute path of the written HTML page. When the
        Outline breaks the schema, carries a stamp, names a Slide past the
        Deck's last, or holds a piece of LaTeX that cannot be drawn, nothing is
        written and the error lists every problem by its path of labels, broken
        LaTeX included. Fix every problem listed and render again; the new
        page replaces the old one.
        """
        with _core_errors_as_tool_errors():
            return render_deck_mindmap(
                deck_id, outline, language=language, cache_dir=cache_dir, output_dir=output_dir
            )

    @server.prompt(name="lecture_to_mindmap")
    def lecture_to_mindmap_prompt(
        source: str | None = None, deck: str | None = None, language: str | None = None
    ) -> str:
        """Turn a lecture, given as a YouTube URL, a KTH Play video URL or a local file path, a slide PDF, or both, into a Mindmap page."""
        if not source and not deck:
            raise MCPError(code=INVALID_PARAMS, message="Give a Source, a Deck, or both")
        lecture_language = _checked_language(language)
        if not source:
            return _slides_only_prompt(deck, lecture_language)
        transcribe_step = (
            f"Call `transcribe` with that Source and language `{lecture_language}`."
            if lecture_language
            else "Call `transcribe` with that Source."
        )
        steps = [
            transcribe_step,
            "Call `get_transcript` with the returned Transcript ID.",
        ]
        if deck:
            steps.append(
                f"Call `read_slides` with the Transcript ID and this Deck path: {deck}. "
                "Match each Slide to the part of the Transcript that covers the same content."
            )
        steps += [
            "Call `get_outline_schema`.",
            "Write an Outline of the lecture as JSON, in the format `get_outline_schema` gives,"
            " following the guidance in the `render_mindmap` tool's description."
            " Write the whole Outline in the lecture's language, the `language` `transcribe` returned."
            " Write every math expression as LaTeX."
            + (" List the matching Slide numbers on each node." if deck else ""),
            "Call `render_mindmap` with the Transcript ID and the Outline.",
            _REPLY_STEP,
        ]
        return f"Turn this lecture into a Mindmap: {source}\n\n{_numbered(steps)}"

    @server.prompt(name="slides_to_mindmap")
    def slides_to_mindmap_prompt(deck: str, language: str | None = None) -> str:
        """Turn a lecture's slide PDF, with no recording, into a Mindmap page."""
        return _slides_only_prompt(deck, _checked_language(language))

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


def _slide_blocks(slides: tuple[Slide, ...]) -> list[TextContent | Image]:
    """Return a `Slide N:` text block, then a PNG image block, for each Slide in order."""
    blocks: list[TextContent | Image] = []
    for slide in slides:
        blocks.append(TextContent(type="text", text=f"Slide {slide.number}:\n{slide.text}"))
        blocks.append(Image(data=slide.image, format="png"))
    return blocks


def _checked_language(language: str | None) -> Language | None:
    """Return the prompt's language as a Language, None when it is empty or absent, or fail with an MCP error."""
    try:
        return parse_language(language or None)
    except LanguageError as error:
        raise MCPError(code=INVALID_PARAMS, message=str(error)) from error


def _slides_only_prompt(deck: str, language: Language | None) -> str:
    """Return the steps that read a Deck on its own and render a Mindmap from its Slides, in `language` when given."""
    if language:
        outline_language = f"Write the whole Outline in language `{language}`."
        render_language = f"Call `render_deck_mindmap` with the Deck ID, the Outline and language `{language}`."
    else:
        outline_language = "Write the whole Outline in the Deck's language, judged from its Slides."
        render_language = (
            "Call `render_deck_mindmap` with the Deck ID, the Outline and the Deck's language as `language`, `sv` or `en`."
        )
    steps = [
        f"Call `read_deck` with this Deck path: {deck}.",
        "Call `get_outline_schema`.",
        (
            "Write an Outline of the lecture from the Slides alone as JSON, in the format `get_outline_schema` gives,"
            " following the guidance in the `render_deck_mindmap` tool's description."
            " Write every math expression as LaTeX. "
            + outline_language
        ),
        render_language,
        _REPLY_STEP,
    ]
    return f"Turn this slide deck into a Mindmap: {deck}\n\n{_numbered(steps)}"


def _numbered(steps: list[str]) -> str:
    """Return the steps as a numbered list, one per line, counting from 1."""
    return "\n".join(f"{number}. {step}" for number, step in enumerate(steps, start=1))
