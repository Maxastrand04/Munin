# Munin

Munin is a local MCP server that turns a recorded Swedish lecture into a mindmap, and every node links back to the second in the lecture it came from. It is also the engine a planned hosted app will build on.

Klang's [Pianissimo](https://huggingface.co/KlangAI/pianissimo-sv) model does the transcription. It's speech-to-text only, Swedish only, with word timestamps and phrase boosting. An LLM in your MCP client (Claude Code or Claude Desktop) reads the transcript and writes the outline. The tools handle everything with one right answer: downloading, cleaning segments, caching, and building links.

## Status

`transcribe`, `get_transcript`, `read_slides` and `render_mindmap` work on local files and YouTube URLs, and `transcribe` takes an optional Vocabulary of course terms to spell correctly. The MVP target is the 7:11 clip [SF1624, Föreläsning 4: Matriser](https://www.youtube.com/watch?v=sZipb-R1hfg).

## Tools

| Tool | Does |
|---|---|
| `transcribe(source, vocabulary?, alpha?)` | Takes a YouTube URL or local file, runs Pianissimo with VAD, caches the Transcript, returns its ID and stats. Vocabulary terms are case sensitive and boosted at `alpha`, 0 to 2, default 1.0. A call with terms reruns the Source and replaces its cached Transcript under the same ID |
| `get_transcript(id)` | Returns `[m:ss] text` lines for the LLM |
| `read_slides(id, deck)` | Attaches a PDF of lecture slides (a Deck) to a Transcript, replacing any earlier Deck, and returns each Slide's number, text and image for the LLM to match against the Transcript |
| `render_mindmap(id, outline)` | Writes an interactive HTML Mindmap with Topic circles and Radial rings, turning each `[m:ss]` or `[h:mm:ss]` into a link to the Source and showing the Slides named by `[slide N]` markers in the node's panel. Returns the page path, the stamps it left unlinked (malformed or past the Source's end) and the Slide markers it left unlinked (malformed, past the Deck's last Slide, or no Deck) |

The `lecture_to_mindmap` prompt takes the Source and an optional Deck path. With a Deck path it adds a `read_slides` step before the Outline is written.

## Measured on an M1 Pro (ONNX int8, CPU only)

| Audio | Time | Peak RAM |
|---|---|---|
| 7:11 real lecture, VAD | 32 s | about 2.4 GB |
| 10 min synthetic, VAD | 41 s | 2.4 GB |
| 10 min synthetic, no VAD | 16 s | 7.8 GB |

Leaving ONNX Runtime on its default CoreML provider was about 30x slower. See [ADR-0003](docs/adr/0003-onnx-cpu-provider.md).

## Setup

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and ffmpeg. `uv sync` installs yt-dlp as a Python dependency.

```bash
brew install uv ffmpeg
```

```bash
uv sync
```

The MCP server runs over stdio. Point your MCP client at this command:

```bash
uv run munin
```

Earlier versions ran as `klang-notes-mcp` and cached Transcripts in a `klang-notes` cache folder. Munin ignores that folder, so you can delete it.

The first transcription downloads the Pianissimo weights, and the loaded model takes about 2.4 GB of RAM. Transcripts are cached in the per-user cache folder. Mindmap pages land in `mindmaps/` at the repo root, which git ignores. Open one straight from disk in Chrome or Safari. Timestamp links work for mp4 and m4a in both.

Generated Mindmaps use the approved Linen theme, ellipse nodes, an explanation panel,
and a small settings control for Radial rings (the default) or Topic circles. The opening
view keeps group labels readable, so large Mindmaps may start partly off-screen; "Show
whole Mindmap" zooms out to fit everything. Clicking a node centres it without changing
zoom. Timestamp links open the Source separately. The page embeds
its styles and scripts, so the Mindmap itself works offline.

Outlines may use Markdown headings or nested lists. Optional prose immediately after
a heading or list item appears in that node's explanation panel. The renderer does
not generate explanations; it uses the supplied Outline.

To regenerate the demo from its existing cached Transcript and the approved example
Outline, run:

```sh
uv run python scripts/render_demo.py
```

This writes `mindmaps/5ea1f5df74c8.html`. The example Outline in
[`docs/examples/matriser-outline.md`](docs/examples/matriser-outline.md) includes the
sample explanations used during design review. For a different cached Transcript,
pass `--transcript-id`.

Install the browser used by the Mindmap tests once with `uv run playwright install chromium`,
then run the tests with `uv run pytest`. On Linux, use
`uv run playwright install --with-deps chromium` to also install browser system dependencies.
Add `-m "not slow and not network"` to skip the test that loads the real model and the tests that download from YouTube.

## Docs

- [CONTEXT.md](CONTEXT.md) defines the domain terms.
- [docs/adr/](docs/adr/) holds decisions that bind one part of the code.
- [docs/pcr/](docs/pcr/) holds project-wide conventions.

Out of scope for the MVP: full-length lectures, background jobs, an embedded player, the website, and speaker labels.
