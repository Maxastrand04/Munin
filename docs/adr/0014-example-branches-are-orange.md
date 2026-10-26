# ADR-0014: Everything under an example or exercise is orange

**Decision:** The Mindmap MUST draw every node under an `Övning:` or `Exempel:` node in the reserved orange, and MUST NOT give those nodes their topic's colour.

**Reason:** The first spec for #25 and #27 kept the children of an example or exercise in their topic's colour, so the colour still told the student which topic a step belonged to. It lost because the children of an example or exercise are part of it, such as its solution steps, and painting them in the topic colour made them look like terms. A topic that is itself an example or exercise also has no topic colour to give, so it takes no palette slot and its whole branch is orange.

**Consequence:** A node's colour depends on its ancestors' labels as well as its topic, so the page has to check the whole path to the main topic. The edge into the top example or exercise node of a branch keeps its topic's colour, and that edge is the only place the branch still shows which topic it sits under. A change that brings back topic colours for nodes under an example breaks this record.

**Scope:** `src/munin/core/mindmap_assets/mindmap.js`, node and edge colouring

**Date:** 2026-10-25
