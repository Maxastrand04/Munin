# ADR-0006: Generated Mindmaps use the approved Topic circles and Radial rings designs

**Decision:** Replace Markmap with the reviewed static HTML, CSS, and SVG interface.
Topic circles is the default. A small settings control also offers Radial rings.
Both use Linen surfaces, ellipse nodes that shrink with depth, group colours,
shadows, filled selected nodes, and a bordered explanation panel on the right.
Clicking a node moves the view without changing zoom. Branch visibility never
recalculates positions. Timestamp links open the Source independently.

**Reason:** The user selected these two designs through several rounds of
interactive prototypes for issue #14. The previous Markmap layout did not support
the approved arrangement of leaves around each topic.

**Consequence:** The Python renderer embeds all assets and Outline data into one
HTML file. No JavaScript build step or network dependency is introduced. Markdown
headings and list items supply nodes; optional following prose supplies explanations.
Explanation generation remains outside this issue. The reviewed sample explanations
live in the example demo Outline, not in the renderer. The temporary prototype
sources are removed now that their selected behaviour is part of the renderer.

**Date:** 2026-10-23
