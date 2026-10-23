# ADR-0010: PDFs are read with pypdfium2 through one module

**Decision:** Reading a Deck's text and drawing its pages as images MUST use pypdfium2, imported only by `src/munin/core/pdf.py`, and MUST NOT use PyMuPDF or call Poppler's command-line tools.

**Reason:** Three options were weighed. PyMuPDF does text and PNG output in one call, but it is AGPL licensed, and the planned hosted app would then have to publish its source. Poppler's `pdftoppm` and `pdftotext` could be wrapped like ffmpeg, but that adds a second `brew install` for every user. pypdfium2 wraps PDFium, the PDF engine in Chrome. It is Apache and BSD licensed, ships prebuilt wheels that `uv sync` installs, and reads both text and page images.

**Consequence:** `pdf.py` is the one module that imports pypdfium2, per PCR-0004, and returns plain Python values such as strings and PNG bytes. pypdfium2 hands back raw bitmaps, so `pdf.py` encodes PNG itself with the standard library rather than adding Pillow as a second dependency. An `import fitz`, an `import pypdfium2` outside `pdf.py`, or a subprocess call to a Poppler tool breaks this record.

**Scope:** `src/munin/core/pdf.py`

**Date:** 2026-10-23
