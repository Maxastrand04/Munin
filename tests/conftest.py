import json
import shutil
import wave
from pathlib import Path
from types import SimpleNamespace

import onnx_asr
import pytest

from munin.core import Fragment, transcribe

SPEECH = Path(__file__).parent / "fixtures" / "sv_short.m4a"
SAMPLE_RATE = 16_000


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A copy of the speech fixture in a temp folder, so a test may change it."""
    path = tmp_path / "media" / "lecture.m4a"
    path.parent.mkdir()
    shutil.copy(SPEECH, path)
    return path


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def write_deck():
    """Write a PDF with one page per string, each page showing its string in Helvetica, and return its path."""
    return write_pdf


@pytest.fixture
def deck(tmp_path: Path) -> Path:
    """A three-page Deck whose Slides read Matriser, Gausselimination and Determinant."""
    return write_pdf(tmp_path / "decks" / "matriser.pdf", ["Matriser", "Gausselimination", "Determinant"])


def write_pdf(path: Path, pages: list[str]) -> Path:
    page_count = len(pages)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids ["
        + b" ".join(f"{4 + 2 * i} 0 R".encode() for i in range(page_count))
        + f"] /Count {page_count} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for index, text in enumerate(pages):
        stream = f"BT /F1 36 Tf 72 300 Td ({text}) Tj ET".encode()
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 640 480] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * index} 0 R >>".encode()
        )
        objects.append(f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream")
    body = b"%PDF-1.4\n"
    offsets = []
    for number, content in enumerate(objects, start=1):
        offsets.append(len(body))
        body += f"{number} 0 obj\n".encode() + content + b"\nendobj\n"
    xref = len(body)
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return path


@pytest.fixture
def five_second_source(tmp_path: Path) -> Path:
    """A WAV of exactly 5.0 s of silence, so stamps can sit on the Source's end to the second."""
    path = tmp_path / "media" / "five_seconds.wav"
    path.parent.mkdir(exist_ok=True)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(SAMPLE_RATE)
        audio.writeframes(bytes(2 * 5 * SAMPLE_RATE))
    return path


@pytest.fixture
def speech_library(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Fakes onnx-asr, the outside library, and records what each load asked for."""
    library = SimpleNamespace(repos=[], model_arguments=[], vad_arguments=[], silence_breaks=[])

    class FakeAsr:
        asr = SimpleNamespace()

        def with_vad(self, vad, **kwargs):
            library.silence_breaks.append(kwargs.get("min_silence_duration_ms"))
            return self

        def recognize(self, path):
            return [SimpleNamespace(start=1.2, end=3.0, text="Hello there.")]

    def load_model(repo, *args, **kwargs):
        library.repos.append(repo)
        library.model_arguments.append(kwargs)
        return FakeAsr()

    def load_vad(name, *args, **kwargs):
        library.vad_arguments.append(kwargs)
        return object()

    monkeypatch.setattr(onnx_asr, "load_model", load_model)
    monkeypatch.setattr(onnx_asr, "load_vad", load_vad)
    return library


@pytest.fixture
def legacy_transcript_id(source: Path, cache_dir: Path) -> str:
    """A Swedish Transcript whose cache entry is rewritten without its `language`, as before lecture languages existed."""
    transcript_id = transcribe(
        source,
        language="sv",
        cache_dir=cache_dir,
        recognize=lambda wav, vocabulary: [Fragment(1.2, 3.0, "Idag ska vi prata om matriser.")],
    ).transcript_id
    for entry in cache_dir.rglob("*.json"):
        stored = json.loads(entry.read_text(encoding="utf-8"))
        if isinstance(stored, dict) and "language" in stored:
            del stored["language"]
            entry.write_text(json.dumps(stored, ensure_ascii=False), encoding="utf-8")
    return transcript_id
