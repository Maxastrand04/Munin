# ADR-0003: Transcription forces the ONNX CPU provider

**Decision:** Transcription MUST load the Pianissimo ONNX model with `providers=["CPUExecutionProvider"]` and MUST NOT rely on ONNX Runtime's default provider selection.

**Reason:** On macOS the default picks CoreML, which supports only 15 of the model's 38 graph nodes and splits the graph between CoreML and CPU. Measured on an M1 Pro with the int8 model: 46 minutes of audio took 92 minutes on the default, while CPU only ran a 10-minute clip in 41 seconds with VAD and the 7:11 SF1624 lecture in 32 seconds. The MLX build on the Apple GPU is the untested alternative and may be faster, but it needs its own loader and has no proven path for phrase boosting here.

**Consequence:** The model loader in the core sets the provider explicitly. Switching to CoreML, CUDA or MLX is a new decision that amends this record with fresh measurements, not a config tweak.

**Scope:** the core's model loading

**Date:** 2026-10-22
