"""The `[m:ss]` stamp that Transcript lines carry and Outline labels repeat."""

import re

_SECONDS_PER_MINUTE = 60

STAMP = re.compile(r"\[(\d+):([0-5]\d)\]")
"""Matches one `[m:ss]` stamp. Group 1 is the minutes, group 2 the seconds."""


def format_stamp(seconds: float) -> str:
    """Return `m:ss` for a time in seconds, rounded down to the whole second.

    Minutes count past 59, so 4503.9 s reads `75:03`.
    """
    minutes, secs = divmod(int(seconds), _SECONDS_PER_MINUTE)
    return f"{minutes}:{secs:02d}"


def stamp_seconds(stamp: re.Match[str]) -> int:
    """Return the seconds offset of a `STAMP` match, so `[75:03]` is 4503."""
    return int(stamp[1]) * _SECONDS_PER_MINUTE + int(stamp[2])
