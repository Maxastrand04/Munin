# PCR-0007: CI installs from the lockfile as committed

**Decision:** CI MUST install Python from `.python-version` and dependencies with `uv sync --locked`, so it runs the same Python and package versions as local work.

**Reason:** A plain `uv sync` was weighed, since it never fails on install. It lost because it re-resolves when `uv.lock` is out of date with `pyproject.toml`, so CI would test versions nobody committed. With `--locked`, a stale lockfile turns the check red.

**Consequence:** A pull request that edits dependencies in `pyproject.toml` must commit the updated `uv.lock`. CI never pins its own Python version or installs packages outside the lockfile, apart from system programs such as Chromium and ffmpeg.

**Date:** 2026-10-27
