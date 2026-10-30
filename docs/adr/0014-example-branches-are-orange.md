# ADR-0014: Exempel and övning nodes are orange by their type

**Decision:** The Mindmap MUST paint every exempel and övning node in the reserved orange because of its `type`, and MUST NOT decide that a node is orange from its label.

**Reason:** Reading an `Exempel:` or `Övning:` prefix from the label was weighed and lost, because a prefix the LLM writes can be missing, misspelled, or put on a topic or term, and the page then paints the wrong nodes. Giving an exempel or övning its topic's colour was weighed and lost too, because the node then looks like a term.

**Consequence:** The page adds `Exempel: ` or `Övning: ` before an exempel's or övning's label wherever it names the node, so the LLM never writes the prefix. The Outline check rejects any label that starts with `Exempel:` or `Övning:`, in any case, so a slide, topic or term labelled that way fails the render instead of rendering as a node that looks like an example but isn't orange. A Slide that is only one example or exercise becomes an exempel or övning node under its topic. The edge into an exempel or övning keeps its topic's colour, and that edge is the only place the node still shows which topic it sits under. An exempel or övning directly under the main topic has no topic, so it takes no palette slot and its edge from the main topic is orange. A check of the label text for the colour, letting a prefixed label through the check, or topic colours on exempel and övning nodes, breaks this record.

**Scope:** `src/munin/core/mindmap_assets/mindmap.js`, node and edge colouring; `src/munin/core/outline.py`, the label prefix check

**Date:** 2026-10-30
