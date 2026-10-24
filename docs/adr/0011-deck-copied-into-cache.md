# ADR-0011: An attached Deck is a copy in the cache

**Decision:** `read_slides` MUST copy the Deck into the cache folder, in a file of its own beside its Transcript's entry, and `render_mindmap` MUST read Slides from that copy, never from the path the caller gave.

**Reason:** Remembering the caller's path and reopening it at render time was weighed. It stores less, but moving, editing or deleting the PDF after `read_slides` would then break the Mindmap, or quietly show different pages from the ones the LLM matched to the Transcript. A copy keeps the Slides the LLM saw and the Slides the page shows the same. The copy lives outside `<id>.json` because a Vocabulary rerun rewrites that whole file and would otherwise drop the Deck.

**Consequence:** The cache holds one Deck copy per Transcript, and attaching a new Deck replaces it. A failed read must leave the earlier copy untouched, so the new copy can only replace the old one once the PDF has read cleanly. Storing the Deck's path in the Transcript entry, or reopening the caller's PDF during render, breaks this record.

**Scope:** `src/munin/core/slides.py`, `read_slides`; `src/munin/core/mindmap.py`, `render_mindmap`

**Date:** 2026-10-23
