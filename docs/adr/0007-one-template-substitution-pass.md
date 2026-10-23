# ADR-0007: Fill the Mindmap template in one substitution pass

**Decision:** `_page_html` MUST fill every template token in a single substitution pass over the template, and MUST NOT substitute tokens one after another.

**Reason:** Unknown. Found as a comment in `src/munin/core/mindmap.py`, quoted:

> One substitution pass keeps token-like text in the Outline literal.

**Consequence:** Outline text that looks like a token, such as `__CSS__` or `__TITLE__`, reaches the page as written. Chained `str.replace` calls would substitute tokens inside text an earlier pass inserted, so a label could pull CSS, JavaScript or data into the page.

**Scope:** `src/munin/core/mindmap.py`, `_page_html`

**Status:** found

**Date:** 2026-10-23
