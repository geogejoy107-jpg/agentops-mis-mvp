# Harness-Style AgentOps Operating Spec

## Purpose

This spec turns Harness engineering research into a practical operating model
for building AgentOps MIS with AgentOps MIS itself.

It does not replace `docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md` or
`docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`. Those files define the
control-plane and execution-contract boundaries. This file defines the product
operating discipline: how a human owner, Codex commander, Hermes/OpenClaw
workers, and future remote workers should move real work through MIS without
falling back to loose chat, mock-only demos, or UI scraping.

## Fresh Harness Research Notes

Primary sources checked on 2026-07-03:

- Harness Worker Agents docs:
  `https://developer.harness.io/docs/platform/harness-ai/harness-agents/`
- Harness MCP Server docs:
  `https://developer.harness.io/docs/platform/harness-ai/harness-mcp-server/`
- Harness Policy As Code overview:
  `https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/`
- Harness Services overview:
  `https://developer.harness.io/docs/continuous-delivery/x-platform-cd-features/services/services-overview/`
- Harness Internal Developer Portal overview:
  `https://developer.harness.io/docs/internal-developer-portal/overview`
- Harness IDP Systems and Environments docs:
  `https://developer.harness.io/docs/internal-developer-portal/catalog/data-model/system-entity`
  and `https://developer.harness.io/docs/internal-developer-portal/environment-management/environments`
- Harness Open Source overview:
  `https://developer.harness.io/docs/open-source/overview`
- Harness Scorecards overview:
  `https://developer.harness.io/docs/internal-developer-portal/scorecards/scorecard/`
- Harness Autonomous Worker Agents launch post:
  `https://www.harness.io/blog/introducing-autonomous-worker-agents`

Observed product patterns:

- Worker agents are reusable governed steps with instructions, model
  connectors, optional MCP connectors, typed inputs, environment variables, and
  pipeline placement.
- MCP exposes a resource registry with scoped list/get/create/update/delete and
  execute actions rather than asking agents to scrape browser UI.
- Policy and approvals are enforcement points, not presentation details.
- Services, environments, systems and IDP catalog objects are kept distinct so
  delivery context does not collapse into one dashboard object.
- IDP combines catalog, workflows, scorecards, environment management, plugins,
  and TechDocs as a developer operating surface.
- Scorecards convert quality standards into measurable readiness.
- Production AI agents inherit pipeline, RBAC, approval, policy and audit
  boundaries instead of inventing their own.

## AgentOps MIS Interpretation

AgentOps MIS should not become Harness, and Harness-like systems must not own
the MIS ledger. The useful lesson is the shape of the harness:

```text
customer goal
-> typed task/work packet
-> scoped agent/runtime
-> policy/readiness decision
-> planned work
-> approved exact action when needed
-> execution
-> verification
-> evidence graph
-> delivery report
-> memory candidate
```

MIS remains the authority for workspace, agent, task, Agent Plan, run,
tool call, prepared action, approval, runtime event, evaluation, memory candidate,
artifact, report and audit.

## Operating Modes

### 1. Solo Local Company Mode

The user is the owner/operator. MIS should help them run a small AI team on one
machine:

- create or import work as tasks;
- dispatch work to Codex/Hermes/OpenClaw/local workers through Agent Gateway;
- keep a visible async lane board;
- enforce approval for external writes, destructive actions and commercial
  side effects;
- show run/evidence/quality/audit posture without requiring the owner to read
  terminal logs;
- create memory candidates only after useful verified work.

### 2. Dogfood Engineering Mode

AgentOps MIS uses itself to build itself. The commander may use Codex locally,
Hermes/OpenClaw as real runtime workers, and CI as offline fallback evidence.

Rules:

- every meaningful slice starts as a MIS task or work packet;
- real-runtime claims require real Hermes/OpenClaw evidence when available and
  explicitly authorized;
- CI/offline evidence is labeled as deterministic fallback;
- completed work records acceptance evidence before product claims;
- product docs and memory updates happen only after stable verification.

### 3. Remote Worker Mode

Remote agents may run on another laptop, server, or customer-controlled runtime.
They should never depend on browser UI. They should use:

- Agent Gateway registration/enrollment;
- scoped API key or local token;
- `agentops task pull`, `task claim`, `run start`, `toolcall record`,
  `eval submit`, `audit emit` and future MCP resources;
- work packets that declare allowed commands, forbidden actions, gates,
  evidence targets and redaction rules.

Remote worker mode is not product-complete until scope enforcement, heartbeat
timeout, revocation, session refresh and audit readback are visible in MIS.

## Async Commander Constraints

The commander loop is a product behavior, not only a Codex working style.

Each lane should have:

- `lane_id`
- `objective`
- `owner`
- `runtime`
- `phase`
- `task_id`
- `run_id`
- `packet_hash`
- `blocked_reason`
- `next_command`
- `verification_command`
- `evidence_refs`
- `claim_limit`

Required behavior:

- start another safe lane while CI, live runtime, browser build, or subagent
  work is still running;
- merge completed lane evidence immediately when it is usable;
- never wait for all lanes merely for tidiness;
- state a concrete no-safe-lane reason before intentional serial waiting;
- treat generated DB/token/cache/artifact drift as cleanup work, not product
  evidence.

## Work Packet Constraints

A task is not ready for a real worker until its packet includes:

- workspace id;
- task id;
- assigned agent/runtime;
- objective summary;
- source docs or knowledge refs;
- allowed commands;
- forbidden actions;
- required approvals;
- required verification;
- evidence targets;
- redaction rules;
- product claim limit.

The packet must be small enough for Hermes, OpenClaw, Codex, or a remote worker
to consume without private chat history or full transcripts.

## Real Runtime Constraints

Default safe behavior remains dry-run/offline. Live execution is allowed only
when the operator explicitly confirms it.

Product-readiness claims require:

- explicit `confirm_run` or approved prepared action;
- runtime connector readiness/trust readback;
- run/tool/runtime/evaluation/audit evidence;
- summary/hash storage only;
- no raw prompt, raw response, credentials, private message, full transcript,
  local DB or generated export committed.

If Hermes/OpenClaw is available but a slice uses mock evidence, the claim must
say `mock_or_ci_fallback_only`.

## UI Constraints

The browser UI is for humans:

- command overview;
- task creation;
- lane posture;
- approvals;
- run ledger;
- evidence graph;
- reports;
- memory review;
- connector trust/readiness.

Agents use CLI/API/MCP. They must not scrape Pixel Office, workspace pages or
admin tables to decide what to do.

Pixel Office can be a useful operating map, but it remains a visual read model.
It must route back to formal MIS authority pages and must not become a second
task ledger.

## Scorecard For Product Slices

Each slice should be graded before being called done:

| Check | Pass Requirement |
| --- | --- |
| Task clarity | Has task/work-packet objective and owner |
| Runtime proof | Real runtime evidence or clearly labeled CI/mock fallback |
| Approval wall | High-risk side effect uses exact prepared-action path |
| Verification | Has smoke/build/manual evidence command |
| Ledger writeback | Run/eval/audit/tool/artifact evidence exists or omission explained |
| Redaction | No secrets, raw prompts, raw responses or full transcripts |
| UI usefulness | Human can see current state and next action |
| Memory | Stable lesson becomes candidate, not auto-approved memory |
| Merge hygiene | No DB, env, cache, dist, node_modules or generated export drift |

## Open-Source And Harness Boundary

Allowed to borrow:

- typed resource registry ideas;
- worker-as-step/pipeline thinking;
- policy-decision shape;
- scorecard and catalog concepts;
- self-service workflow patterns;
- MCP resource/tool exposure patterns.

Not allowed:

- vendoring Harness as the MIS authority;
- replacing Agent Plan/Approval Wall/Audit with external platform state;
- claiming production governance because a reference platform supports it;
- exposing broad raw API access to agents without scoped packets and policy
  gates;
- using third-party UI/assets as commercial product surface without license
  review and replacement plan.

## Open-Source Base Adoption Rules

Each GitHub/open-source base or experimental branch must enter through one of
these lanes before it can touch mainline product authority:

| Lane | Allowed use | Must not do |
| --- | --- | --- |
| Research packet | Summarize patterns, licenses, risks, commands and fit. | Claim product integration. |
| Incubator | Run isolated code, demos, adapters or protocol probes. | Read/write production MIS DB or own MIS ledger state. |
| Adapter | Translate external tool output into MIS summaries, hashes and provenance. | Store raw prompts, raw responses, credentials or full transcripts. |
| Read model | Project MIS authority data into a UI/map/report. | Become a second task/run/approval source of truth. |
| First-party migration | Reimplement authority behavior inside MIS with tests. | Vendor a framework that owns workspace/task/run/approval/memory/audit state. |

Merge readiness requires:

- a named MIS authority boundary;
- a work packet or adoption packet;
- exact files and modules touched;
- verification command;
- secret/generated-artifact check;
- product claim limit;
- rollback or isolation plan.

Commercial or multi-user claims require separate RBAC, workspace isolation,
approval, retention and deployment gates. A branch being runnable locally is not
enough to call it customer-ready.

## Next Implementation Slices

1. Add a machine-readable commander lane packet endpoint that mirrors the lane
   fields above.
2. Make a real Hermes/OpenClaw dogfood task consume that lane packet and write
   back run/evidence/scorecard results.
3. Add a worker scorecard read model for task/run detail.
4. Add a remote worker enrollment readback that shows scope, heartbeat,
   revocation and last evidence write.
5. Promote verified dogfood lessons into memory candidates.

## Acceptance

This spec is accepted when:

- `docs/HARNESS_STYLE_AGENTOPS_OPERATING_SPEC.md` exists;
- `scripts/harness_style_agentops_operating_spec_smoke.py` passes;
- the smoke is wired into CI offline smokes;
- the smoke is listed in release evidence;
- no DB, `.env`, token, cache, `node_modules`, `dist`, generated export, raw
  prompt or raw response is committed.
