# ADR-0020: Math in an Outline is LaTeX

**Decision:** An exempel's or övning's task, step calculations and answer MUST be written in LaTeX, and MUST NOT use a notation of Munin's own, such as names like `rho` or `fraction` that the page maps to symbols.

**Reason:** A mapping from names to symbols was weighed, to spare the LLM LaTeX's backslashes. It lost because no list covers matrices, integrals and the rest of a course, so the LLM would write LaTeX anyway and switch between two notations. The LLM writes LaTeX fluently and would have to learn the mapping from `get_outline_schema` on every run, and a later math renderer for the page reads LaTeX directly.

**Consequence:** JSON silently decodes an unescaped backslash, so `\frac` arrives as a form feed and `\times` as a tab. The check therefore treats a control character in any part but an explanation as a problem. A symbol vocabulary, or a renderer that translates one into LaTeX, breaks this record.

**Scope:** `src/munin/core/outline.py`, `get_outline_schema` and the Outline check

**Date:** 2026-10-29
