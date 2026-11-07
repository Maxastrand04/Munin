"""The languages a lecture can be transcribed in."""

from typing import Literal

Language = Literal["sv", "en"]
"""The language a lecture is spoken in, Swedish or English."""


def parse_language(value: str | None) -> Language | None:
    """Return `value` as a Language, or None when the caller gave no language.

    The check is exact, so `"EN"`, `"english"`, `"sv "` and the empty string are
    all rejected. An adapter that treats an empty argument as absent does so
    itself before calling this.

    Raises `LanguageError` naming `value` when it is anything but `"sv"`, `"en"`
    or None.
    """
    raise NotImplementedError
