# Which model should transcribe English lectures

Research for [#51][i51], feeding the prototype in [#52][i52] and the epic [#50][i50]. Checked on 2026-11-04 against onnx-asr 0.12.0, the version pinned in `uv.lock:413-414`. No model was run and no weights were downloaded.

New terms
- **ONNX**, a file format for trained models that runs without the framework that trained them.
- **ONNX Runtime provider**, the backend that executes an ONNX model, such as the CPU or CoreML.
- **int8**, a model version whose numbers are stored in 8 bits, which makes it smaller and usually a little less accurate.
- **WER**, word error rate, the share of words a model gets wrong, in percent, where lower is better.
- **RTFx**, seconds of audio processed per second of compute, where higher is faster.
- **Fragment**, one raw span of speech as VAD and the speech model return it, before Munin merges Fragments into Segments.
- **merge rule**, the rule in `src/munin/core/segments.py` that joins neighbouring Fragments into one Segment.
- **tokenizer**, the file that turns text into the numbered word pieces a model reads and writes.
- **token**, one of those numbered word pieces.
- **phrase boosting**, adding a bonus to listed terms while the model picks tokens, which is how a Vocabulary steers spelling.
- **transducer**, a decoder that walks the audio frame by frame and at each frame emits a token or a blank meaning "nothing here".
- **TDT**, Token-and-Duration Transducer, a transducer that also predicts how many frames to skip.
- **RNN-T**, Recurrent Neural Network Transducer, the plain transducer without duration prediction.
- **CTC**, Connectionist Temporal Classification, a simpler decoder that picks one token per frame with no memory of earlier tokens.
- **AED**, attention encoder-decoder, a decoder that writes tokens one after another while reading the whole clip, as Canary and Whisper do.
- **NeMo**, NVIDIA's training toolkit for speech models.
- **checkpoint**, a saved copy of a trained model, here a `.nemo` file holding the weights and the tokenizer.
- **fine-tune**, further training of an existing model on new data.
- **Parakeet** and **Canary**, NVIDIA's families of speech models, Parakeet with transducer or CTC decoders and Canary with an AED decoder.
- **Whisper**, OpenAI's family of speech models with an AED decoder.
- **Open ASR Leaderboard**, a public benchmark from Hugging Face and collaborators that scores speech models on the same English test sets. ASR means automatic speech recognition.
- **TED-LIUM v3**, a test set of TED talks in that leaderboard.

## Answer

Use Parakeet TDT 0.6B v3, repo [`istupakov/parakeet-tdt-0.6b-v3-onnx`][hf-v3-onnx], with `quantization="int8"`. The fallback is Parakeet TDT 0.6B v2, repo [`istupakov/parakeet-tdt-0.6b-v2-onnx`][hf-v2-onnx].

I pick v3 over the slightly more accurate v2 for one reason: it is the model Pianissimo was built from. Klang fine-tuned Pianissimo from v3 and kept its architecture and tokenizer ([Swedish card][hf-sv]). The vendored `tokenizer.model` in `src/munin/core/_vendor/klang/` is byte for byte the tokenizer inside NVIDIA's v3 checkpoint, so Klang's phrase boosting should work on v3 with no code change, and moving to an English Pianissimo later should be a one-line change.

The accuracy cost is small and points both ways. v2 beats v3 by 0.27 WER points on the mean of the Open ASR Leaderboard's English test sets, and v3 beats v2 by 0.58 points on TED talks, the closest public data to a lecture. v3's real risk is that it detects the language by itself and onnx-asr gives no way to force English. If it drifts out of English on the clip, #52 should switch to v2.

Do not wait for Klang. No English Pianissimo is public, Klang's public page speaks only of Nordic languages, and the move would be easy if it ever comes.

## Comparison

New terms
- **VoxPopuli**, a test set of European Parliament speech.
- **FLEURS**, a test set of short read-aloud clips in many languages.
- **Common Voice**, a test set of crowd-recorded sentences.
- **LibriSpeech**, **AMI**, **Earnings-22**, **GigaSpeech** and **SPGI**, other leaderboard test sets, covering audiobooks, meetings, earnings calls, online audio and financial calls.
- **long-form**, the leaderboard's track for audio over 30 s.
- **signal-to-noise**, how much louder speech is than background noise, measured in decibels (dB), where lower is noisier.
- **CC BY 4.0**, a licence allowing any use, commercial included, as long as the author is credited.
- **MIT** and **Apache 2.0**, permissive software licences that mainly ask you to keep the copyright notice.

Three accuracy figures appear below, and only figures of the same kind can be compared.

- "Mean" is the leaderboard's short-form English mean over 8 test sets, scored with punctuation and case removed. It comes from [the leaderboard paper, v4][paper], [v2's record][eval-v2], [v3's record][eval-v3] and [Canary's card][card-canary]. The live leaderboard's default test sets have since changed, so its current numbers may differ.
- "TED" is that leaderboard's TED-LIUM v3 figure.
- "Vox" is WER on a VoxPopuli test subset, measured by the onnx-asr author [through onnx-asr itself][oa-compare]. This is the only figure that reflects the runtime Munin uses. The page does not say which quantization it used, so treat it as not int8 until shown otherwise.

| Candidate and repo | English accuracy, WER % | Licence | Runs in onnx-asr 0.12.0 on the CPU provider | Outputs punctuation | Fits behind Silero VAD with Segment times intact |
|---|---|---|---|---|---|
| **Parakeet TDT 0.6B v3**, [`istupakov/parakeet-tdt-0.6b-v3-onnx`][hf-v3-onnx] | Mean 6.32, TED 2.80, Vox 6.75 | CC BY 4.0 in [repo metadata][hf-v3-readme] and [NVIDIA's card][card-v3] | Yes, [named in the loader][oa-loader-names] and [typed TDT][oa-loader-types] | Yes, [`.`, `?`, `!` are in its vocabulary][hf-v3-vocab] and [the card says so][card-v3] | Yes |
| **Parakeet TDT 0.6B v2**, [`istupakov/parakeet-tdt-0.6b-v2-onnx`][hf-v2-onnx] | Mean 6.05, TED 3.38, Vox 6.51 | CC BY 4.0 in [repo metadata][hf-v2-readme] and [NVIDIA's card][card-v2] | Yes, same class as v3 | Yes, [same tokens present][hf-v2-vocab] | Yes |
| **Canary 1B v2**, [`istupakov/canary-1b-v2-onnx`][hf-canary-onnx] | Mean 7.15, TED 4.29, Vox 7.42 | CC BY 4.0 in [repo metadata][hf-canary-onnx] and [card][card-canary] | Yes, [AED class][oa-aed], about half Parakeet's speed | Yes, [the default prompt asks for it][oa-canary-prompt] | Yes |
| **Whisper large-v3-turbo**, [`onnx-community/whisper-large-v3-turbo`][hf-turbo-onnx] | Mean 7.83, TED unknown, Vox 14.81 through onnx-asr against 11.54 through `openai-whisper` | MIT on [OpenAI's repo][hf-turbo]. The ONNX repo [declares none][hf-turbo-onnx] | Yes, [type `whisper`][oa-loader-whisper], about a sixth of Parakeet's speed | Yes, [`.`, `?`, `!` are in its vocabulary][hf-turbo-onnx] | Yes |
| **Whisper base**, [`istupakov/whisper-base-onnx`][hf-base-onnx] | Mean and TED not read, Vox 12.76 | Apache 2.0 in [repo metadata][hf-base-onnx] | Yes, [alias `whisper-base`][oa-resolver] | Yes, [same tokens present][hf-base-onnx] | Yes |
| **Parakeet RNN-T 0.6B**, [`istupakov/parakeet-rnnt-0.6b-onnx`][hf-rnnt-onnx] | Mean and TED not read, Vox 6.34 | CC BY 4.0 in [repo metadata][hf-rnnt-onnx] | Yes | **No**, [no `.`, `?`, `!` or capitals in its vocabulary][hf-rnnt-vocab] | Times yes, merge rule degraded |
| **Parakeet CTC 0.6B**, [`istupakov/parakeet-ctc-0.6b-onnx`][hf-ctc-onnx] | Mean and TED not read, Vox 7.22 | CC BY 4.0 in [repo metadata][hf-ctc-onnx] | Yes | **No**, [same vocabulary gap][hf-ctc-vocab] | Times yes, merge rule degraded |
| **Parakeet unified 0.6B**, [`nvidia/parakeet-unified-en-0.6b`][card-unified] | Mean 5.91, TED 3.39, both from NVIDIA's own card, Vox not measured | [NVIDIA Open Model License][card-unified], not CC BY | **Not as published.** NVIDIA ships no ONNX, and neither third-party conversion I checked, [one][hf-unified-a] and [two][hf-unified-b], has the `config.json` or the file names onnx-asr expects | Yes, per card | Yes in principle |
| **Moonshine** | Not looked up, since it cannot run | Not looked up | **No.** Absent from [0.12.0's model list][oa-loader-names] and from `main` at commit [`a2fd753`][oa-main] | Not looked up | Not applicable |

Also supported but not given a row. [Canary 1B Flash and 180M Flash][oa-usage] use the same AED class as Canary 1B v2 and share its boosting problem. The GigaAM, Vosk and T-one models named in the loader are aimed at Russian.

**No candidate needs a newer onnx-asr.** 0.12.0 is [the latest release on PyPI][pypi]. Unreleased `main` adds [revision support and new models][oa-commits], none of which changes this choice.

### How Segment times hold for every candidate

Verified from code. Segment times never touch the speech model. Silero finds the speech spans, and [`vad.py:112`][oa-vad-result] builds each result from the sample positions of the cut, taking only `text` from the speech model. `model.py:41` copies those times into a `Fragment`, and `merge_fragments` keeps the first Fragment's start and the last one's end (`src/munin/core/segments.py:48`). So any model whose `recognize_batch` returns text fits, including Canary and Whisper, which return no token timestamps at all ([`nemo.py`, AED decoding][oa-aed], [`whisper.py`][oa-whisper]).

Two limits come along with this, and neither depends on the model. VAD [cuts any span over 20 s][oa-vad-defaults] at the 20 s mark, even mid-word. And a Timestamp link opens at the start of a Segment, so a term 15 s into a Segment is still 15 s from its link, as it is today.

### What the merge rule needs

Verified from code. A new Segment starts only when the current text ends in `.`, `?` or `!` and the next Fragment does not start lowercase, or when the pause reaches 1.5 s, or when the joined Segment would pass 20 s (`src/munin/core/segments.py:61-67`). Without punctuation, the first condition never fires, so Fragments join until a long pause or the 20 s cap. Times stay correct, but Segments stop following sentences. That rules out Parakeet RNN-T and CTC 0.6B, even though RNN-T has the best Vox figure.

### Accuracy, read carefully

- **Mean and TED figures come from the same test sets, so they can be compared with each other.** Inference: they score the original checkpoints, not the ONNX int8 exports Munin would run, since the leaderboard runs each model through its own toolkit. v3's card shows 6.34 and 2.75 where [its leaderboard record][eval-v3] shows 6.32 and 2.80. I use the record, which the paper's mean agrees with.
- **Vox figures cannot be compared with the mean or TED figures.** They are a different test subset.
- **Per-set detail for v2 against v3.** v2 wins on LibriSpeech clean (1.69 against 1.92), LibriSpeech other (3.19 against 3.59), AMI meetings (11.16 against 11.39), Earnings-22 (11.15 against 11.19), SPGI (2.17 against 3.98) and VoxPopuli (5.95 against 6.09). v3 wins on TED-LIUM (2.80 against 3.38) and GigaSpeech (9.57 against 9.74). Source: [v2's record][eval-v2], [v3's record][eval-v3].
- **Long-form.** The [paper's][paper] long-form track, on audio over 30 s, gives v3 10.7 and Whisper turbo 11.0. It reports no long-form figure for v2. Its sets are CORAAL, Earnings-21, Earnings-22 and TED-LIUM. Munin feeds the model VAD clips of at most 20 s, so this track does not match how Munin runs.
- **Lecture audio.** I found no benchmark on university lectures for any candidate. TED-LIUM is the nearest, with 3 hours of TED talks. Inference: rehearsed talks on a good microphone are easier than a lecture with a room microphone, board-writing pauses and course jargon, so expect worse numbers than TED suggests. v2's card gives [one noise figure][card-v2]: its TED-LIUM WER rises from 3.38 clean to 4.24 at 5 dB signal-to-noise.
- **Int8 WER of the recommended export is unknown.** I found no published int8 WER for the `istupakov` repos. Klang's int8 is a different build, with extra steps before quantizing ([Swedish ONNX card][hf-sv-onnx]), so its small loss of 4.46 to 4.65 on Common Voice Swedish does not carry over.
- **Whisper turbo loses accuracy in this runtime.** Through onnx-asr, its Vox WER is 14.81 against 11.54 in `openai-whisper`, on the [same page][oa-compare]. Parakeet and Canary figures match their originals within 0.01. I do not know the cause.

### Speed, since #52 gates on it

[onnx-asr's English CPU benchmarks][oa-bench], on an AMD Ryzen 7 9800X3D. The page does not name the audio in its text, so treat these as ratios between models, not as a forecast for this machine.

| Model | RTFx, full precision | RTFx, int8 | int8 download |
|---|---:|---:|---:|
| Parakeet TDT v3 | 35.4 | 31.4 | 670 MB |
| Parakeet TDT v2 | 36.8 | 30.5 | 661 MB |
| Canary 1B v2 | 8.3 | 14.9 | 1.03 GB |
| Whisper large-v3-turbo | 3.9 | 5.4 | 1.08 GB |

Download sizes are the encoder and decoder files in each repo's listing. Swedish Pianissimo int8 is [660 MB][hf-sv-onnx].

Inference: #52 passes a model at no more than twice Pianissimo's time. Pianissimo has v3's architecture, so its speed should sit near v3's. Canary at about 2.1 times slower than v3 would miss the gate narrowly, and turbo at about 5.8 times slower would miss it clearly. On this machine, 8 cached Transcripts in `~/Library/Caches/Munin/` show Pianissimo at 15.8 to 19.3 times real time, and ADR-0003 records 13 to 15 times on an M1 Pro.

## Phrase boosting on the chosen model

New terms
- **blank token**, the transducer's "emit nothing" output.
- **logit**, the raw score a model gives a token before picking the highest.

**Verdict: on v3 it should work with no code change, as far as code and file hashes can show. Whether it steers English spelling as well as it does Swedish is untested.**

Verified. What the vendored code assumes, and what v3 provides:

| Assumption in the vendored code | Where | On v3 in onnx-asr 0.12.0 |
|---|---|---|
| The model has `_blank_idx`, and the blank is the last token | `pianissimo_onnx.py:24` | `<blk>` is token 8192 of 8193 in [`vocab.txt`][hf-v3-vocab]. [`asr.py:127`][oa-asr-blank] sets the index |
| Decoding is a private `_decoding` method to replace | `pianissimo_onnx.py:27` | Inherited from [the transducer class][oa-asr-decoding] |
| `_decode`, `_create_state` and `_max_tokens_per_step` exist, and `_decode` returns logits, a step and a state | `pianissimo_onnx.py:35,41,56` | [`NemoConformerTdt`][oa-tdt], the same class Pianissimo loads as, since both configs say `nemo-conformer-tdt` |
| `tokenizer.model` numbers tokens the way the model does | `phrase_boost.py:24,30` | See below |

The tokenizer check is the strongest evidence here. I read the tar headers of [NVIDIA's v3 `.nemo` file][hf-v3-nemo] with HTTP range requests, which fetch only part of a file, and took only its tokenizer, not the weights. Its SHA-256 is `eacec2b0a77f336d4a2ca4a25a7047575d3c2b74de47e997f4c205126ed3135e`, the same as `src/munin/core/_vendor/klang/tokenizer.model`. The `vocab.txt` in the `istupakov` v3 repo and the one in [Klang's Swedish repo][hf-sv-vocab] are also the same file, `d5854467...`. Loading both tokenizers in `sentencepiece`, the tokenizer library the vendored code uses, and walking all 8,192 tokens against `vocab.txt` found 0 mismatches. That walk read tokenizer data and ran no model.

So on v3, `apply_vocabulary` (`src/munin/core/boosting.py:13-16`) calls the same boosting code against the same token numbers and the same decoder class as today. Only the weights differ. The reset on `None`, required by ADR-0009, is a dictionary pop on the loaded object and does not care which weights it holds. `load_recognizer` boosts the same `asr` object the VAD pipeline uses, because [`with_vad` passes `self.asr` along][oa-with-vad].

Inference. Boosting will run without error on v3 and will change the output when a term's tokens are close to winning. Sample encodings look usable: `context switch` becomes 6 tokens and `ID1200` becomes 6 tokens.

Untested, for #52:

- Whether boosting improves English spelling. Klang's only published test is [Swedish names on NeMo][hf-sv], where names spelled right rose from 39% to 64% at alpha 1.0, and wrong insertions appeared at alpha 2.0. Klang says its ONNX code [matches NeMo's results on the original model][hf-sv-onnx]. I did not check that claim.
- The code only re-scores a token when the model has already chosen a non-blank (`pianissimo_onnx.py:42-45`). A term the model hears as silence cannot be rescued.

On the other candidates:

- **v2, the fallback, needs one small change.** Its tokenizer is a different file with [1,024 tokens][hf-v2-vocab], and NVIDIA keeps it only inside [the `.nemo` file][hf-v2-nemo]: 251,396 bytes, SHA-256 `5a3a82c4...`. It also walks clean against `vocab.txt`. `boost()` already takes a `tokenizer_path` argument (`pianissimo_onnx.py:18`), but `boosting.py:16` never passes it. Left alone, a term tokenized with the Swedish tokenizer gets ids up to 8,191 against a 1,024-slot array. `Process` starts with token 1758, so `phrase_boost.py:72` raises `IndexError`. A term whose ids all fall below 1,024 would raise nothing and steer toward the wrong tokens. Fixing this means vendoring a second tokenizer and choosing by model.
- **Canary and Whisper cannot use it.** Canary's vocabulary has no `<blk>`, so `_blank_idx` is never set and `boost()` raises `AttributeError` on any non-empty Vocabulary. `_Whisper` [has no `_blank_idx` either][oa-whisper]. Both also decode with a different algorithm, so the patched loop has no meaning for them. Choosing either would mean no Vocabulary on English lectures or a new boosting implementation.

## The move to English Pianissimo

**Verdict: easy, so it is no reason to wait.** Expect one constant, one comparison of hashes, one rerun of #52's checks and a cache decision. The move is hard only if Klang breaks its own pattern, and even then the known cost is a re-vendor of a few files.

Verified on 2026-11-04. No English Pianissimo is public. Hugging Face's API answers 401 for `KlangAI/pianissimo-en` and `KlangAI/pianissimo-en-onnx`, the answer it gives for missing and private repos alike, [Klang's model list][hf-klang] holds only Swedish and Danish, and [its release page][klang] says "open speech-to-text models for Nordic languages, now covering Swedish and Danish". I found no announced plan for English. Inference: the move may never come. Pianissimo's gain on Swedish came from v3 being weak there, 18.54 down to 4.46 on Common Voice Swedish ([card][hf-sv]). v3 is already at 4.85 on English FLEURS ([card][card-v3]), so a fine-tune has less to win.

### What the two published repos show

Compared at [Swedish `63730c6`][hf-sv-onnx] and [Danish `07f0f28`][hf-da-onnx]. Hashes are SHA-256 fingerprints of each file, from my downloads of the small files and from each repo's `manifest.json`.

| File | Swedish against Danish |
|---|---|
| File names | The same 18 names in both, all at the top level |
| `config.json` | Identical, `f19eee59...`, type `nemo-conformer-tdt` |
| `vocab.txt` | Identical, `d5854467...`, also identical to v3's |
| `tokenizer.model` | Identical, `eacec2b0...`, also identical to v3's |
| `phrase_boost.py` | Identical, `bce21b66...` |
| `pianissimo_onnx.py` | Differs. `boost` and `_boosted_decoding` are identical. Danish adds `quiet_cuts` and `transcribe_long` |
| `nemo128.onnx` | Identical, `5b4a84c5...` |
| Weights, int8 | Differ in content. Encoder 630 MB in both, decoder 30 MB Swedish and 54 MB Danish |
| Licence | CC BY 4.0 on both |

The local `pianissimo_onnx.py` differs from Swedish upstream only in its relative import, as `NOTICE.md` says.

Both cards state that the model keeps "Parakeet v3's architecture and tokenizer" ([Swedish][hf-sv], [Danish][hf-da]). Inference: an English build would keep it too, since keeping the tokenizer is what Klang did twice. That is a pattern, not a promise, and step 2 checks it.

### Steps

These assume #50 has shipped with v3 and that `src/munin/core/model.py` holds one repo per language. Today it holds one constant, `_MODEL_REPO`, and `load_recognizer()` takes no language (`model.py:10,22`). The epic pays for that routing, so I do not count it as part of the move.

1. Note the repo and revision. By pattern the name would be `KlangAI/pianissimo-en-onnx`, which is inference, so read the real one.
2. Fetch the small files only, into an empty folder outside the repo, and compare them with the vendored copies. Expect these hashes: `config.json` `f19eee59...`, `vocab.txt` `d5854467...`, `tokenizer.model` `eacec2b0...`, `phrase_boost.py` `bce21b66...`. Diff `boost` and `_boosted_decoding` against `src/munin/core/_vendor/klang/pianissimo_onnx.py`. Check that `encoder-model.int8.onnx` and `decoder_joint-model.int8.onnx` exist.
3. Read the card's licence and its note on long recordings. The Danish card warns that [VAD gives shorter segments, which reduced accuracy on clean speech in Klang's tests][hf-da-onnx]. Munin keeps VAD regardless, because Segment times come from it.
4. In `src/munin/core/model.py`, change the English repo from `istupakov/parakeet-tdt-0.6b-v3-onnx` to the new one. Keep `quantization="int8"` and the CPU provider.
5. If every hash in step 2 matched, leave `_vendor/klang/` alone. If the tokenizer differs, vendor the new one per ADR-0008, add a per-language tokenizer path in `boosting.py`, and update `NOTICE.md`. This also applies if Klang builds on v2.
6. Rerun #52's checks on the ID1200 clip: speed, memory, 10 Segment starts, merge rule, boosting and a read of the transcript. Run the slow tests.
7. Decide about cached Transcripts. A cached Transcript is returned as is when no Vocabulary is given (`src/munin/core/transcribe.py:124-125`), and a cache entry does not record which model made it (`transcribe.py:220-226`). So old Parakeet Transcripts stay until someone deletes their JSON files or reruns with Vocabulary terms. Inference: Mindmaps already rendered keep working, since Silero sets the times, though a rerun can group Segments differently.
8. Update the docs that name the model: `README.md`, `CONTEXT.md`, and the record the epic writes for the English model. Add Klang's attribution for the new weights.

Do one thing now to make step 7 cheap. Store the model repo in each cache entry when the epic ships, so old English Transcripts can be found later. That is a suggestion for #50, not something this research needs.

## What #52 should check

Load it the way `model.py` does, with onnx-asr's other options unchanged:

```python
asr = onnx_asr.load_model(
    "istupakov/parakeet-tdt-0.6b-v3-onnx",
    quantization="int8",
    providers=["CPUExecutionProvider"],
)
```

Only running it can settle these:

1. **Speed.** Compare with Pianissimo on the same machine and the same audio length. Measure Pianissimo fresh too, and do not reuse benchmark figures from this file.
2. **Memory.** The gate is 4 GB. Pianissimo takes about 2.4 GB here (`README.md:57`). The encoder files are nearly the same size, so I expect a similar figure, but VAD batches 8 clips [by default][oa-vad-batch] and the real peak is unknown.
3. **Language drift.** This is v3's main risk. v3 [detects the language itself][card-v3], and onnx-asr's `language` option [applies only to Whisper and Canary][oa-options]. One [unanswered NeMo discussion][nemo-15104] reports stray characters from other languages on pure English audio. That is one report, not a measurement. ID1200 is a KTH course, and a Swedish accent could plausibly tip short clips toward Swedish, which v3 also knows. That part is inference. Read every Fragment for non-English words. The rule: any Fragment out of English on the 6:32 clip means switch to v2. The clip is far shorter than a lecture, so even one drift there predicts more across a full lecture. The rule has no data behind it, and one stray foreign phrase would also trigger it.
4. **Int8 quality.** No published WER exists for this export. If the transcript reads worse than expected, try leaving out `quantization`, which downloads about 2.5 GB. Only the user's reading can judge this.
5. **Punctuation at VAD cuts.** The model sees each clip as a whole utterance, so it may end every clip with a period and start the next with a capital. Then Segments equal Fragments and the merge rule does nothing. This would not break any time, but it would change how Segments read. Report the count of Fragments per Segment and the median Segment length. For comparison, the 1,580 Segments in the local Pianissimo cache have a median of 6.8 s.
6. **Segment starts.** I expect these to pass, because Silero sets them regardless of the model. Silero's behaviour on this English clip is still unmeasured, so the check stays.
7. **Boosting.** Call `apply_vocabulary(asr, Vocabulary([...], 1.0))` from `munin.core.boosting`, with `asr` as loaded above. Pick terms the unboosted transcript actually got wrong, since a term it already spells right shows nothing. Check that a term gets fixed, that nothing wrong is inserted, that `alpha` at 2.0 does not do harm, and that a later `None` call goes back to unboosted. This answers the Vocabulary item left open in the epic.
8. **Pinning.** `load_model` in 0.12.0 [has no revision argument][oa-load-model], so `load_recognizer` tracks whatever the repo's main branch holds, for Pianissimo today as well. The weights would come from the `istupakov` account, run by the onnx-asr author, as a conversion of NVIDIA's checkpoint. That repo [was last changed in February 2026][hf-v3-onnx]. Decide whether that is acceptable or whether Munin should load from a pinned local copy.

If #52 falls back to v2, boosting needs the small change described above before item 7 can run.

## Sources

Verified means I read the source itself. Inference is marked where it appears.

Model repos and cards, each linked at the commit I read:

- ONNX exports: [Parakeet v3][hf-v3-onnx], [Parakeet v2][hf-v2-onnx], [Canary 1B v2][hf-canary-onnx], [Parakeet RNN-T 0.6B][hf-rnnt-onnx], [Parakeet CTC 0.6B][hf-ctc-onnx], [Whisper base][hf-base-onnx], [Whisper large-v3-turbo][hf-turbo-onnx]
- NVIDIA and OpenAI cards: [Parakeet v3][card-v3], [Parakeet v2][card-v2], [Canary 1B v2][card-canary], [Parakeet unified][card-unified], [Whisper large-v3-turbo][hf-turbo]
- Third-party conversions of Parakeet unified: [eschmidbauer][hf-unified-a], [bobNight][hf-unified-b]
- Leaderboard records and paper: [v3 record][eval-v3], [v2 record][eval-v2], [arXiv 2510.06961v4][paper]
- Checkpoints, tar headers and tokenizers only: [v3 `.nemo`][hf-v3-nemo], [v2 `.nemo`][hf-v2-nemo]

Klang:

- Cards: [Swedish][hf-sv], [Danish][hf-da], [Swedish ONNX][hf-sv-onnx], [Danish ONNX][hf-da-onnx]
- [Klang's Hugging Face account][hf-klang], not pinned, and [its release page][klang], not pinned

onnx-asr at tag `v0.12.0`:

- [Usage][oa-usage], [comparison][oa-compare], [benchmarks][oa-bench]
- Code: [`loader.py`][oa-loader-names], [`resolver.py`][oa-resolver], [`vad.py`][oa-vad-result], [`asr.py`][oa-asr-decoding], [`adapters.py`][oa-options], [`models/nemo.py`][oa-tdt], [`models/whisper.py`][oa-whisper]
- [PyPI release history][pypi], not pinned, and [`main` at `a2fd753`][oa-main]

Other: [NeMo discussion 15104][nemo-15104]

Munin, read in the working tree at branch `48-resizable-explanation-panel`, commit `6fceb46`:

- `src/munin/core/model.py`, `boosting.py`, `segments.py`, `transcribe.py`, `vocabulary.py`
- `src/munin/core/_vendor/klang/pianissimo_onnx.py`, `phrase_boost.py`, `tokenizer.model`, `NOTICE.md`
- `docs/adr/0003-onnx-cpu-provider.md`, `0004-recognizer-is-injected.md`, `0005-transcript-id-from-source-path.md`, `0008-vendored-klang-phrase-boosting.md`, `0009-recognize-takes-vocabulary-per-call.md`, `docs/pcr/0004-one-module-per-dependency.md`
- `CONTEXT.md`, `README.md`, `uv.lock`

The installed wheel's `vad.py`, `asr.py`, `adapters.py`, `loader.py`, `resolver.py`, `models/nemo.py` and `models/whisper.py` are byte-identical to tag `v0.12.0` on GitHub, so the links below match what Munin runs.

Could not read: the leaderboard's own results files, such as `hf-audio/open-asr-leaderboard-results`, which return HTTP 401. That is why Whisper turbo's TED figure and the mean and TED figures for Whisper base, Parakeet RNN-T and Parakeet CTC are missing.

[i50]: https://github.com/Maxastrand04/Munin/issues/50
[i51]: https://github.com/Maxastrand04/Munin/issues/51
[i52]: https://github.com/Maxastrand04/Munin/issues/52
[hf-v3-onnx]: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/tree/8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce
[hf-v3-readme]: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/blob/8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce/README.md
[hf-v3-vocab]: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v3-onnx/blob/8f23f0c03c8761650bdb5b40aaf3e40d2c15f1ce/vocab.txt
[hf-v2-onnx]: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx/tree/0bbb45a3365852604aef28b538a8f066f4ccaa85
[hf-v2-readme]: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx/blob/0bbb45a3365852604aef28b538a8f066f4ccaa85/README.md
[hf-v2-vocab]: https://huggingface.co/istupakov/parakeet-tdt-0.6b-v2-onnx/blob/0bbb45a3365852604aef28b538a8f066f4ccaa85/vocab.txt
[hf-canary-onnx]: https://huggingface.co/istupakov/canary-1b-v2-onnx/tree/5ebc1520cef7b6b318b3526ad17adbfe00bc1bfc
[hf-rnnt-onnx]: https://huggingface.co/istupakov/parakeet-rnnt-0.6b-onnx/tree/e973d3a8e721a5a677b92a2b1b70d2d480e72e76
[hf-rnnt-vocab]: https://huggingface.co/istupakov/parakeet-rnnt-0.6b-onnx/blob/e973d3a8e721a5a677b92a2b1b70d2d480e72e76/vocab.txt
[hf-ctc-onnx]: https://huggingface.co/istupakov/parakeet-ctc-0.6b-onnx/tree/658f956396c5a6e41f23ed50838bdb7d1d1b6056
[hf-ctc-vocab]: https://huggingface.co/istupakov/parakeet-ctc-0.6b-onnx/blob/658f956396c5a6e41f23ed50838bdb7d1d1b6056/vocab.txt
[hf-base-onnx]: https://huggingface.co/istupakov/whisper-base-onnx/tree/998334d3bfe2deba3c8e6821f05388dbf2b706d2
[hf-turbo-onnx]: https://huggingface.co/onnx-community/whisper-large-v3-turbo/tree/360ebcde2559d60bb474678be3c1de9ef347d01a
[hf-turbo]: https://huggingface.co/openai/whisper-large-v3-turbo/blob/41f01f3fe87f28c78e2fbf8b568835947dd65ed9/README.md
[hf-unified-a]: https://huggingface.co/eschmidbauer/parakeet-unified-en-0.6b-onnx/tree/7a16ff98b72e5b0beba6f182a5357c704d977b15
[hf-unified-b]: https://huggingface.co/bobNight/parakeet-unified-en-0.6b-onnx/tree/09e9060322d99c5f070010724786e6ee090fd51d
[card-v3]: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/blob/541d1f99c6b0c3cd0b11a95167540bb8edefd82b/README.md
[card-v2]: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2/blob/ae9ad07059c7c739ffaf932226a8fe64ae2620b0/README.md
[card-canary]: https://huggingface.co/nvidia/canary-1b-v2/blob/d455706339a6b32e1aa40f82c713a482a0c938e2/README.md
[card-unified]: https://huggingface.co/nvidia/parakeet-unified-en-0.6b/blob/fe53cd885760c96b6a5f51a0bfd362cb4584a98b/README.md
[eval-v3]: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/blob/541d1f99c6b0c3cd0b11a95167540bb8edefd82b/.eval_results/open_asr_leaderboard.yaml
[eval-v2]: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2/blob/ae9ad07059c7c739ffaf932226a8fe64ae2620b0/.eval_results/open_asr_leaderboard.yaml
[hf-v3-nemo]: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3/blob/541d1f99c6b0c3cd0b11a95167540bb8edefd82b/parakeet-tdt-0.6b-v3.nemo
[hf-v2-nemo]: https://huggingface.co/nvidia/parakeet-tdt-0.6b-v2/blob/ae9ad07059c7c739ffaf932226a8fe64ae2620b0/parakeet-tdt-0.6b-v2.nemo
[paper]: https://arxiv.org/abs/2510.06961v4
[hf-sv]: https://huggingface.co/KlangAI/pianissimo-sv/blob/b087ed21fd3d0e8bf8aee4495b7352b03ce23c29/README.md
[hf-da]: https://huggingface.co/KlangAI/pianissimo-da/blob/84b50304ce3c0eb4ca5e97c5ee1d6e6423c6e1a9/README.md
[hf-sv-onnx]: https://huggingface.co/KlangAI/pianissimo-sv-onnx/blob/63730c6021234f26b9bbae9a07a04fec39e7a52e/README.md
[hf-da-onnx]: https://huggingface.co/KlangAI/pianissimo-da-onnx/blob/07f0f281017b06158012e463a60ee0e9b4817cab/README.md
[hf-sv-vocab]: https://huggingface.co/KlangAI/pianissimo-sv-onnx/blob/63730c6021234f26b9bbae9a07a04fec39e7a52e/vocab.txt
[hf-klang]: https://huggingface.co/KlangAI
[klang]: https://klang.ai/pianissimo/
[nemo-15104]: https://github.com/NVIDIA-NeMo/Speech/discussions/15104
[pypi]: https://pypi.org/project/onnx-asr/#history
[oa-main]: https://github.com/istupakov/onnx-asr/tree/a2fd7530c01a78727422e592bc67ab98d96a9697/src/onnx_asr/models
[oa-commits]: https://github.com/istupakov/onnx-asr/commit/6e63052eb760a5b5ac565ea70cd7f0e90377967b
[oa-usage]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/docs/usage.md
[oa-compare]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/docs/comparison.md
[oa-bench]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/docs/benchmarks.md
[oa-loader-names]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/loader.py#L36-L55
[oa-loader-types]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/loader.py#L108-L110
[oa-loader-whisper]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/loader.py#L120
[oa-load-model]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/loader.py#L306
[oa-resolver]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/resolver.py#L29-L32
[oa-aed]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/models/nemo.py#L141
[oa-canary-prompt]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/models/nemo.py#L165-L167
[oa-tdt]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/models/nemo.py#L131-L138
[oa-whisper]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/models/whisper.py#L34
[oa-asr-blank]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/asr.py#L126-L127
[oa-asr-decoding]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/asr.py#L179-L192
[oa-vad-result]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/vad.py#L112
[oa-vad-defaults]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/vad.py#L62-L80
[oa-vad-batch]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/vad.py#L102
[oa-with-vad]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/adapters.py#L80
[oa-options]: https://github.com/istupakov/onnx-asr/blob/v0.12.0/src/onnx_asr/adapters.py#L50-L55
