# PCR-0001: Python 3.12 managed by uv

**Decision:** All project code MUST be Python 3.12, with the environment and dependencies managed by uv.

**Reason:** The transcription stack is Python: onnx-asr, Silero VAD, and Klang's phrase boosting helpers. TypeScript was weighed, since the product may become a website, and lost because it would mean reimplementing the transducer decoding loop and phrase boosting. Python 3.14, the system default on the dev machine, was weighed and lost because prebuilt ONNX Runtime packages were not guaranteed for it; the whole pipeline was verified on 3.12.

**Consequence:** Dependencies live in `pyproject.toml` and the lockfile uv produces. A future frontend may add HTML, CSS and JS output, but no second language runtime for the backend. Moving to another Python version means rechecking that onnx-asr and onnxruntime install and transcribe.

**Date:** 2026-10-22
