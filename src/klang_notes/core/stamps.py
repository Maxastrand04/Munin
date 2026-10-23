"""The `[m:ss]` stamp that Transcript lines carry and Outline labels repeat."""

import re

_SECONDS_PER_MINUTE = 60

_MINUTES_STAMP = re.compile(r"\[(\d+):([0-5]\d)\]")
_HOURS_STAMP = re.compile(r"\[(\d+):([0-5]\d):([0-5]\d)\]")

STAMP = re.compile(r"\[[\d:]*:[\d:]*\]")
"""Matches one stamp candidate: a bracket holding only digits and at least one colon.

The match covers well-formed stamps, such as `[4:34]` and `[1:10:05]`, and
malformed ones, such as `[1:75]` or `[1:]`. `stamp_seconds` tells them apart.
Brackets with no colon or with other characters, such as `[12]` or
`[se nedan]`, never match.
"""


def format_stamp(seconds: float) -> str:
    """Return `m:ss` for a time in seconds, rounded down to the whole second.

    Minutes count past 59, so 4503.9 s reads `75:03`.
    """
    minutes, secs = divmod(int(seconds), _SECONDS_PER_MINUTE)
    return f"{minutes}:{secs:02d}"


def stamp_seconds(stamp: str) -> int | None:
    """Return the seconds offset of a stamp's text, brackets included, or None when it is malformed.

    Two shapes are well-formed:

    - `[m:ss]`, where minutes are one or more digits of any value, so
      `[70:05]` is 4205,
    - `[h:mm:ss]`, where hours are one or more digits, so `[1:10:05]` is 4205
      and `[0:10:05]` is 605.

    Seconds, and the minutes of an `[h:mm:ss]` stamp, are exactly two digits
    from 00 to 59. Anything else is malformed, such as `[1:75]`, `[1:7]`,
    `[1:75:00]`, `[1:5:00]`, `[1:2:3:4]`, `[:05]` or `[1:]`. The function knows
    nothing of any Source, so it never judges a stamp past the end.
    """
    if match := _MINUTES_STAMP.fullmatch(stamp):
        minutes, secs = match.groups()
        return int(minutes) * _SECONDS_PER_MINUTE + int(secs)
    if match := _HOURS_STAMP.fullmatch(stamp):
        hours, minutes, secs = match.groups()
        return (int(hours) * _SECONDS_PER_MINUTE + int(minutes)) * _SECONDS_PER_MINUTE + int(secs)
    return None
