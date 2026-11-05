"""PROTOTYPE for #52. Throwaway. Spot-check 10 Segment starts by ear.

    uv run python prototypes/english_model/spotcheck.py

Plays the clip from each picked Segment's start. Pass means the Segment's first
words begin within 2 seconds of the audio starting. Answers save after every key,
so you can quit and come back. Run measure.py's `prepare` and `speed` first.
"""

import json
import subprocess
import sys
import termios
import tty
from pathlib import Path

WORK = Path(__file__).parent / "work"
ANSWERS = WORK / "spotcheck.json"
WAV = WORK / "id1200.wav"
PICKS = 10
PLAY_S = 8
MUTE = "--mute" in sys.argv

BOLD, DIM, RESET = "\x1b[1m", "\x1b[2m", "\x1b[0m"


def pick_segments():
    """Evenly spread across the clip, so one stretch of audio cannot hide a problem elsewhere."""
    segments = json.loads((WORK / "runs/parakeet-v3_id1200_0.json").read_text())["segments"]
    step = len(segments) / PICKS
    return [segments[int(i * step)] for i in range(PICKS)]


def read_key():
    fd = sys.stdin.fileno()
    old = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)


def play(start):
    volume = ["-volume", "0"] if MUTE else []
    return subprocess.Popen(
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", *volume, "-ss", str(start), "-t", str(PLAY_S), str(WAV)],
        stdin=subprocess.DEVNULL,
    )


def stamp(seconds):
    return f"{int(seconds) // 60}:{int(seconds) % 60:02}"


def frame(picks, answers, at):
    print("\x1b[2J\x1b[H", end="")
    print(f"{BOLD}Segment starts, ID1200 clip, Parakeet v3{RESET}  {DIM}pass = first words within 2 s{RESET}\n")
    for i, segment in enumerate(picks):
        mark = {"y": "pass", "n": "FAIL"}.get(answers.get(str(i)), "    ")
        pointer = ">" if i == at else " "
        print(f"{pointer} {mark} {DIM}{stamp(segment['start']):>5}{RESET} {segment['text'][:64]}")
    current = picks[at]
    print(f"\n{BOLD}Now playing {stamp(current['start'])}{RESET} ({current['start']:.2f} s)\n{current['text'][:300]}\n")
    passed = sum(a == "y" for a in answers.values())
    print(f"{DIM}{len(answers)}/{PICKS} answered, {passed} pass{RESET}\n")
    print(f"{BOLD}[y]{RESET} pass  {BOLD}[n]{RESET} fail  {BOLD}[r]{RESET} replay  {BOLD}[b]{RESET} back  {BOLD}[q]{RESET} quit")


def main():
    picks = pick_segments()
    answers = json.loads(ANSWERS.read_text()) if ANSWERS.exists() else {}
    at = next((i for i in range(PICKS) if str(i) not in answers), 0)
    player = None
    replay = True
    while True:
        frame(picks, answers, at)
        if replay:
            if player:
                player.kill()
            player = play(picks[at]["start"])
        key = read_key()
        replay = True
        if key == "q":
            break
        if key in "yn":
            answers[str(at)] = key
            ANSWERS.write_text(json.dumps(answers))
            at = min(at + 1, PICKS - 1)
        elif key == "b":
            at = max(at - 1, 0)
        elif key != "r":
            replay = False
    if player:
        player.kill()
    print(f"\n{sum(a == 'y' for a in answers.values())} of {len(answers)} answered pass. Saved to {ANSWERS}")


if __name__ == "__main__":
    main()
