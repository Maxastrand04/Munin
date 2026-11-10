# ADR-0015: The slides-only path has its own entry points

**Decision:** Reading a Deck on its own and rendering against it MUST go through their own functions and MCP tools, `read_deck` and `render_deck_mindmap`, and MUST NOT make `transcript_id` optional on `read_slides` or `render_mindmap`.

**Reason:** Two alternatives were weighed. Making `transcript_id` optional on `read_slides` forces a parameter reorder that breaks every existing call, and its return type would have to grow to carry the new Deck ID. One `render_mindmap(outline, transcript_id=None, deck_id=None)` that takes exactly one ID means fewer tools, but its MCP description would have to teach two kinds of Outline at once, one written from a recording and one from Slides alone, and the transcript path's signature would change even though the ticket keeps that path as it is. Separate entry points leave the transcript path untouched and keep each tool's description about one kind of Outline.

**Consequence:** The MCP server has eight tools, three of them render tools: `render_mindmap`, `render_drawn_outline` and `render_deck_mindmap`. The Outline's JSON structure lives in `get_outline_schema`, shared by every render tool, and the slides-only content guidance lives only in `render_deck_mindmap`'s description. The render functions may share private code, but their public signatures stay apart. Adding an optional ID to `read_slides` or `render_mindmap`, or folding the slides-only guidance into `render_mindmap`'s description, breaks this record.

**Scope:** `src/munin/core/slides.py`, `read_deck`; `src/munin/core/mindmap.py`, `render_deck_mindmap`; `src/munin/mcp_server.py`, `create_server`

**Date:** 2026-11-09
