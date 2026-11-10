# ADR-0027: The transcript render tools share one Outline guidance text

**Decision:** The `render_mindmap` and `render_drawn_outline` tool descriptions MUST take their Outline-writing guidance from one string in `mcp_server.py`, and MUST NOT each carry their own copy or point the LLM at the other tool's description.

**Reason:** A short `render_drawn_outline` description that says "like `render_mindmap`" was weighed and lost. The web app's LLM may only be offered `render_drawn_outline`, and it would then write an Outline without the guidance. Two hand-kept copies were weighed and lost, because every edit to one would have to be made to the other, and a missed edit means the two tools quietly ask for different Outlines.

**Consequence:** Changing how the LLM should write an Outline from a Transcript is one edit, and both tools follow. Each tool keeps its own opening line and its own paragraph on what it returns. A second copy of the guidance, or a description that sends the LLM to another tool for it, breaks this record. `render_deck_mindmap`'s slides-only guidance stays its own, per ADR-0015.

**Scope:** `src/munin/mcp_server.py`, the `render_mindmap` and `render_drawn_outline` tools

**Date:** 2026-11-09
