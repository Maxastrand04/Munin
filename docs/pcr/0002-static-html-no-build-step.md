# PCR-0002: Self-contained static HTML with no build step

**Decision:** Any HTML the project produces MUST be a static file written by Python with every asset embedded, including third-party JS, CSS and fonts such as KaTeX, so it opens from disk with no network access, and the project MUST NOT have a JS build step, a bundler, a `package.json` or `node_modules`.

**Reason:** A TypeScript frontend with a bundler was weighed, since the long-term product is a website. It lost because the page needs only its own small script and a few prebuilt libraries, and a second toolchain costs setup and upkeep without changing what a student sees. Loading libraries from a CDN was weighed too and lost, because a page opened with no network would show its math as raw LaTeX, while the rest of the page, Slide images included, already works offline. The website path stays open through the core and adapter split in ADR-0002.

**Consequence:** A third-party JS library enters the project as its prebuilt release files, vendored into the repo and inlined by the renderer. Python MAY run vendored JS at render time, such as KaTeX's parser for the LaTeX check, through one module per PCR-0004, but never through npm or installed Node packages. Pages grow by the size of every library they embed, and no cap applies. A `<script src="http...">`, a stylesheet or font fetched from a CDN, a `package.json`, `node_modules` or a bundler config breaks this record.

**Date:** 2026-11-01
