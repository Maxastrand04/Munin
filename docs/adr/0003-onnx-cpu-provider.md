# ADR-0003: Transcription forces the ONNX CPU provider

**Decision:** Transcription MUST load every speech model, Pianissimo and Parakeet alike, with `providers=["CPUExecutionProvider"]` and MUST NOT rely on ONNX Runtime's default provider selection.

**Reason:** On macOS the default picks CoreML, which supports only 15 of Pianissimo's 38 graph nodes and splits the graph between CoreML and CPU. Measured on an M1 Pro with the int8 model: 46 minutes of audio took 92 minutes on the default, while CPU only ran a 10-minute clip in 41 seconds with VAD and the 7:11 SF1624 lecture in 32 seconds. Parakeet has only been measured on the CPU provider, where it ran the 391.9-second ID1200 clip in a median of 15.7 seconds, so it has no evidence that the default would be safe. The MLX build on the Apple GPU is the untested alternative and may be faster, but it needs its own loader and has no proven path for phrase boosting here.

**Consequence:** The model loader in the core sets the provider explicitly for each language. Switching any model to CoreML, CUDA or MLX is a new decision that amends this record with fresh measurements, not a config tweak.

**Scope:** the core's model loading

**Date:** 2026-11-07
