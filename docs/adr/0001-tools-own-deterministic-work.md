# ADR-0001: Tools own deterministic work

**Decision:** The LLM MUST NOT produce anything that has one correct answer computable from data, such as timestamp links, source URLs, segment merging, or file paths; the tools compute these and the LLM only writes the Outline.

**Reason:** The alternative was letting the LLM format links and clean the Transcript itself, since it already reads both. It lost because an LLM gets exactly these parts wrong now and then (an off-by-one second, a mangled video ID), and a wrong link is worse than no link. The LLM's job is the part with no single right answer: choosing structure and wording.

**Consequence:** Tool outputs carry only what the LLM needs to decide on, for example `[4:34] text` lines rather than URLs. `render_mindmap` takes a Transcript ID plus the Outline and resolves every timestamp to a Timestamp link itself. A change that asks the LLM to emit a URL, a seconds offset in link form, or a cleaned Transcript breaks this record.

**Date:** 2026-10-22
