"""Errors the core raises. Adapters turn these into their own error shape."""

from pathlib import Path


class KlangError(Exception):
    """Base for every error the core raises on purpose."""


class SourceError(KlangError):
    """The Source path does not exist, is not a file, or ffmpeg cannot decode it.

    `path` is the path as the caller gave it, and the message names it.
    """

    def __init__(self, path: str | Path, reason: str) -> None:
        raise NotImplementedError


class NoSpeechError(KlangError):
    """The Source decoded, but VAD and Pianissimo found no non-empty speech in it.

    `path` is the path as the caller gave it, and the message names it.
    """

    def __init__(self, path: str | Path) -> None:
        raise NotImplementedError


class UnknownTranscriptError(KlangError):
    """No cached Transcript has this ID.

    `transcript_id` is the ID the caller gave, and the message names it.
    """

    def __init__(self, transcript_id: str) -> None:
        raise NotImplementedError
