# ADR-0020: Math in an Outline is LaTeX

**Decision:** Math in an Outline MUST be LaTeX, and MUST NOT use a notation of Munin's own, such as names like `rho` or `fraction` that the page maps to symbols. A task, an answer and an explanation MUST be plain prose with each piece of math between `$...$`. A step's calculation MUST be LaTeX alone, with no `$`. A single `$` always opens math, and a literal dollar sign MUST be written `\$`.

**Reason:** A mapping from names to symbols was weighed, to spare the LLM LaTeX's backslashes. It lost because no list covers matrices, integrals and the rest of a course, so the LLM would write LaTeX anyway and switch between two notations. The LLM writes LaTeX fluently, and the page's math renderer reads it directly.

Writing a whole task or answer as one LaTeX expression, with Swedish words inside `\text{}`, was the first rule and lost in the #41 prototype. KaTeX treats each `\text{}` as one block that never wraps, so a sentence-long answer ran off the 326px panel. Prose without `\text{}` typeset as italic letters with the spaces gone, as "Skriv flödet av" did in the Gauss sats sample. Plain prose with math between `$...$` wraps like any paragraph and is how a LaTeX document is written. A calculation is all math, so `$` around it would only add a way to get it wrong.

**Consequence:** JSON silently decodes an unescaped backslash, so `\frac` arrives as a form feed and `\times` as a tab. The check therefore treats a control character in any part but an explanation as a problem. An unclosed `$` is broken LaTeX for the render-time LaTeX check to report. A symbol vocabulary, a renderer that translates one into LaTeX, or math outside `$...$` in prose breaks this record.

**Scope:** `src/munin/core/outline.py`, `get_outline_schema` and the Outline check

**Date:** 2026-10-29, revised 2026-10-31
