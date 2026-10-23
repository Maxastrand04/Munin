# Munin

Munin turns a recorded Swedish lecture into a mindmap whose nodes link back to the moment in the lecture they summarize. Klang's Pianissimo model transcribes. Munin does the deterministic work, and the LLM writes the Outline. See [ADR-0001](docs/adr/0001-tools-own-deterministic-work.md).

## Language

**Source**:
The recording a Transcript was made from, either a YouTube URL or a local audio or video file path.
_Avoid_: input, video, file

**Transcript**:
The cached text of one Source, made of Segments and identified by a Transcript ID, which remembers its Source.
_Avoid_: transcription (for the stored result), text, captions

**Segment**:
One span of speech in a Transcript with a start time, an end time and its text, after Fragments are merged and empty spans dropped.
_Avoid_: chunk, line, utterance

**Fragment**:
One raw span of speech as VAD and Pianissimo return it, before merging into Segments.
_Avoid_: chunk, piece

**Vocabulary**:
A list of terms, plus a boost strength (alpha) from 0 to 2, that steers Pianissimo toward spelling those terms correctly. Terms are case sensitive. A Vocabulary whose terms are all blank counts as none.
_Avoid_: glossary, keywords, hotwords

**Outline**:
The nested Markdown the LLM writes from a Transcript, where node labels carry `[m:ss]` or `[h:mm:ss]` stamps.
_Avoid_: notes, summary, mindmap (for the Markdown)

**Mindmap**:
The rendered HTML page built from an Outline, with each stamp turned into a Timestamp link. A malformed stamp, or one past the Source's end, stays as plain text and is reported back as unlinked.
_Avoid_: map, graph, diagram

**Timestamp link**:
A link that opens the Source at a given second, `&t=<s>s` for YouTube and `#t=<s>` for local files.
_Avoid_: jump link, deep link, seek link

## Relationships

- A **Source** has at most one cached **Transcript**
- A **Transcript** contains one or more **Segments**
- A **Segment** is merged from one or more **Fragments**
- A **Vocabulary** is optional and applies to one transcription of a **Source**
- A cached **Transcript** records the **Vocabulary** it was made with, or none. Transcribing with a **Vocabulary** replaces the cached **Transcript** and keeps its ID
- An **Outline** is written from exactly one **Transcript**
- A **Mindmap** renders exactly one **Outline** and resolves its stamps against that **Transcript**'s **Source** and the Source's duration

## Example dialogue

> **Dev:** "The LLM wrote `[4:34]` on the Gauss elimination node. Does it also write the YouTube link?"
> **Domain expert:** "No. The **Outline** only carries the stamp. When we render the **Mindmap**, the tool looks up the **Transcript**'s **Source** and builds the **Timestamp link** itself."
> **Dev:** "And if the transcript spells it 'Gausselminering'?"
> **Domain expert:** "Then you transcribe again with 'Gausselimination' in the **Vocabulary**. The LLM can fix spelling in the **Outline**, but the **Transcript** stays what Pianissimo heard."

## Flagged ambiguities

- "mindmap" was used for both the LLM's Markdown and the rendered page. Resolved: the Markdown is the **Outline**, the page is the **Mindmap**.
- "transcription" means the act of running Pianissimo. The stored result is the **Transcript**.
