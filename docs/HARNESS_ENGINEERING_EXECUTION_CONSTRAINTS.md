# Harness Engineering Execution Constraints

## Purpose

This spec turns Harness engineering research into operational constraints for
AgentOps MIS delivery work. It complements
`docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md` by defining what an agent,
worker, operator, or future MCP client must receive before it can perform
product-grade work.

The target is a local-first AgentOps MIS harness: the browser is for humans,
the Agent Gateway and CLI/API/MCP packets are for agents, and the MIS ledger is
the authority for plans, runs, approvals, evidence, memory review and audit.

## Research Inputs

The rules here are grounded in:

- `docs/research/HARNESS_ENGINEERING_RESEARCH_BRIEF.md`
- `docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md`
- Harness Open Source: `https://github.com/harness/harness`
- Harness Open Source product page: `https://www.harness.io/open-source`
- Harness Policy As Code overview:
  `https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/`
- OpenAI harness engineering field report:
  `https://openai.com/index/harness-engineering/`
- OpenAI Codex App Server harness article:
  `https://openai.com/index/unlocking-the-codex-harness/`
- Addy Osmani agent harness engineering overview:
  `https://addyosmani.com/blog/agent-harness-engineering/`
- Code-as-agent-harness survey:
  `https://arxiv.org/html/2605.18747v1`
- LangChain observability/evals overview:
  `https://www.langchain.com/resources/llm-observability-tools`

## Non-Negotiable Authority Boundary

Harness, CI, OpenClaw, Hermes, Dify, Codex, local scripts, MCP servers and
future remote workers may execute or observe work, but they must not become the
source of truth for:

- workspace
- agent
- task
- Agent Plan
- run
- tool call
- prepared action
- approval
- runtime event
- evaluation
- memory candidate
- artifact
- delivery report
- audit log

External systems can contribute redacted summaries, stable IDs, source URIs,
hashes, counters, timestamps and provenance. Raw prompts, raw responses,
credentials, private messages, full transcripts, local DB files and generated
exports must not be committed or stored as canonical evidence.

## Work Packet Contract

Every product-grade agent task should be represented as a typed work packet
instead of a loose instruction pasted into chat. A work packet must include:

- `packet_id`
- `packet_kind`
- `packet_version`
- `workspace_id`
- `task_id`
- `agent_id`
- `runtime_connector_id`
- `objective_summary`
- `authority_refs`
- `allowed_commands`
- `forbidden_actions`
- `required_gates`
- `evidence_targets`
- `verification_commands`
- `redaction_rules`
- `claim_limit`

The packet should be small enough for Hermes, OpenClaw, Codex or a remote
worker to consume without full chat history. If a worker needs more context, it
must fetch scoped knowledge or evidence packets through the Agent Gateway.

## Required Gate Chain

A governed execution loop is only product-grade when the chain is visible:

```text
READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD
```

Minimum evidence:

- READ: task/workspace/agent ids plus source spec or knowledge refs
- PLAN: submitted Agent Plan id, immutable plan hash and verification result
- RETRIEVE: knowledge evidence packet hash or explicit no-knowledge rationale
- COMPARE: base/reference comparison or documented no-reference rationale
- EXECUTE: run id, runtime connector id and runtime trust/readiness state
- VERIFY: smoke/test/evaluation ids and pass/warn/fail result
- RECORD: tool/runtime/eval/audit/artifact/memory-review evidence counts

Skipping a gate is allowed only when the packet records a reason and the
acceptance smoke can verify the omission was intentional.

## Receipt Readback Constraint

Operator receipts and readbacks are RECORD-stage feedback sensors. They answer:

- Was the exact copied or confirmed action packet recorded?
- Does the receipt match the current action signature?
- Is the matching receipt stale, missing, recorded, verified or failed?
- Is a control readback attached when the action type requires it?

The readback must be machine-addressable. When an action packet includes
`source`, `action_id` and `action_signature`, the companion receipt query should
support those exact filters and must remain read-only:

```bash
agentops operator action-receipts \
  --source local_harness_proof.governed_launch \
  --action-id local_harness_proof:openclaw \
  --action-signature <signature> \
  --limit 20
```

Scanning the latest receipt rows by eye is acceptable for human orientation, but
it is not sufficient evidence for a governed harness packet. Agents, workers and
future MCP clients need deterministic receipt lookup so they can compare the
current action signature against stale or missing receipts.

They do not answer:

- Did Hermes/OpenClaw finish the run?
- Did the task meet customer acceptance?
- Did an external provider perform an irreversible side effect?

For local harness proof specifically, a `receipt_status` may support operator
coordination, but product proof still requires completed run, tool-call,
runtime event, evaluation, audit, artifact and plan-evidence readbacks. The
packet must say `receipt_presence_is_runtime_success=false` whenever receipt
state is shown beside runtime proof.

## Policy Decision Shape

AgentOps MIS does not need OPA/Rego as a local v1.x dependency, but policy-style
decisions must be explicit. Each gate decision should be representable as:

```json
{
  "policy_id": "agentops.example_policy",
  "policy_version": "v1",
  "target_type": "run",
  "target_id": "run_example",
  "normalized_args_hash": "sha256:...",
  "decision": "allow|deny|warn",
  "enforcement_point": "agent_gateway.runs.start",
  "evidence_refs": ["plan:plan_example", "task:tsk_example"],
  "audit_ref": "aud_example"
}
```

Future policy engines may adapt this shape, but cannot replace Agent Plan,
Approval Wall, workspace scope enforcement, runtime trust, evaluation or audit
authority.

## Approval Wall Constraint

Any external side effect or high-risk tool action must use the exact
prepared-action path:

```text
prepare normalized action
-> hash action
-> checkpoint
-> human or policy approval
-> resume exact action
-> execute once
-> record provider summary/hash
-> audit
```

A generic approval row is not enough to claim exact tool-action governance.
The resumed action hash must match the approved prepared action.

## Real-Runtime Proof Standard

For demo, dogfood or product-readiness claims:

- use real Hermes/OpenClaw/OpenClaw-agent execution when local runtimes are
  available and explicitly authorized;
- label mock/offline evidence as CI fallback, not product-grade proof;
- require `confirm_run` or a prepared-action approval for live execution;
- record only summary/hash/counter/provenance evidence;
- never save full prompt, raw response, token, private message or full
  transcript.

If a runtime is opaque and does not emit internal tool events, the claim limit
must say `summary_only_until_runtime_events_available`.

## Async Lane Constraint

AgentOps MIS should support the same async operating model used to build it.
A commander or worker supervisor should track:

- lane id
- owner agent/runtime
- current phase
- blocked reason or next command
- started/updated timestamps
- evidence refs
- merge/readiness state

Slow CI, live runtime calls, browser builds and subagent work must not block
unrelated safe lanes. A lane can wait only when no independent safe
implementation, verification, docs/spec or integration lane remains.

## UI And CLI Constraint

The human UI should show posture and decisions. It should not be the interface
that agents scrape to understand work.

Agents should use:

- `agentops operator ... --work-packet`
- Agent Gateway API endpoints
- scoped CLI wrappers
- future MCP resources/tools

The UI can link to run graphs, approvals, evidence reports and action receipts,
but the machine-readable source should stay in packet/API/CLI surfaces.

## Product Claims Constraint

Do not claim:

- hosted/shared deployment readiness without hosted auth/RBAC/isolation gates;
- universal per-action governance for opaque runtimes;
- commercial readiness from local dry-run evidence;
- real AI work from mock adapter-only evidence;
- safe external writes without Approval Wall exact-action evidence;
- memory correctness without human memory-review closure;
- open-source platform integration as MIS authority replacement.

Acceptable claim language:

```text
local-first harness slice verified
CI/offline fallback verified
real-runtime dogfood verified for this adapter/run id
summary-only opaque runtime evidence
approval-gated external action prepared, not executed
```

## Implementation Queue

Near-term slices should stay small:

1. Keep run/task/detail UI linked to work-delivery graph evidence.
2. Add work-packet and evidence-graph readbacks to CLI/API surfaces before
   adding new visual dashboards.
3. Make worker supervisors consume the packet contract directly.
4. Run one real local Hermes/OpenClaw task for each product-readiness claim and
   record only safe IDs, hashes, statuses and summaries.
5. Promote lessons as memory candidates, not auto-approved memories.

## Acceptance Requirements

This spec is accepted when:

- this file exists;
- `scripts/harness_engineering_execution_constraints_smoke.py` passes;
- the smoke is wired into CI offline safety smokes;
- the smoke is listed in `scripts/release_evidence_packet_smoke.py`;
- the smoke is listed in `docs/RELEASE_EVIDENCE_PACKET.md`;
- no DB, `.env`, token, cache, `node_modules`, `dist` or generated artifact is
  committed.
