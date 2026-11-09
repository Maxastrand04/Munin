# ADR-0024: The Outline samples hold one language each

**Decision:** `get_outline_schema` MUST return the same two samples for every lecture, an example written in Swedish and an exercise written in English, and MUST NOT vary them with the lecture's language.

**Reason:** Three options were weighed. Keeping both samples Swedish was the cheapest, but it shows an English lecture's LLM only Swedish text to copy. Four samples, an example and an exercise in each language, doubles what the LLM reads on every call and changes `samples` from two nodes to four. A `language` parameter on `get_outline_schema` gives each lecture samples in its own language, but it adds an argument to an MCP tool the LLM calls before it writes anything, and the ticket never asked for one. One sample per language keeps the type and the tool as they are and shows the LLM that either language is fine. The schema's description, not the samples, says which language to write in.

**Consequence:** `OutlineSchema.samples` stays a pair, and `get_outline_schema` takes no arguments. A Swedish lecture's LLM sees an English exercise, and an English lecture's LLM sees a Swedish example, so the description's "the lecture's language" is the only language instruction. If LLMs start copying a sample's language into the wrong lecture, the fix is a new decision that amends this record. Adding a language parameter or a second pair of samples without one breaks it.

**Scope:** `src/munin/core/outline.py`, `get_outline_schema` and `OutlineSchema`; `src/munin/mcp_server.py`, the `get_outline_schema` tool

**Date:** 2026-11-08
