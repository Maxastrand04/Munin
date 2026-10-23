"""Errors the core raises. Adapters turn these into their own error shape."""

from pathlib import Path


class KlangError(Exception):
    """Base for every error the core raises on purpose."""


class SourceError(KlangError):
    """The Source is neither a file nor a YouTube URL, ffmpeg cannot decode it, or its video cannot be downloaded.

    `path` is the path or URL as the caller gave it, or a video's canonical URL
    for a failed download, and the message names it.
    """

    def __init__(self, path: str | Path, reason: str) -> None:
        self.path = str(path)
        self.reason = reason
        super().__init__(f"Cannot read {self.path}: {reason}")


class NoSpeechError(KlangError):
    """The Source decoded, but VAD and Pianissimo found no non-empty speech in it.

    `path` is the path as the caller gave it, and the message names it.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        super().__init__(f"No speech found in {self.path}")


class UnknownTranscriptError(KlangError):
    """No cached Transcript has this ID.

    `transcript_id` is the ID the caller gave, and the message names it.
    """

    def __init__(self, transcript_id: str) -> None:
        self.transcript_id = transcript_id
        super().__init__(f"No Transcript with ID {transcript_id}")


class OutlineError(KlangError):
    """The Outline has no Markdown headings or list items, so it has no nodes to draw."""

    def __init__(self) -> None:
        super().__init__("Outline has no headings or list items to turn into Mindmap nodes")
