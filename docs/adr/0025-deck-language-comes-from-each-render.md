# ADR-0025: A standalone Deck's page language comes from each render

**Decision:** A Mindmap rendered from a standalone Deck MUST take its page language from the `language` its render call passes, which the LLM judges from the Slides when the user gives none, and Munin MUST NOT detect, store or default it to anything but Swedish.

**Reason:** Three readings were weighed for an English Deck rendered with no language given. Rendering it with no language, so the page stays Swedish, was the literal reading of "when the caller asks for it", but it puts `Exempel:` and `Visa lösning` around English text, the mismatch the English Deck work exists to fix. Having the LLM write the Outline in Swedish kept the page consistent but translated the course away from its own terms. The deck render tool's description already asks the LLM to judge the Deck's language to write the Outline, so the page follows that same judgement. Storing the language on the Deck, or having Munin detect it, was out of scope, and a stored language would go stale on a Deck read once and rendered many times.

**Consequence:** `render_deck_mindmap` takes an optional `language` and treats none as Swedish. The `render_deck_mindmap` tool description and the slides-only prompt ask the LLM to pass the Deck's language when the user gave none. `read_deck` returns no language, and the Deck cache holds none. Adding language detection to Munin, a stored Deck language, or a description that stops asking the LLM to pass the language breaks this record.

**Scope:** `src/munin/core/mindmap.py`, `render_deck_mindmap`; `src/munin/mcp_server.py`, the `render_deck_mindmap` tool and `_slides_only_prompt`

**Date:** 2026-11-08
