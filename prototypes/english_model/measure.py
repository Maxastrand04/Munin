"""PROTOTYPE for #52. Throwaway. Lives only on prototype/52-english-model, not main.

Question: how well does Parakeet TDT 0.6B v3 (the pick from #51) run on this
machine, on the 6:32 ID1200 clip, with Pianissimo's Swedish numbers alongside?

    uv run python prototypes/english_model/measure.py prepare
    uv run python prototypes/english_model/measure.py speed
    uv run python prototypes/english_model/measure.py report
    uv run python prototypes/english_model/measure.py boost "term one" "term two"
    uv run python prototypes/english_model/spotcheck.py

Everything lands in prototypes/english_model/work/, which git ignores. Nothing
calls `transcribe()`, so Munin's real Transcript cache stays untouched.
"""

import json
import re
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

from munin.core.boosting import apply_vocabulary
from munin.core.decode import decode_to_wav
from munin.core.segments import Fragment, merge_fragments
from munin.core.vocabulary import Vocabulary
from munin.core.youtube import YouTubeSource, download_audio

WORK = Path(__file__).parent / "work"
RUNS = WORK / "runs"
MODELS = {
    "parakeet-v3": "istupakov/parakeet-tdt-0.6b-v3-onnx",
    "parakeet-v2": "istupakov/parakeet-tdt-0.6b-v2-onnx",
    "pianissimo": "KlangAI/pianissimo-sv-onnx",
}
ID1200 = "BwHP-pZsKNw"
SWEDISH = "zESlZxUgcWE"
# (model, audio) pairs. Parakeet on Swedish audio tells us nothing for the gate.
PAIRS = [("pianissimo", "swedish"), ("pianissimo", "id1200"), ("parakeet-v3", "id1200")]
SPEED_GATE = 2.0
MEMORY_GATE_GB = 4.0


def load(model):
    """Load the way `munin.core.model.load_recognizer` does, with only the repo swapped."""
    import onnx_asr

    providers = ["CPUExecutionProvider"]
    asr = onnx_asr.load_model(MODELS[model], quantization="int8", providers=providers)
    vad = onnx_asr.load_vad("silero", providers=providers)
    return asr, asr.with_vad(vad, min_silence_duration_ms=500)


def recognize(pipeline, wav):
    return [Fragment(r.start, r.end, r.text) for r in pipeline.recognize(str(wav))]


def rss_gb():
    kb = int(subprocess.check_output(["ps", "-o", "rss=", "-p", str(_pid())]))
    return kb * 1024 / 1e9


def peak_gb():
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e9  # bytes on macOS


def _pid():
    import os

    return os.getpid()


def duration_s(wav):
    import wave

    with wave.open(str(wav)) as audio:
        return audio.getnframes() / audio.getframerate()


def prepare():
    WORK.mkdir(exist_ok=True)
    for name, video_id in (("id1200", ID1200), ("swedish_full", SWEDISH)):
        wav = WORK / f"{name}.wav"
        if wav.exists():
            continue
        with tempfile.TemporaryDirectory() as tmp:
            media = download_audio(YouTubeSource(video_id), Path(tmp))
            decode_to_wav(video_id, media, wav)
    length = duration_s(WORK / "id1200.wav")
    subprocess.run(
        ["ffmpeg", "-y", "-nostdin", "-v", "error", "-i", str(WORK / "swedish_full.wav"),
         "-t", str(length), "-c", "copy", str(WORK / "swedish.wav")],
        check=True,
    )
    print(f"id1200 {length:.1f} s, swedish {duration_s(WORK / 'swedish.wav'):.1f} s")
    # Pull weights now, so a first download never lands inside a timed run.
    for model in ("pianissimo", "parakeet-v3"):
        started = time.perf_counter()
        load(model)
        print(f"{model} ready after {time.perf_counter() - started:.0f} s")


def child(model, audio, out):
    """One timed run in its own process, so memory figures do not mix between models."""
    started = time.perf_counter()
    _, pipeline = load(model)
    load_s = time.perf_counter() - started
    loaded_rss, loaded_peak = rss_gb(), peak_gb()
    wav = WORK / f"{audio}.wav"
    started = time.perf_counter()
    fragments = recognize(pipeline, wav)
    segments = merge_fragments(fragments)
    Path(out).write_text(json.dumps({
        "model": model, "audio": audio, "duration_s": duration_s(wav), "load_s": load_s,
        # Same span as `transcription_s` in munin.core.transcribe.
        "transcription_s": time.perf_counter() - started,
        "loaded_rss_gb": loaded_rss, "loaded_peak_gb": loaded_peak,
        "run_rss_gb": rss_gb(), "run_peak_gb": peak_gb(),
        "fragments": [asdict(f) for f in fragments],
        "segments": [asdict(s) for s in segments],
    }, ensure_ascii=False))


def speed(rounds=3):
    RUNS.mkdir(parents=True, exist_ok=True)
    # Rounds alternate models, so a machine that warms up or gets busy hits all of them.
    for round_no in range(rounds):
        for model, audio in PAIRS:
            out = RUNS / f"{model}_{audio}_{round_no}.json"
            subprocess.run([sys.executable, __file__, "_child", model, audio, str(out)], check=True)
            r = json.loads(out.read_text())
            print(f"round {round_no} {model:12} {audio:8} {r['transcription_s']:6.1f} s  "
                  f"x{r['duration_s'] / r['transcription_s']:.1f}  peak {r['run_peak_gb']:.2f} GB", flush=True)


def runs(model, audio):
    return [json.loads(p.read_text()) for p in sorted(RUNS.glob(f"{model}_{audio}_*.json"))]


SWEDISH_WORDS = re.compile(r"\b(och|att|det|som|är|jag|vi|inte|för|på|en|ett|den|har|med|så|kan|till)\b", re.IGNORECASE)
ENGLISH_WORDS = re.compile(r"\b(the|and|of|to|is|that|we|you|it|in|this|have|for|what|so|can|a)\b", re.IGNORECASE)
NON_ASCII = re.compile(r"[^\x00-\x7f]")


def report():
    baseline = {}
    print("## Speed and memory\n")
    for model, audio in PAIRS:
        rs = runs(model, audio)
        t = statistics.median(r["transcription_s"] for r in rs)
        baseline[model, audio] = t
        d = rs[0]["duration_s"]
        same = len({json.dumps(r["fragments"]) for r in rs}) == 1
        print(f"{model:12} {audio:8} median {t:5.1f} s of {[round(r['transcription_s'], 1) for r in rs]}, "
              f"x{d / t:.1f}, load {statistics.median(r['load_s'] for r in rs):.1f} s, "
              f"RSS loaded {max(r['loaded_rss_gb'] for r in rs):.2f} GB, "
              f"RSS end {max(r['run_rss_gb'] for r in rs):.2f} GB, "
              f"peak {max(r['run_peak_gb'] for r in rs):.2f} GB, "
              f"output identical across runs: {same}")
    t = baseline["parakeet-v3", "id1200"]
    for key in (("pianissimo", "swedish"), ("pianissimo", "id1200")):
        print(f"parakeet-v3 / {key[0]} on {key[1]}: {t / baseline[key]:.2f} (gate {SPEED_GATE})")
    print(f"memory gate {MEMORY_GATE_GB} GB")

    print("\n## Merge rule\n")
    for model, audio in PAIRS:
        r = runs(model, audio)[0]
        frags, segs = r["fragments"], r["segments"]
        lengths = [s["end"] - s["start"] for s in segs]
        ends = sum(f["text"].strip().endswith((".", "?", "!")) for f in frags)
        print(f"{model:12} {audio:8} {len(frags)} Fragments, {len(segs)} Segments, "
              f"{len(frags) / len(segs):.2f} Fragments per Segment, median {statistics.median(lengths):.1f} s, "
              f"longest {max(lengths):.1f} s, Fragments ending in punctuation {ends}/{len(frags)}")

    print("\n## Language drift, parakeet-v3 on id1200\n")
    for f in runs("parakeet-v3", "id1200")[0]["fragments"]:
        text = f["text"]
        sv, en = len(SWEDISH_WORDS.findall(text)), len(ENGLISH_WORDS.findall(text))
        if NON_ASCII.search(text) or sv > en:
            print(f"[{f['start']:6.1f}] sv={sv} en={en} {text}")

    for model, audio in PAIRS:
        r = runs(model, audio)[0]
        lines = [f"[{int(s['start']) // 60}:{int(s['start']) % 60:02}] {s['text']}" for s in r["segments"]]
        (WORK / f"transcript_{model}_{audio}.txt").write_text("\n".join(lines) + "\n")


def boost(terms, model="parakeet-v3"):
    """Runs every setting on one loaded model, which also shows whether `None` really resets it."""
    asr, pipeline = load(model)
    wav = WORK / "id1200.wav"
    settings = [("none", None), ("alpha1", Vocabulary(terms, 1.0)), ("alpha2", Vocabulary(terms, 2.0)), ("none2", None)]
    results = {}
    for name, vocabulary in settings:
        apply_vocabulary(asr, vocabulary)
        results[name] = recognize(pipeline, wav)
        (WORK / f"boost_{name}.json").write_text(json.dumps([asdict(f) for f in results[name]], ensure_ascii=False))
    print(f"terms {terms}")
    print(f"later None matches first None: {results['none'] == results['none2']}\n")
    for name in ("alpha1", "alpha2"):
        changed = [(a, b) for a, b in zip(results["none"], results[name], strict=True) if a.text != b.text]
        print(f"## {name}, {len(changed)} of {len(results['none'])} Fragments changed\n")
        for a, b in changed:
            print(f"[{a.start:6.1f}] - {a.text}\n         + {b.text}\n")
    for term in terms:
        counts = [sum(term in f.text for f in results[name]) for name, _ in settings]
        print(f"{term!r} exact hits none/alpha1/alpha2/none2: {counts}")


def token_offsets():
    """How far into each Fragment the model places its first token. A proxy for Segment starts, not ears."""
    import onnx_asr

    providers = ["CPUExecutionProvider"]
    asr = onnx_asr.load_model(MODELS["parakeet-v3"], quantization="int8", providers=providers)
    vad = onnx_asr.load_vad("silero", providers=providers)
    pipeline = asr.with_vad(vad, min_silence_duration_ms=500).with_timestamps()
    results = list(pipeline.recognize(str(WORK / "id1200.wav")))
    merged = merge_fragments([Fragment(r.start, r.end, r.text) for r in results])
    starts = {s.start for s in merged}
    # Timestamps are relative to the clip VAD cut, so the first one is the gap before the first word.
    offsets = [(r.start, r.timestamps[0]) for r in results if r.start in starts and r.timestamps]
    gaps = sorted(gap for _, gap in offsets)
    print(f"{len(gaps)} Segment starts, median gap {statistics.median(gaps):.2f} s, largest {gaps[-1]:.2f} s")
    print("largest five:", [(round(start, 1), round(gap, 2)) for start, gap in sorted(offsets, key=lambda o: -o[1])[:5]])


if __name__ == "__main__":
    command, *args = sys.argv[1:]
    match command:
        case "prepare":
            prepare()
        case "speed":
            speed()
        case "report":
            report()
        case "boost":
            boost(args)
        case "offsets":
            token_offsets()
        case "_child":
            child(*args)
