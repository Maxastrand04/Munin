"""Reading PDFs through pypdfium2. See ADR-0010."""

import re
import struct
import zlib
from pathlib import Path

import pypdfium2

_SCALE = 2.0
_EMPTY_PAGE_TREE = re.compile(rb"<<(?:(?!>>).)*?/Type\s*/Pages\b(?:(?!>>).)*?/Count\s+0\b", re.DOTALL)


def read_pages(path: Path) -> list[tuple[str, bytes]]:
    """Return each page's extracted text and its drawing as PNG bytes, in page order.

    Returns an empty list for a PDF whose page tree declares no pages. PDFium
    refuses to open such a file, with the same error as for a file that is not
    a PDF, so the page tree is checked in the raw bytes. Raises `ValueError`
    when the file is not a PDF that can be opened.
    """
    try:
        document = _open(path)
    except ValueError:
        if _declares_no_pages(path):
            return []
        raise
    try:
        return [_read_page(document[index]) for index in range(len(document))]
    finally:
        document.close()


def page_count(path: Path) -> int:
    """Return the number of pages in the PDF. Raises `ValueError` when it cannot be opened."""
    document = _open(path)
    try:
        return len(document)
    finally:
        document.close()


def page_png(path: Path, number: int) -> bytes:
    """Return page `number`, counted from 1, drawn as PNG bytes. Raises `ValueError` when the PDF cannot be opened."""
    document = _open(path)
    try:
        return _read_page(document[number - 1])[1]
    finally:
        document.close()


def _declares_no_pages(path: Path) -> bool:
    data = path.read_bytes()
    return data.startswith(b"%PDF-") and _EMPTY_PAGE_TREE.search(data) is not None


def _open(path: Path) -> pypdfium2.PdfDocument:
    try:
        return pypdfium2.PdfDocument(path)
    except pypdfium2.PdfiumError as error:
        raise ValueError(str(error)) from error


def _read_page(page: pypdfium2.PdfPage) -> tuple[str, bytes]:
    try:
        text = page.get_textpage().get_text_range()
        bitmap = page.render(scale=_SCALE, rev_byteorder=True)
        return text, _png(bitmap.width, bitmap.height, bitmap.stride, bitmap.n_channels, bytes(bitmap.buffer))
    finally:
        page.close()


def _png(width: int, height: int, stride: int, channels: int, pixels: bytes) -> bytes:
    row = width * channels
    raw = b"".join(b"\x00" + pixels[y * stride : y * stride + row] for y in range(height))
    color_type = {3: 2, 4: 6}[channels]
    header = struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw)) + _chunk(b"IEND", b"")


def _chunk(kind: bytes, data: bytes) -> bytes:
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))
