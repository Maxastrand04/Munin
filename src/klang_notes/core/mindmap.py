"""Rendering an Outline into a Mindmap page with Timestamp links."""

from pathlib import Path


def render_mindmap(
    transcript_id: str,
    outline: str,
    *,
    cache_dir: Path | None = None,
    output_dir: Path | None = None,
) -> Path:
    raise NotImplementedError
