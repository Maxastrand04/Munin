# PCR-0003: Tests run on pytest from the tests folder

**Decision:** All automated tests MUST be pytest tests under `tests/`, run with `uv run pytest`.

**Reason:** The standard library's `unittest` was weighed, since it needs no dependency. It lost because the first suite already leans on pytest's `tmp_path` and `monkeypatch` fixtures and on `parametrize`, which `unittest` would replace with hand-written setup and teardown.

**Consequence:** pytest sits in the `dev` dependency group in `pyproject.toml`. Tests that load the real Pianissimo model carry the `slow` marker. A second test runner, or tests outside `tests/`, requires challenging this record first.

**Date:** 2026-10-22
