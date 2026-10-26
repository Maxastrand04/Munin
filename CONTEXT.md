# Munin

Munin turns a recorded Swedish lecture into a mindmap whose nodes link back to the moment in the lecture they summarize. Klang's Pianissimo model transcribes. Munin does the deterministic work, and the LLM writes the Outline. See [ADR-0001](docs/adr/0001-tools-own-deterministic-work.md).

## Language

**Source**:
The recording a Transcript was made from: a YouTube URL, a KTH Play video URL, or a local audio or video file path. A KTH Play Source is identified by its Kaltura entry ID alone, and its fixed lecture address is `https://play.kth.se/media/t/<entry id>`.
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

**Deck**:
The PDF of lecture slides attached to one Transcript. A Transcript has at most one Deck, and attaching a new one replaces the old.
_Avoid_: slideshow, presentation, PDF

**Slide**:
One page of a Deck, numbered from 1.
_Avoid_: page, frame

**Outline**:
The nested Markdown the LLM writes from a Transcript, where node labels carry `[m:ss]` or `[h:mm:ss]` stamps and `[slide N]` markers.
_Avoid_: notes, summary, mindmap (for the Markdown)

**Mindmap**:
The rendered HTML page built from an Outline, with each stamp turned into a Timestamp link. A malformed stamp, or one past the Source's end, stays as plain text and is reported back as unlinked. A node's panel shows the Slides its markers name, and a marker that is malformed, past the Deck's last Slide, or on a Transcript with no Deck is reported back as unlinked too. A term that appears under several Slide nodes, worded the same, lists every place it appears in each copy's panel.
_Avoid_: map, graph, diagram

**Example or exercise**:
An Outline node whose label, as the Mindmap shows it, starts with `Exempel:` or `Övning:` in any case, plus every node under it. The Mindmap paints it in a reserved orange that no topic gets. `Övning 2:` and `Övningar:` don't count.
_Avoid_: task, problem, worked example

**Timestamp link**:
A link that opens the Source at a given second, `&t=<s>s` for YouTube, `?st=<s>` on the fixed lecture address for KTH Play, and `#t=<s>` for local files.
_Avoid_: jump link, deep link, seek link

## Relationships

- A **Source** has at most one cached **Transcript**
- A **Transcript** contains one or more **Segments**
- A **Segment** is merged from one or more **Fragments**
- A **Vocabulary** is optional and applies to one transcription of a **Source**
- A cached **Transcript** records the **Vocabulary** it was made with, or none. Transcribing with a **Vocabulary** replaces the cached **Transcript** and keeps its ID
- A **Transcript** has at most one **Deck**, which has one or more **Slides**
- A node of an **Outline** lists any number of **Slides**, and a **Slide** can appear on any number of nodes
- An **Outline** is written from exactly one **Transcript**
- A node under an **Example or exercise** is part of it, so a topic that is one takes no topic colour
- A **Mindmap** renders exactly one **Outline** and resolves its stamps against that **Transcript**'s **Source** and the Source's duration, and its Slide markers against that **Transcript**'s **Deck**

## Example dialogue

> **Dev:** "The LLM wrote `[4:34]` on the Gauss elimination node. Does it also write the YouTube link?"
> **Domain expert:** "No. The **Outline** only carries the stamp. When we render the **Mindmap**, the tool looks up the **Transcript**'s **Source** and builds the **Timestamp link** itself."
> **Dev:** "And if the transcript spells it 'Gausselminering'?"
> **Domain expert:** "Then you transcribe again with 'Gausselimination' in the **Vocabulary**. The LLM can fix spelling in the **Outline**, but the **Transcript** stays what Pianissimo heard."

## Flagged ambiguities

- "mindmap" was used for both the LLM's Markdown and the rendered page. Resolved: the Markdown is the **Outline**, the page is the **Mindmap**.
- "transcription" means the act of running Pianissimo. The stored result is the **Transcript**.
