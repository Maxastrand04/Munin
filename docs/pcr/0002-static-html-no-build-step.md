# PCR-0002: Static HTML output with no build step

**Decision:** Any HTML the project produces MUST be self-contained static files written by Python, with JS libraries such as Markmap loaded from a CDN, and the project MUST NOT have a JS build step or `package.json`.

**Reason:** A TypeScript frontend with a bundler was weighed, since the long-term product is a website. It lost for the MVP because the mindmap page needs only Markmap and a few links, and a second toolchain costs setup time on hackathon day without changing what the demo shows. The website path stays open through the core and adapter split in ADR-0002.

**Consequence:** Rendered pages open straight from disk in a browser. They need network access the first time the CDN script loads. Adding a frontend framework, a bundler, or `node_modules` requires challenging this record first.

**Date:** 2026-10-22
