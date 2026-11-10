# ADR-0026: The Drawn Outline gives prose as text and math runs

**Decision:** `render_drawn_outline` MUST return each explanation, task, answer and step reason as a sequence of `ProseRun`s, each `text` holding plain text or `math` holding KaTeX's HTML for one piece, and MUST NOT return prose as one HTML string.

**Reason:** One HTML string per part was weighed, with plain text HTML-escaped and math inlined as KaTeX HTML. It is fewer types and one `innerHTML` for the drawing app. It lost because the drawing app then can't tell LLM-written text from Munin's KaTeX output, so a missed escape turns a `<` in an explanation into markup. With runs, the app sets text through `textContent` and only Munin's own KaTeX HTML through `innerHTML`, and the plain text comes back as text, as the ticket asks.

**Consequence:** `ProseRun` has exactly `kind` and `content`, and the MCP tool returns each run as an object with those two keys. A part with nothing in it is an empty sequence. Merging runs into one HTML string, adding HTML anywhere in a text run, or returning prose as raw `$...$` source for the app to typeset breaks this record.

**Scope:** `src/munin/core/mindmap.py`, `render_drawn_outline` and `ProseRun`; `src/munin/mcp_server.py`, the `render_drawn_outline` tool

**Date:** 2026-11-09
