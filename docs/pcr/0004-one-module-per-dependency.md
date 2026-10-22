# PCR-0004: Each external dependency lives in one module

**Decision:** Each external dependency, meaning a third-party library or an outside program, MUST be imported or invoked from exactly one module, and that module MUST NOT wrap a second external dependency.

**Reason:** The project is built for encapsulation, low coupling and high cohesion. The alternative weighed was letting the module that needs a dependency call it directly, as `transcribe.py` calls ffmpeg, which is less code and fewer files. It lost because a dependency spread across modules couples each of them to its API, so a breaking upgrade, such as yt-dlp tracking a YouTube change, touches every caller instead of one file, and a module wrapping two dependencies changes for two unrelated reasons.

**Consequence:** Code that needs a dependency calls the project module that wraps it, never the dependency itself. Adding a dependency means adding or choosing its one module. A second `import yt_dlp`, `import onnx_asr` or `subprocess` call to ffmpeg outside its module breaks this record, and so does one module wrapping both ffmpeg and `platformdirs`. The standard library is not an external dependency.

**Date:** 2026-10-22
