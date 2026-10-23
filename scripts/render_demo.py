"""Render the approved demo Outline using an already cached Transcript."""

import argparse
from pathlib import Path

from munin.core import render_mindmap


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transcript-id", default="5ea1f5df74c8")
    args = parser.parse_args()
    outline = (
        Path(__file__).resolve().parents[1]
        / "docs"
        / "examples"
        / "matriser-outline.md"
    )
    print(render_mindmap(args.transcript_id, outline.read_text(encoding="utf-8")).page)


if __name__ == "__main__":
    main()
