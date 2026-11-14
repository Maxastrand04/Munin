# ADR-0002: Core does not import MCP

**Decision:** The core library MUST NOT import the MCP SDK or any other transport; adapters such as the MCP server depend on the core, never the reverse.

**Reason:** Putting the logic straight into MCP tool handlers was weighed. It is less code on day one, but ties every function to one client protocol. A core free of MCP stays testable and usable without an MCP client. Tests call it as plain Python with no server running, and `scripts/render_demo.py` calls it directly.

**Consequence:** `transcribe`, `get_transcript` and `render_mindmap` are plain Python functions with plain arguments and return values. The MCP adapter only maps tool calls onto them and stays thin enough to rewrite in an afternoon. An import of `mcp` anywhere in the core package breaks this record.

**Date:** 2026-10-22
