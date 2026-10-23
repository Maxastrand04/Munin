import asyncio
import json
import re
from pathlib import Path

import pytest
from mcp import Client

from klang_notes.core import Fragment, RenderResult, UnlinkedStamp, render_mindmap, transcribe
from klang_notes.core.stamps import stamp_seconds
from klang_notes.mcp_server import create_server

TIMESTAMP_LINK = re.compile(r"file://[^\"'\\\s]*#t=\d+")


def one_sentence(wav: Path):
    """A recognizer that ignores the audio and yields one sentence."""
    return [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")]


def transcript_of(source: Path, cache_dir: Path) -> str:
    return transcribe(source, cache_dir=cache_dir, recognize=one_sentence).transcript_id


def render(source: Path, cache_dir: Path, tmp_path: Path, outline: str) -> RenderResult:
    return render_mindmap(
        transcript_of(source, cache_dir), outline, cache_dir=cache_dir, output_dir=tmp_path / "out"
    )


def link_seconds(result: RenderResult) -> list[int]:
    return [int(link.rsplit("#t=", 1)[1]) for link in TIMESTAMP_LINK.findall(result.page.read_text(encoding="utf-8"))]


def call(server, tool: str, arguments: dict):
    async def run():
        async with Client(server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


def labels(result: RenderResult) -> list[str]:
    text = result.page.read_text(encoding="utf-8").split("const DATA = ", 1)[1]
    return [node["label"] for node in json.JSONDecoder().raw_decode(text)[0]]


# The stamp resolver


def test_stamp_seconds_counts_minutes_past_an_hour():
    """`[70:05]` resolves to 4205 s."""
    assert stamp_seconds("[70:05]") == 4205


def test_stamp_seconds_reads_hour_stamp():
    """`[1:10:05]` resolves to 4205 s."""
    assert stamp_seconds("[1:10:05]") == 4205


def test_stamp_seconds_accepts_leading_zero_hour():
    """An hour field of zero is well-formed, so `[0:10:05]` resolves to 605 s."""
    assert stamp_seconds("[0:10:05]") == 605


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


# Linking against the Source's end


def test_stamp_at_source_end_links(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp exactly at the Source's duration becomes a Timestamp link."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Slutet [0:05]")
    assert link_seconds(result) == [5]


def test_stamp_past_source_end_gets_no_link(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp after the Source's duration gets no Timestamp link."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Slutet [0:06]")
    assert link_seconds(result) == []


def test_stamp_past_source_end_is_reported(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A stamp after the Source's duration is reported as past the end, with its Outline label."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Slutet [0:06]")
    assert result.unlinked == (UnlinkedStamp("Slutet [0:06]", "[0:06]", "past_end"),)


# Malformed stamps


def test_malformed_stamp_gets_no_link(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A malformed stamp gets no Timestamp link."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [1:75]")
    assert link_seconds(result) == []


def test_malformed_stamp_is_reported(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A malformed stamp is reported as malformed, with its Outline label."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [1:75]")
    assert result.unlinked == (UnlinkedStamp("Gauss [1:75]", "[1:75]", "malformed"),)


def test_bad_stamp_stays_in_label_as_text(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A bad stamp stays in its node's label on the page as plain text."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [1:75]")
    assert "Gauss [1:75]" in labels(result)


def test_good_stamp_beside_bad_one_still_links(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A good stamp in the same label as a bad one still becomes a Timestamp link."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [0:02] [1:75]")
    assert link_seconds(result) == [2]


# Brackets that are not stamps


@pytest.mark.parametrize("bracket", ["[se nedan]", "[12]"])
def test_bracket_without_colon_is_not_reported(
    five_second_source: Path, cache_dir: Path, tmp_path: Path, bracket: str
):
    """Bracketed text with no colon or with letters is not a stamp, so it is not reported."""
    result = render(five_second_source, cache_dir, tmp_path, f"# Matriser\n- Gauss {bracket}")
    assert result.unlinked == ()


def test_bracket_without_colon_stays_in_label(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Bracketed text that is not a stamp stays in its node's label."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [se nedan]")
    assert "Gauss [se nedan]" in labels(result)


# The report


def test_outline_without_bad_stamps_reports_none(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """An Outline whose stamps all link reports no unlinked stamps."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser [0:01]\n- Gauss [0:04]")
    assert result.unlinked == ()


def test_unlinked_stamps_follow_outline_order(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Unlinked stamps come in Outline order, left to right in a label, one entry per occurrence."""
    outline = "# Matriser\n- Gauss [1:75]\n- Slutet [1:75] [0:09]"
    result = render(five_second_source, cache_dir, tmp_path, outline)
    assert result.unlinked == (
        UnlinkedStamp("Gauss [1:75]", "[1:75]", "malformed"),
        UnlinkedStamp("Slutet [1:75] [0:09]", "[1:75]", "malformed"),
        UnlinkedStamp("Slutet [1:75] [0:09]", "[0:09]", "past_end"),
    )


def test_bad_stamp_in_explanation_is_not_reported(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """A bad stamp in a node's explanation prose is not reported."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n\nSe slutet [1:75].")
    assert result.unlinked == ()


def test_render_with_bad_stamps_writes_page(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """An Outline with bad stamps still writes the page."""
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [1:75]\n- Slutet [0:09]")
    assert result.page.is_file()


# Rendering again with a corrected Outline


def test_corrected_outline_reports_none(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering again with the bad stamps fixed reports no unlinked stamps."""
    render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [1:75]")
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [0:03]")
    assert result.unlinked == ()


def test_corrected_outline_links_fixed_stamp(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """Rendering again with a fixed stamp overwrites the page with that stamp's link."""
    render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [1:75]")
    result = render(five_second_source, cache_dir, tmp_path, "# Matriser\n- Gauss [0:03]")
    assert link_seconds(result) == [3]


# The MCP tool


def test_mcp_render_mindmap_reports_unlinked_stamps(five_second_source: Path, cache_dir: Path, tmp_path: Path):
    """The render_mindmap tool returns each unlinked stamp's label, stamp and reason."""
    server = create_server(cache_dir=cache_dir, recognize=one_sentence, output_dir=tmp_path / "out")
    transcript_id = call(server, "transcribe", {"source": str(five_second_source)}).structured_content["transcript_id"]
    result = call(server, "render_mindmap", {"transcript_id": transcript_id, "outline": "# Matriser\n- Gauss [1:75]"})
    assert result.structured_content["unlinked"] == [{"label": "Gauss [1:75]", "stamp": "[1:75]", "reason": "malformed"}]
