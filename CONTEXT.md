# Munin

Munin turns a recorded Swedish or English lecture into a mindmap whose nodes link back to the moment in the lecture they summarize. Klang's Pianissimo model transcribes Swedish, and NVIDIA's Parakeet TDT 0.6B v3 transcribes English. Munin does the deterministic work, and the LLM writes the Outline. See [ADR-0001](docs/adr/0001-tools-own-deterministic-work.md).

## Language

**Source**:
The recording a Transcript was made from: a YouTube URL, a KTH Play video URL, or a local audio or video file path. A KTH Play Source is identified by its Kaltura entry ID alone, and its fixed lecture address is `https://play.kth.se/media/t/<entry id>`.
_Avoid_: input, video, file

**Transcript**:
The cached text of one Source, made of Segments and identified by a Transcript ID, which remembers its Source.
_Avoid_: transcription (for the stored result), text, captions

**Lecture language**:
The language a Source is spoken in, `sv` for Swedish or `en` for English, which picks the model that transcribes it: Pianissimo for `sv`, Parakeet for `en`. The caller gives it, and Munin never detects it. A call with no lecture language and nothing cached runs Swedish, and a Transcript cached before lecture languages existed counts as Swedish. Any other value fails before anything downloads or loads.
_Avoid_: locale, transcription language

**Segment**:
One span of speech in a Transcript with a start time, an end time and its text, after Fragments are merged and empty spans dropped.
_Avoid_: chunk, line, utterance

**Fragment**:
One raw span of speech as VAD and the lecture language's model return it, before merging into Segments.
_Avoid_: chunk, piece

**Vocabulary**:
A list of terms, plus a boost strength (alpha) from 0 to 2, that steers Pianissimo toward spelling those terms correctly. Terms are case sensitive. A Vocabulary whose terms are all blank counts as none. Only Swedish lectures take a Vocabulary, so terms on an English lecture fail and write nothing.
_Avoid_: glossary, keywords, hotwords

**Deck**:
The PDF of lecture slides, either attached to one Transcript or read on its own with no Source. A Transcript has at most one Deck, and attaching a new one replaces the old. A Deck read on its own is a standalone Deck, identified by a Deck ID derived from its resolved PDF path, so a moved or renamed PDF is a new Deck. A standalone Deck and the same PDF attached to a Transcript are separate copies.
_Avoid_: slideshow, presentation, PDF

**Slide**:
One page of a Deck, numbered from 1.
_Avoid_: page, frame

**Outline**:
The JSON tree of typed nodes the LLM writes from a Transcript, or from a standalone Deck's Slides alone, following the schema `get_outline_schema` returns. One main-topic node sits at the root, with topic nodes under it, slide nodes under those and term nodes under those. Each node carries a `label`, `stamps` in `m:ss` or `h:mm:ss`, Slide numbers in `slides`, an `explanation` and `children`. Every node carries every part its type has, and a part with nothing in it is `""` or `[]`. An Outline written from a standalone Deck carries no stamps and gives every term node a one to three sentence explanation. Math in any part is LaTeX. A task, an answer, an explanation or a step's reason is prose with its math between `$...$`, and a step's calculation is LaTeX alone.
_Avoid_: notes, summary, mindmap (for the JSON)

**Mindmap**:
The rendered HTML page built from an Outline, with every stamp turned into a Timestamp link and every node's panel showing the Slides it lists. A render that finds any problem writes nothing and lists every problem by its path of labels. A problem is a break from the schema or the nesting rules, a malformed stamp, a stamp past the Source's end, a Slide number below 1 or past the Deck's last Slide, a Slide number listed twice on one node, a label that starts with the page language's example or exercise prefix, a piece of LaTeX the page's KaTeX cannot draw, or any Slide number on a Transcript with no Deck. A Mindmap rendered against a standalone Deck has no Source, so any stamp in its Outline is a problem too. A term that appears under several Slide nodes, worded the same, lists every place it appears in each copy's panel.
_Avoid_: map, graph, diagram

**Example or exercise**:
An Outline node of type `example` or `exercise`. It sits under any node but another example or exercise, has no children, and carries a `task`, a list of `steps` and an `answer` instead of an explanation. Each step has a `calculation` and a `reason`. The Mindmap paints it in a reserved orange that no topic gets, and adds its prefix before its label, `Exempel: ` or `Övning: ` on a Swedish page and `Example: ` or `Exercise: ` on an English one. Its panel shows it as a box headed `Exempel N` or `Övning N`, or `Example N` or `Exercise N`, where N counts each type separately in Outline order, with the task, then the steps and the answer each behind a closed toggle. A Slide that is only one example or exercise is one of these, under its topic, and gets no slide node. No node's label may start with its page language's prefix, so the render fails on a slide, topic or term labelled that way, while the other language's prefix passes.
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
- A cached **Transcript** records its **Lecture language**. A call with no language, or with the same one, returns it, and a call with a different one replaces it and keeps its ID
- A **Vocabulary** applies only to a **Transcript** whose **Lecture language** is Swedish
- A **Transcript** has at most one **Deck**, which has one or more **Slides**
- A node of an **Outline** lists any number of **Slides**, and a **Slide** can appear on any number of nodes
- An **Outline** is written from exactly one **Transcript**, or from exactly one standalone **Deck**
- A node under an **Example or exercise** is part of it, so a topic that is one takes no topic colour
- A **Mindmap** takes its page language from its **Transcript**'s **Lecture language**, and one rendered from a standalone **Deck** is Swedish
- A **Mindmap** renders exactly one **Outline** and resolves its stamps against that **Transcript**'s **Source** and the Source's duration, and its Slide numbers against that **Transcript**'s **Deck**

## Example dialogue

> **Dev:** "The LLM wrote `[4:34]` on the Gauss elimination node. Does it also write the YouTube link?"
> **Domain expert:** "No. The **Outline** only carries the stamp. When we render the **Mindmap**, the tool looks up the **Transcript**'s **Source** and builds the **Timestamp link** itself."
> **Dev:** "And if the transcript spells it 'Gausselminering'?"
> **Domain expert:** "Then you transcribe again with 'Gausselimination' in the **Vocabulary**. The LLM can fix spelling in the **Outline**, but the **Transcript** stays what Pianissimo heard."

## Flagged ambiguities

- "mindmap" was used for both what the LLM writes and the rendered page. Resolved: what the LLM writes is the **Outline**, the page is the **Mindmap**.
- "transcription" means the act of running the lecture language's model, Pianissimo or Parakeet. The stored result is the **Transcript**.
