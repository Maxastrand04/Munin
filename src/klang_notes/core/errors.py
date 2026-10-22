"""Errors the core raises. Adapters turn these into their own error shape."""

from pathlib import Path


class KlangError(Exception):
    """Base for every error the core raises on purpose."""


class SourceError(KlangError):
    """The Source path does not exist, is not a file, or ffmpeg cannot decode it.

    `path` is the path as the caller gave it, and the message names it.
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
