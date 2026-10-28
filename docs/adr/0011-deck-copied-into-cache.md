# ADR-0011: A Deck is a copy in the cache

**Decision:** `read_slides` and `read_deck` MUST copy the Deck into the cache folder, in a file of its own, and `render_mindmap` and `render_deck_mindmap` MUST read Slides from that copy, never from the path the caller gave.

**Reason:** Remembering the caller's path and reopening it at render time was weighed. It stores less, but moving, editing or deleting the PDF after reading it would then break the Mindmap, or quietly show different pages from the ones the LLM wrote the Outline from. A copy keeps the Slides the LLM saw and the Slides the page shows the same. An attached Deck's copy lives outside `<id>.json` because a Vocabulary rerun rewrites that whole file and would otherwise drop the Deck.

**Consequence:** The cache holds one Deck copy per Transcript and one per standalone Deck, and these are separate files, so reading a PDF on its own never touches a copy attached to a Transcript, or the reverse. Reading again replaces the copy it read before. A failed read must leave the earlier copy untouched, so the new copy can only replace the old one once the PDF has read cleanly. Storing the Deck's path in the Transcript entry, or reopening the caller's PDF during render, breaks this record.

**Scope:** `src/munin/core/slides.py`, `read_slides` and `read_deck`; `src/munin/core/mindmap.py`, `render_mindmap` and `render_deck_mindmap`

**Date:** 2026-10-27
