# Harness Engineering Product Constraints Spec

## Purpose

This spec converts current Harness engineering research into AgentOps MIS
product constraints for local dogfood, open-source base experiments, and future
remote workers.

It is deliberately narrower than a full product roadmap. It answers one
question: when AgentOps MIS uses Harness-style ideas, OpenClaw, Hermes, Codex,
Dify, CI, or another external runtime, what must remain true before we can call
the result product-grade?

## Current Research Inputs

Checked on 2026-07-08:

- Harness Worker Agents:
  `https://developer.harness.io/docs/platform/harness-ai/harness-agents/`
- Harness Policy As Code overview:
  `https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-overview/`
- Harness Policy As Code quickstart:
  `https://developer.harness.io/docs/platform/governance/policy-as-code/harness-governance-quickstart/`
- Harness Open Source repository:
  `https://github.com/harness/harness`
- Adaptive Auto-Harness paper:
  `https://arxiv.org/abs/2606.01770`

Prior local research remains in:

- `docs/research/HARNESS_ENGINEERING_RESEARCH_BRIEF.md`
- `docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md`
- `docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`
- `docs/HARNESS_STYLE_AGENTOPS_OPERATING_SPEC.md`
- `docs/AGENT_TASK_HARNESS_ENGINEERING_SPEC.md`

## Research Takeaways

Harness Worker Agents show a useful product shape: agents are reusable,
governed execution steps with instructions, model connectors, optional MCP
connectors, typed inputs, environment variables, catalog placement, and
pipeline execution. For AgentOps MIS, the equivalent is not a browser page. It
is a work packet plus Agent Gateway/CLI/API/MCP execution.

Harness Policy As Code shows that governance must be an enforcement point, not
only a dashboard label. Harness uses OPA/Rego and policy sets; AgentOps MIS can
keep first-party policy logic in v1.x, but every decision still needs a policy
id, target, normalized action hash, enforcement point, decision, evidence refs,
and audit output.

Harness Open Source shows a self-hostable developer-platform shape with code
hosting, automated DevOps pipelines, hosted development environments, and
artifact registries. AgentOps MIS should borrow the platform discipline, not
replace its own ledger with a DevOps platform.

Adaptive Auto-Harness research highlights open-ended task streams, changing
task distributions, stateful multi-agent improvement, and human steering. This
supports AgentOps MIS async commander mode: multiple lanes should progress
independently, and the harness should route work to the right runtime without
turning one dense global memory or one mega-prompt into the authority.

## Product Position

AgentOps MIS is a local-first human-AI work harness and authority ledger. It
can use Harness-style worker, policy, catalog, scorecard, pipeline, and
developer-platform ideas, but the AgentOps MIS source of truth remains:

- workspace
- agent
- task
- Agent Plan
- run
- tool call
- runtime event
- prepared action
- approval
- evaluation
- artifact
- memory candidate
- report
- audit log

External systems may produce redacted summaries, IDs, source URIs, counters,
hashes, and evidence packets. They must not own or silently rewrite AgentOps MIS
authority objects.

## Hard Constraints

### 1. Agent Interface Constraint

Agents must use machine contracts:

- Agent Gateway API
- `agentops` CLI
- future MCP resources/tools
- operator work packets
- bounded action packets

Agents must not scrape Pixel Office, admin tables, or browser-only pages to
decide what to do.

### 2. Work Packet Constraint

Every real product task must have a compact packet with:

- `packet_id`
- `workspace_id`
- `task_id`
- `agent_id`
- `runtime_adapter`
- `objective_summary`
- `allowed_commands`
- `forbidden_actions`
- `required_approvals`
- `required_evidence`
- `verification_commands`
- `redaction_rules`
- `claim_limit`

The packet must be enough for Hermes, OpenClaw, Codex, or a remote worker to
operate without private chat history or full transcripts.

### 3. Policy Decision Constraint

Policy decisions must be represented as first-class evidence:

```json
{
  "policy_id": "agentops.example",
  "policy_version": "v1",
  "target_type": "run",
  "target_id": "run_example",
  "normalized_args_hash": "sha256:...",
  "enforcement_point": "agent_gateway.runs.start",
  "decision": "allow|deny|warn",
  "evidence_refs": ["plan:plan_example"],
  "audit_ref": "aud_example"
}
```

OPA/Rego may become a future adapter, but it must not replace Agent Plan,
Approval Wall, workspace scope enforcement, runtime trust, evaluation, memory
review, or audit authority.

### 4. Approval Wall Constraint

External writes, privileged actions, destructive actions, connector mutation,
credential handling, production deployment, remote server mutation, and
customer-visible delivery must use exact-action governance:

```text
prepare normalized action
-> hash action
-> checkpoint
-> approve
-> resume exact action
-> execute once
-> record summary/hash/provenance
-> audit
```

A generic approval row is not enough.

### 5. Real Runtime Constraint

Real product-readiness claims require:

- explicit confirmation or approved prepared action;
- runtime readiness/trust readback;
- completed run id;
- tool call or runtime event evidence;
- evaluation evidence;
- audit evidence;
- artifact or no-artifact rationale;
- no raw prompt, raw response, credential, token, private message, full
  transcript, local DB, or generated export committed.

Mock and fixture evidence is CI/offline fallback only and must be labeled.

### 6. Open-Source Base Constraint

Open-source bases and experimental branches may enter through:

- research packet
- isolated incubator
- adapter
- read model
- first-party reimplementation

They must not be merged as a second authority system for tasks, runs, approvals,
memory, artifacts, or audit.

### 7. Async Commander Constraint

The product must support the way it is being built:

- lane id
- owner/runtime
- current phase
- blocked reason
- next command
- evidence refs
- claim limit
- merge/readiness state

CI, live runtime calls, browser builds, and subagent work must not block an
independent safe lane.

## Product Slice Acceptance

A slice can be called product-grade only when it passes this scorecard:

| Check | Required result |
| --- | --- |
| Task packet | Work packet exists and is machine-readable. |
| Authority | MIS owns the authoritative objects. |
| Runtime | Real runtime evidence exists, or fallback is explicitly labeled. |
| Approval | High-risk action uses exact prepared-action approval. |
| Evidence | Run/tool/runtime/eval/audit/artifact/report readback is available or omission is explained. |
| Redaction | Raw prompt/response, secrets and full transcripts are omitted. |
| Async | Slow lanes do not block independent safe lanes. |
| UI | Human UI shows posture and next action, not bot-scraped authority. |
| Open-source | External base is research/incubator/adapter/read-model/reimplementation only. |
| Claim limit | Result states exactly what can and cannot be claimed. |

## Immediate Implementation Queue

1. Keep the governed local harness live runner as the manual real-runtime proof
   path for OpenClaw/Hermes.
2. Keep CI coverage read-only and deterministic through preview smokes.
3. Add exact readback for every recorded action receipt by source, action id,
   and action signature.
4. Surface live proof status in operator/UI surfaces without treating receipt
   presence as runtime success.
5. Continue turning open-source base experiments into adoption packets and
   incubators before any authority-system merge.

