# OpenClaw Base Spec

OpenClaw is a local/live runtime adapter for agent execution. MIS treats OpenClaw as an execution base, not as the ledger authority.

## Reuse

- Live agent execution through worker adapter.
- Local OpenClaw metadata import.
- Runtime health and readiness evidence.

## Boundaries

- Live runs require explicit confirmation.
- Raw OpenClaw transcripts must not be stored in MIS by default.
- Success must be verified through MIS run/tool/evaluation/audit/artifact evidence.
