"""Decoding audio and video files to wav, through ffmpeg."""

import os
import subprocess
from pathlib import Path

from munin.core.errors import SourceError

_SAMPLE_RATE_HZ = 16000
_MONO = 1


def decode_to_wav(given: str | os.PathLike[str], media: Path, wav: Path) -> None:
    """Decode the audio track of `media` with ffmpeg into `wav` as 16 kHz mono.

    `given` is how the caller named the Source, and any error names it.

    Raises `SourceError` when ffmpeg is not installed or cannot decode `media`,
    with ffmpeg's last error line as the reason when it printed one.
    """
    command = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(media), "-vn",
        "-ac", str(_MONO), "-ar", str(_SAMPLE_RATE_HZ), "-f", "wav", str(wav),
    ]
    try:
        ffmpeg = subprocess.run(command, check=False, capture_output=True, text=True)
    except FileNotFoundError:
        raise SourceError(given, "ffmpeg is not installed") from None
    if ffmpeg.returncode != 0 or not wav.is_file():
        raise SourceError(given, _last_line(ffmpeg.stderr) or "ffmpeg could not decode it")


def _last_line(text: str) -> str:
    lines = text.strip().splitlines()
    return lines[-1] if lines else ""
