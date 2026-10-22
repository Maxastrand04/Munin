# ADR-0002: Core does not import MCP

**Decision:** The core library MUST NOT import the MCP SDK or any other transport; adapters such as the MCP server depend on the core, never the reverse.

**Reason:** Two alternatives were weighed. Putting the logic straight into MCP tool handlers is less code on day one, but ties every function to one client protocol. Building a TypeScript website instead would mean reimplementing Pianissimo's decoding and phrase boosting outside Python. The planned product path is a website later, with an HTTP adapter and a server-side LLM loop calling the same tools, so the core has to work unchanged under a second adapter.

**Consequence:** `transcribe`, `get_transcript` and `render_mindmap` are plain Python functions with plain arguments and return values. The MCP adapter only maps tool calls onto them and stays thin enough to rewrite in an afternoon. An import of `mcp` anywhere in the core package breaks this record.

**Date:** 2026-10-22
