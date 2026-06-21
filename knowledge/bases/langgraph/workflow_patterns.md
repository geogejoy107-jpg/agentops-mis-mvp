# LangGraph Workflow Patterns

LangGraph is useful as a reference for durable graph state, checkpoints, stores, human-in-the-loop pauses, and resumable workflows.

MIS implication:

- Keep runtime state separate from MIS ledger authority.
- Record plan, approval, run, tool, memory, and evaluation evidence outside the graph runtime.
