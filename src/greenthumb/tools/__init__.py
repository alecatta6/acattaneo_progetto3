"""The three tools the agent can call.

Each tool is built by a factory rather than declared at module level, because each one
needs dependencies injected — the order repository, the vector store, the clock — and a
module-level tool would have to reach for globals to get them.

Every tool returns ``(content, artifact)``: the content is what the model reads, the
artifact is the structured record the deterministic response layer reads from the turn's
ToolMessages without parsing text (ADR-002, verified in ADR-027).
"""
