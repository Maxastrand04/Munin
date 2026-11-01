# ADR-0021: The LaTeX check runs the page's own KaTeX in V8

**Decision:** The render-time LaTeX check MUST parse each piece with the same vendored KaTeX build the page embeds, run in V8 through `mini-racer`, and MUST NOT judge LaTeX with a Python parser, a list of known commands, another JS engine or a Node subprocess.

**Reason:** The check promises to accept exactly what the page can draw. A hand-written Python check would drift from KaTeX with every command it missed. `dukpy` was weighed for its small size and lost, because Duktape runs only older JavaScript, so KaTeX might not load on it, and any gap would make the check disagree with the browser. Running `node` was weighed and lost, because every user would need Node installed. V8 is the engine family Chromium runs, so the check and the page parse with the same code on nearly the same engine.

**Consequence:** `mini-racer` is a runtime dependency with its one module, per PCR-0004, and KaTeX's release files are vendored once and read both by that check and by the page template. Upgrading KaTeX changes the check and the page together. A second KaTeX copy, a check that skips KaTeX, or a page and check on different KaTeX versions breaks this record.

**Scope:** `src/munin/core/mindmap.py`, `render_mindmap` and `render_deck_mindmap`, and the module that wraps `mini-racer`

**Date:** 2026-11-02
