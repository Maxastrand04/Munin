# ADR-0014: Example and exercise nodes are orange by their type

**Decision:** The Mindmap MUST paint every example and exercise node in the reserved orange because of its `type`, and MUST NOT decide that a node is orange from its label.

**Reason:** Reading an `Exempel:` or `Example:` prefix from the label was weighed and lost, because a prefix the LLM writes can be missing, misspelled, or put on a topic or term, and the page then paints the wrong nodes. Giving an example or exercise its topic's colour was weighed and lost too, because the node then looks like a term.

**Consequence:** The page adds its language's prefix before an example's or exercise's label wherever it names the node, `Exempel: ` or `Övning: ` on a Swedish page and `Example: ` or `Exercise: ` on an English one, so the LLM never writes the prefix. The Outline check rejects any label that starts with the page language's prefix, in any case, so a slide, topic or term labelled that way fails the render instead of rendering as a node that looks like an example but isn't orange. A Slide that is only one example or exercise becomes an example or exercise node under its topic. The edge into an example or exercise keeps its topic's colour, and that edge is the only place the node still shows which topic it sits under. An example or exercise directly under the main topic has no topic, so it takes no palette slot and its edge from the main topic is orange. A check of the label text for the colour, letting a prefixed label through the check, or topic colours on example and exercise nodes, breaks this record.

**Scope:** `src/munin/core/mindmap_assets/mindmap.js`, node and edge colouring; `src/munin/core/outline.py`, the label prefix check

**Date:** 2026-11-08
