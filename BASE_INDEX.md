# Base Index

This file is the short map of reusable bases and runtime foundations.

## Local Authority

- `base_local_tasks`: canonical local task authority.
- `base_local_memory`: canonical reviewed memory authority.
- `base_local_templates`: canonical template package authority.
- `agentops_mis.db`: local ledger for tasks, runs, tools, approvals, memory, evaluations, artifacts, and audit.

## Runtime Bases

- OpenClaw: live worker/runtime adapter for local customer task execution.
- Hermes: local gateway/runtime adapter for live agent execution when explicitly confirmed.
- Codex: coding collaborator and local implementation runtime.
- Agnesfallback: Hermes-compatible fallback connector on this machine.

## Knowledge Bases

- Markdown files under `knowledge/` and `docs/`.
- SQLite FTS5 index through `knowledge_documents` and `knowledge_fts`.
- Future optional layer: embeddings, hybrid retrieval, and vector database only after the Markdown/SQLite layer is reliable.

## External Bases

- Notion: presentation and external memory/task pages, not audit authority.
- Dify: agent tool/workflow/knowledge ingestion layer, approval-gated for real uploads.
- OpenAI File Search: planned external knowledge retrieval base, approval-gated.
- AnythingLLM: planned self-hosted/private knowledge base.
- Plane, Docmost, Mattermost, W&B, Langfuse, Helicone, AgentOps: reference or planned external bases depending on use case.
