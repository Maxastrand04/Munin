# PCR-0008: Lint runs on ruff at a pinned version with its default rules

**Decision:** All code MUST pass `uv run ruff check` with ruff pinned to an exact version in the `dev` dependency group and its default rules, and the CI lint check MUST run that same command.

**Reason:** Running ruff in CI with `uvx ruff@<version>` or astral's `ruff-action` was weighed, since neither adds a project dependency. Both lost because they install ruff outside `uv.lock`, which PCR-0007 forbids, and the local command would differ from what CI runs. A version range such as `>=0.17.3,<0.18` was weighed too and lost, because ruff changes what its defaults catch between releases, so `uv lock --upgrade` could turn lint red on a change nobody tied to lint.

**Consequence:** `pyproject.toml` lists `ruff==<version>` and has no rule selection under `[tool.ruff]`, only path exclusions. Raising the ruff version is its own change and fixes whatever the new version reports. Enabling or ignoring a rule, or a lint check that runs anything but `uv run ruff check`, requires challenging this record first.

**Date:** 2026-10-27

