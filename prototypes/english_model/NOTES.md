# Prototype #52: Parakeet v3 on the ID1200 clip

Throwaway. Measured 2026-11-05 on an M1 Pro with 16 GB, onnx-asr 0.12.0, int8, CPU provider. Weights: `istupakov/parakeet-tdt-0.6b-v3-onnx` at `8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce`.

Audio: the 391.9 s ID1200 clip, and the Swedish lecture `zESlZxUgcWE` trimmed to the same length. Three rounds, alternating models, each run in a fresh process. Output was identical across rounds for every pair. Load average was 5 to 8 on 8 cores, so trust the ratios more than the absolute times.

## Results

| Model and audio | Median time | Speed | Peak memory |
|---|---:|---:|---:|
| Pianissimo, Swedish lecture | 22.1 s | 17.8x | 2.67 GB |
| Pianissimo, ID1200 | 20.4 s | 19.3x | 2.66 GB |
| Parakeet v3, ID1200 | 15.7 s | 25.0x | 2.47 GB |

**Speed passes.** Parakeet takes 0.71 of Pianissimo's time on the Swedish lecture and 0.77 on the same clip. The gate is 2.0.

**Memory passes.** The peak is 2.47 GB against a 4 GB gate. Resident memory right after loading is 1.27 GB. A full-length lecture was not measured.

**Segment starts pass.** The user listened to 10 evenly spread starts with `uv run python prototypes/english_model/spotcheck.py`, and all 10 were within 2 s. Across all 29 Segment starts, the model also puts its first token at most 0.16 s after the start.

**The merge rule produces sensible Segments.** 36 Fragments become 29 Segments, median 13.8 s, longest 19.9 s. 7 of the 28 boundaries fall mid-sentence. 4 come from the 20 s cap and 3 from a period the model put at a VAD cut, as in "...program and processes." / "Is the fact that...". Pianissimo on the same clip makes 23 Segments with a median of 17.6 s and breaks at the same cap, so this speaker's long runs cause much of it.

**Phrase boosting works.** Terms: `heap`, `PID`, `PCB`, `task_struct`, `getpid`.

- Fixed: "hip section" to "heap section", "PCP" to "PCB", and 4 uses of "P ID" or "P IDs" in 3 Fragments.
- Not fixed: `task_struct` and `getpid`, heard as "task" or "tax structure" and "get a P ID", and one "if section". Boosting gave "get a PID" instead.
- Side effects: one dropped comma. No wrong insertions.
- Alpha 2.0 gave the same output as 1.0.
- A later `None` call returned output identical to the first unboosted run.
- No code change was needed.

This suggests Vocabulary can stay on English lectures, which settles that open item on the epic. Boosting fixes spelling of a sound the model already heard. It does not turn two spoken words into one identifier.

**Language drift: none.** I read all 36 Fragments and all are English, so the research's rule does not trigger a switch to v2. This is one speaker over 6:32.

**Transcript quality passes, in the user's judgment.** My own read: clearly better than Pianissimo on this clip, which wrote "membran", "data suction" and "Mello". One new habit: Parakeet keeps fillers, 19 "uh" or "um" in 854 words against 0 for Pianissimo.

## Verdict

Parakeet TDT 0.6B v3 passes on this machine, so English lectures use it and v2 stays unused.

- Segment starts: 10 of 10 within 2 s, checked by ear by the user
- Transcript quality: acceptable, in the user's judgment ("everything passed in my eyes")
- Vocabulary on English lectures: keep it, since boosting works with no code change
- Fillers in the Transcript: keep
- Weights (research item 8): follow the repo's main branch for now, as Munin does for Pianissimo

## Rerun

```bash
uv run python prototypes/english_model/measure.py prepare
uv run python prototypes/english_model/measure.py speed
uv run python prototypes/english_model/measure.py report
uv run python prototypes/english_model/measure.py offsets
uv run python prototypes/english_model/measure.py boost heap PID PCB task_struct getpid
```
