# PCR-0006: CI leaves out slow and network tests

**Decision:** The CI tests check MUST run `uv run pytest -m "not slow and not network"`, and every test that loads the real Pianissimo model or downloads from the internet MUST carry the `slow` or `network` marker.

**Reason:** Running the whole suite in CI was weighed. It lost because `slow` tests download and load the real model, and `network` tests depend on YouTube and KTH Play staying reachable, so a red check would often mean an outside service failed rather than the code. Setting the marker filter as a pytest default in `pyproject.toml` was weighed too and lost, because it would change what a bare `uv run pytest` does on a developer's machine.

**Consequence:** Locally, `uv run pytest` still runs everything. A new test that needs the model or the network without its marker turns the CI check red or flaky. Browser tests are not left out, so CI installs Chromium.

**Date:** 2026-10-27
