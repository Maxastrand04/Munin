# ADR-0006: Generated Mindmaps use the approved Radial rings and Topic circles designs

**Decision:** Replace Markmap with the reviewed static HTML, CSS, and SVG interface.
Radial rings is the default. A small settings control also offers Topic circles.
Both use Linen surfaces, ellipse nodes that shrink with depth, group colours,
shadows, filled selected nodes, and a bordered explanation panel on the right.
The opening view centres the main topic and never zooms out below 55%, so group
labels stay readable; "Show whole Mindmap" may zoom out further to fit every node.
Clicking a node moves the view without changing zoom. Branch visibility never
recalculates positions. Timestamp links open the Source independently.

**Reason:** The user selected these two designs through several rounds of
interactive prototypes for issue #14. The previous Markmap layout did not support
the approved arrangement of leaves around each topic. Radial rings keeps every
group on screen at a readable zoom; Topic circles spreads groups too far apart to
do both.

**Consequence:** The Python renderer embeds all assets and Outline data into one
HTML file. No JavaScript build step or network dependency is introduced. Markdown
headings and list items supply nodes; optional following prose supplies explanations.
Explanation generation remains outside this issue. The reviewed sample explanations
live in the example demo Outline, not in the renderer. The temporary prototype
sources are removed now that their selected behaviour is part of the renderer.
In Topic circles, and in large Mindmaps, some nodes start off-screen.

**Date:** 2026-10-23
