# Runtime Connector Spec

## Purpose

Runtime connectors let AgentOps MIS observe and govern agent runtimes without becoming the runtime itself. The local ledger remains the source of truth for agents, tasks, runs, tool calls, approvals, evaluations, memory and audit.

## v1.2.1 Tables

- `runtime_connectors`: configured local runtime endpoints and binaries.
- `runtime_events`: health checks, dry-run plans, fixed probes and model discovery attempts.
- `runs`: normalized runtime execution records.
- `evaluations`: quality gate results for probes and imported runs.
- `audit_logs`: hashed metadata for connector actions.

## Default Connectors

- `rtc_hermes_default_gateway`: Hermes gateway health at `HERMES_GATEWAY_URL`.
- `rtc_agnesfallback_cli`: local Agnesfallback CLI fixed probe.
- `rtc_agnesfallback_openai_api`: OpenAI-compatible Agnesfallback API probe.

## Safety Rules

- Health checks are allowed locally.
- Fixed probes are dry-run by default.
- Real fixed probes require `HERMES_ALLOW_REAL_RUN=true` and request `confirm_run:true`.
- Arbitrary runtime tasks remain disabled in v1.2.1.
- No full prompt, transcript, credential or raw command body is stored.
