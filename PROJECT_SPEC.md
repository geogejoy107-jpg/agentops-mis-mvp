# AgentOps MIS Project Spec

AgentOps MIS is the local control plane for a small AI workforce. It does not replace agent runtimes such as Codex, Hermes, OpenClaw, LangGraph, CrewAI, AutoGen, Dify, or OpenHands. It records who did what, why it was allowed, what evidence was produced, and which memory candidates should survive.

## Product Boundary

- Humans use the workspace UI for supervision, approvals, delivery review, reports, and memory review.
- Agents use the Agent Gateway CLI/API/MCP path for task execution, readback, plans, tool evidence, evaluations, audit, and memory proposals.
- MIS stores structured state, short summaries, hashes, IDs, and reviewable records.
- MIS must not store raw secrets, full private transcripts, arbitrary raw prompts, or raw model responses by default.
- Open-source tools may be adopted for storage reliability, retrieval, CI, secret scanning, SBOMs, Git isolation, protocol adapters, and visual references.
- Open-source methods may be adapted for spec workflows, repo maps, human-in-the-loop checkpoints, policy vocabulary, and coding-agent work packages.
- MIS authority objects, including workspace, agent, task, run, tool call, approval, prepared action, memory, evaluation, artifact, audit, and customer delivery state, must remain first-party AgentOps MIS code.

See `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md` before adding any framework,
runtime, visualizer, agent system, policy engine, retrieval system, or workflow
dependency.

## First-Class Objects

- Agent
- Task
- Run
- Tool call
- Approval
- Memory candidate
- Evaluation
- Artifact
- Audit log
- Runtime connector
- Template package
- Base
- Agent plan
- Knowledge document

## Current Priority

The current module is the Agent Work Method Block. It makes every agent follow:

READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD

The first implementation uses Markdown knowledge files, SQLite tables, SQLite FTS5 search, and Agent Gateway/CLI commands. Embeddings and vector databases are later upgrades, not v1 requirements.
