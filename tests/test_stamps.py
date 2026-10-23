import pytest

from munin.core.stamps import display_stamp, stamp_seconds

# Well-formed stamps


def test_stamp_seconds_reads_zero_stamp():
    """`[0:00]` resolves to 0 s."""
    assert stamp_seconds("[0:00]") == 0


def test_stamp_seconds_accepts_seconds_of_59():
    """A seconds field of 59 is the largest well-formed one, so `[0:59]` resolves to 59 s."""
    assert stamp_seconds("[0:59]") == 59


def test_stamp_seconds_counts_minutes_past_an_hour():
    """`[70:05]` resolves to 4205 s."""
    assert stamp_seconds("[70:05]") == 4205


def test_stamp_seconds_reads_hour_stamp():
    """`[1:10:05]` resolves to 4205 s."""
    assert stamp_seconds("[1:10:05]") == 4205


def test_stamp_seconds_accepts_leading_zero_hour():
    """An hour field of zero is well-formed, so `[0:10:05]` resolves to 605 s."""
    assert stamp_seconds("[0:10:05]") == 605


# Malformed stamps


def test_stamp_seconds_rejects_seconds_of_60():
    """A seconds field of 60, such as `[0:60]`, is malformed."""
    assert stamp_seconds("[0:60]") is None


def test_stamp_seconds_rejects_seconds_over_59():
    """A seconds field over 59, such as `[1:75]`, is malformed."""
    assert stamp_seconds("[1:75]") is None


def test_stamp_seconds_rejects_single_seconds_digit():
    """A single seconds digit, such as `[1:7]`, is malformed."""
    assert stamp_seconds("[1:7]") is None


def test_stamp_seconds_rejects_hour_stamp_minutes_over_59():
    """In an `[h:mm:ss]` stamp a minutes field over 59, such as `[1:75:00]`, is malformed."""
    assert stamp_seconds("[1:75:00]") is None


def test_stamp_seconds_rejects_single_minute_digit_in_hour_stamp():
    """In an `[h:mm:ss]` stamp a single minutes digit, such as `[1:5:00]`, is malformed."""
    assert stamp_seconds("[1:5:00]") is None


@pytest.mark.parametrize("stamp", ["[1:2:3:4]", "[:05]", "[1:]"])
def test_stamp_seconds_rejects_wrong_field_count(stamp: str):
    """A stamp with too many fields or an empty field is malformed."""
    assert stamp_seconds(stamp) is None


# Display stamps


def test_display_stamp_keeps_minutes_under_an_hour():
    """A time under an hour, such as 3599 s, reads `59:59`."""
    assert display_stamp(3599) == "59:59"


def test_display_stamp_shows_hours_from_one_hour():
    """A time of exactly an hour reads `1:00:00`."""
    assert display_stamp(3600) == "1:00:00"


def test_display_stamp_pads_minutes_after_the_hour():
    """6321 s reads `1:45:21`, and 3665 s reads `1:01:05` with two-digit minutes."""
    assert (display_stamp(6321), display_stamp(3665)) == ("1:45:21", "1:01:05")


def test_display_stamp_rounds_down_to_the_whole_second():
    """3600.9 s reads `1:00:00`."""
    assert display_stamp(3600.9) == "1:00:00"
