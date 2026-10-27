# ADR-0006: Generated Mindmaps use the approved Radial rings and Topic circles designs

**Decision:** Replace Markmap with the reviewed static HTML, CSS, and SVG interface.
Radial rings is the default. A small settings control also offers Topic circles.
Both use Linen surfaces, ellipse nodes that shrink with depth, group colours,
shadows, filled selected nodes, and a bordered explanation panel on the right.
In Topic circles, each top-level topic MUST place its subtopics on a full circle
around it, and every deeper topic MUST place its children on an arc that faces
away from its own parent and never reaches a half circle. A child's share of a
circle or arc follows the size of its branch.
The opening view centres the main topic and never zooms out below 55%, so group
labels stay readable; "Show whole Mindmap" may zoom out further to fit every node.
Clicking a node moves the view without changing zoom. Branch visibility never
recalculates positions. Timestamp links open the Source independently.

**Reason:** The user selected these two designs through several rounds of
interactive prototypes for issue #14. The previous Markmap layout did not support
the approved arrangement of leaves around each topic. Radial rings keeps every
group on screen at a readable zoom; Topic circles spreads groups too far apart to
do both. Topic circles first gave every topic a full ring, at every depth, with
equal shares. That lost once every level showed, because a full ring below the
top level puts children back toward the parent, onto the incoming edge and into
the neighbouring branch, and equal shares squeezed big branches into crossing
edges.

**Consequence:** The Python renderer embeds all assets and Outline data into one
HTML file. No JavaScript build step or network dependency is introduced. Markdown
headings and list items supply nodes; optional following prose supplies explanations.
Explanation generation remains outside this issue. The reviewed sample explanations
live in the example demo Outline, not in the renderer. The temporary prototype
sources are removed now that their selected behaviour is part of the renderer.
In Topic circles, and in large Mindmaps, some nodes start off-screen. Topic circles
spreads top-level topics as far from the main topic as their branches need, so a
big Mindmap grows wide rather than letting branches meet. The overlap fixer still
runs last, as a backstop, and a layout that leans on it to separate a branch's own
children breaks this record. Radial rings positions are not touched by this rule.

**Date:** 2026-10-26
