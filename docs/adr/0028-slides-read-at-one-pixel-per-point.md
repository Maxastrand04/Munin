# ADR-0028: Slides are read at one pixel per point, with a size limit

**Decision:** `read_slides` and `read_deck` MUST return each Slide's image drawn at one pixel per point, and MUST return a tool error instead of the Slides when their text and base64 images come to more than 12 MB. The Mindmap page MUST keep drawing Slides at two pixels per point.

**Reason:** Claude Code drops an MCP server that writes a message over 16 MB. At two pixels per point, `read_deck` on an 80 page lecture Deck, `CPU-scheduling.pdf`, wrote 17.3 MB and lost the connection (issue #72). Three fixes were measured on that Deck. JPEG at quality 85 gave 15.0 MB, still close to the limit, and needs Pillow, which ADR-0010 kept out. Drawing at 1.5 pixels per point gave 11.7 MB. Drawing at one pixel per point gave 6.5 MB, and the densest Slide, a table in small print, still reads clearly at 960 pixels wide. Claude shrinks any image wider than about 1568 pixels before reading it, so the larger images cost tokens for pixels it never sees. One pixel per point cuts that Deck from about 147k image tokens to about 55k. The Mindmap page shows a Slide in a panel a student can widen, so it keeps the sharper drawing. The 12 MB limit leaves room for the JSON around the Slides, and allows about 150 pages like these.

**Consequence:** `pdf.read_pages` draws at scale 1.0 and `pdf.page_png` at scale 2.0, so `Slide.image` is not the image the page embeds. `create_server` takes `slide_bytes_limit`, defaulting to `SLIDE_BYTES_LIMIT`, so a test can pass a small one. A Deck over the limit has to be split into smaller PDFs. Returning Slides in pages, or text first with images on request, would lift that limit but changes the tools' contract, and was left out. Raising `read_pages`' scale, sending JPEG, or removing the size check breaks this record.

**Scope:** `src/munin/core/pdf.py`; `src/munin/mcp_server.py`, `_slide_blocks` and `create_server`

**Date:** 2026-11-14
