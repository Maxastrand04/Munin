# Klang notes

Turns a recorded Swedish lecture into a mindmap whose nodes link back to the moment in the lecture they summarize. Klang's Pianissimo model transcribes, an LLM structures the notes, and deterministic tools do everything else.

## Language

**Source**:
The recording a Transcript was made from, either a YouTube URL or a local audio or video file path.
_Avoid_: input, video, file

**Transcript**:
The cached text of one Source, made of Segments and identified by a Transcript ID, which remembers its Source.
_Avoid_: transcription (for the stored result), text, captions

**Segment**:
One span of speech in a Transcript with a start time, an end time and its text, after fragments are merged and empty spans dropped.
_Avoid_: chunk, line, utterance

**Vocabulary**:
A list of terms, plus a boost strength (alpha), that steers Pianissimo toward spelling those terms correctly.
_Avoid_: glossary, keywords, hotwords

**Outline**:
The nested Markdown the LLM writes from a Transcript, where node labels carry `[m:ss]` stamps.
_Avoid_: notes, summary, mindmap (for the Markdown)

**Mindmap**:
The rendered HTML page built from an Outline, with each stamp turned into a Timestamp link.
_Avoid_: map, graph, diagram

**Timestamp link**:
A link that opens the Source at a given second, `&t=<s>s` for YouTube and `#t=<s>` for local files.
_Avoid_: jump link, deep link, seek link

## Relationships

- A **Source** has at most one cached **Transcript**
- A **Transcript** contains one or more **Segments**
- A **Vocabulary** is optional and applies to one transcription of a **Source**
- An **Outline** is written from exactly one **Transcript**
- A **Mindmap** renders exactly one **Outline** and resolves its stamps against that **Transcript**'s **Source**

## Example dialogue

> **Dev:** "The LLM wrote `[4:34]` on the Gauss elimination node. Does it also write the YouTube link?"
> **Domain expert:** "No. The **Outline** only carries the stamp. When we render the **Mindmap**, the tool looks up the **Transcript**'s **Source** and builds the **Timestamp link** itself."
> **Dev:** "And if the transcript spells it 'Gausselminering'?"
> **Domain expert:** "Then you transcribe again with 'Gausselimination' in the **Vocabulary**. The LLM can fix spelling in the **Outline**, but the **Transcript** stays what Pianissimo heard."

## Flagged ambiguities

- "mindmap" was used for both the LLM's Markdown and the rendered page. Resolved: the Markdown is the **Outline**, the page is the **Mindmap**.
- "transcription" means the act of running Pianissimo. The stored result is the **Transcript**.
