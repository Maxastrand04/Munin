# PCR-0005: CI checks run on every pull request

**Decision:** Every CI check MUST run on every pull request event, with no filter on which files changed, and MUST NOT run on pushes to `main`.

**Reason:** A paths filter that skips pull requests touching only Markdown was weighed, since it saves runner minutes on a private repo. It lost because a skipped check shows nothing on the pull request, and a docs change can still break a test that reads `docs/examples/`. Running on pushes to `main` was weighed too and lost, because every change reaches `main` through a pull request that was already checked.

**Consequence:** CI lives in `.github/workflows/ci.yml`, triggered by `pull_request`, and each check is a job in that file. A new commit on a pull request cancels the run still going for the older one. Adding `paths`, `paths-ignore` or a `push` trigger requires challenging this record first.

**Date:** 2026-10-27
