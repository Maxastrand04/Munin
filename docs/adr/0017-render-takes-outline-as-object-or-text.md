# ADR-0017: The render functions take the Outline as an object or as text

**Decision:** `render_mindmap`, `render_deck_mindmap` and their MCP tools MUST take `outline` as `dict | str`, and MUST NOT narrow it to `str` or to `dict`.

**Reason:** `outline: str` was weighed and lost, because the LLM then writes JSON inside a JSON string and escapes every quote and LaTeX backslash twice. `outline: dict` was weighed and lost, because the MCP SDK rejects a Markdown Outline before Munin sees it, with its own "Input should be a valid dictionary" error that has no position and never tells the LLM to call `get_outline_schema`. With the union, an object or JSON text arrives as a dict, and anything else arrives as text that Munin parses and rejects with its own message.

**Consequence:** The core parses a `str` itself and reports where parsing broke, and takes a `dict` as parsed. A JSON array at the root still gets the SDK's error, not Munin's. Changing either annotation to one type breaks this record.

**Scope:** `src/munin/core/mindmap.py`, `render_mindmap` and `render_deck_mindmap`; `src/munin/mcp_server.py`, `create_server`

**Date:** 2026-10-29
