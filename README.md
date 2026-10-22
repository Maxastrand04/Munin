# klang-notes

Workspace for the Klang AI hackathon. A local MCP server turns a recorded Swedish lecture into a mindmap, and every node links back to the second in the lecture it came from.

Klang's [Pianissimo](https://huggingface.co/KlangAI/pianissimo-sv) model does the transcription. It's speech-to-text only, Swedish only, with word timestamps and phrase boosting. An LLM in your MCP client (Claude Code or Claude Desktop) reads the transcript and writes the outline. The tools handle everything with one right answer: downloading, cleaning segments, caching, and building links.

## Status

`transcribe`, `get_transcript` and `render_mindmap` work on local files. YouTube URLs and Vocabulary are still planned. The MVP target is the 7:11 clip [SF1624, Föreläsning 4: Matriser](https://www.youtube.com/watch?v=sZipb-R1hfg).

## Planned tools

| Tool | Does |
|---|---|
| `transcribe(source, vocabulary?)` | Takes a YouTube URL or local file, runs Pianissimo with VAD, caches the Transcript, returns its ID and stats |
| `get_transcript(id)` | Returns `[m:ss] text` lines for the LLM |
| `render_mindmap(id, outline)` | Writes a static Markmap HTML page and turns each `[m:ss]` into a link to the Source |

## Measured on an M1 Pro (ONNX int8, CPU only)

| Audio | Time | Peak RAM |
|---|---|---|
| 7:11 real lecture, VAD | 32 s | about 2.4 GB |
| 10 min synthetic, VAD | 41 s | 2.4 GB |
| 10 min synthetic, no VAD | 16 s | 7.8 GB |

Leaving ONNX Runtime on its default CoreML provider was about 30x slower. See [ADR-0003](docs/adr/0003-onnx-cpu-provider.md).

## Setup

Needs Python 3.12, [uv](https://docs.astral.sh/uv/) and ffmpeg. yt-dlp comes in with YouTube support.

```bash
brew install uv ffmpeg yt-dlp
```

```bash
uv sync
```

The MCP server runs over stdio. Point your MCP client at this command:

```bash
uv run klang-notes-mcp
```

The first transcription downloads the Pianissimo weights, and the loaded model takes about 2.4 GB of RAM. Transcripts are cached in the per-user cache folder. Mindmap pages land in `mindmaps/` at the repo root, which git ignores. Open one straight from disk in Chrome or Safari. Timestamp links work for mp4 and m4a in both.

Run the tests with `uv run pytest`. Add `-m "not slow"` to skip the one test that loads the real model.

## Docs

- [CONTEXT.md](CONTEXT.md) defines the domain terms.
- [docs/adr/](docs/adr/) holds decisions that bind one part of the code.
- [docs/pcr/](docs/pcr/) holds project-wide conventions.

Out of scope for the MVP: full-length lectures, background jobs, an embedded player, the website, and speaker labels.
