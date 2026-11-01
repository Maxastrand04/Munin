# ADR-0018: A bad stamp, Slide number or piece of LaTeX fails the render

**Decision:** A render MUST fail, write nothing, and list every problem when any stamp or Slide number cannot be linked or any piece of LaTeX cannot be typeset, and MUST NOT write a page that leaves one as plain text or raw LaTeX.

**Reason:** Writing the page anyway and returning the bad stamps and Slide numbers as `unlinked` and `unlinked_slides` was weighed and lost, and so was returning broken LaTeX as a `broken_latex` list beside the page. The LLM could skip the report and hand the student a page with silent leftovers. The run's last step tells the LLM to reply with only the page link, so a render that succeeds with a report usually ends the run there. A failure that lists every problem at once costs one more render to fix.

**Consequence:** A malformed stamp, one past the Source's end, any stamp against a standalone Deck, a Slide number below 1 or past the Deck's last Slide, any Slide number on a Transcript with no Deck, a Slide number listed twice on one node, and every broken piece of LaTeX are problems in the same error as the shape problems. `RenderResult` carries only the page. Bringing back a partial page with an unlinked or broken-LaTeX report breaks this record.

**Scope:** `src/munin/core/mindmap.py`, `render_mindmap`, `render_deck_mindmap` and `RenderResult`

**Date:** 2026-11-02
