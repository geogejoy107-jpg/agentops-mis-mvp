# AgentOps MIS v1.5 Agent Gateway Hardening Objective

## Source

This objective incorporates the first static audit package from
`audit/v1-5-agent-gateway-hardening` and the current project-governance files.
It is the hardening overlay for `docs/V1_5_EIGHT_PRODUCT_CLOSURE_SPEC.md`.

The product target is unchanged: AgentOps MIS remains a local-first AI workforce
control plane where humans supervise and approve through the UI, while AI
workers execute through Agent Gateway CLI/API/MCP and write evidence back into
the MIS ledger.

## Current Goal

Before a v1.5 release candidate or main merge, the branch must prove that a
normal Agent Gateway run cannot bypass the authority chain:

```text
Project Spec / Approved Decision
-> Knowledge Retrieval
-> Agent Plan
-> Task
-> Run
-> Tool Call / Prepared Action
-> Approval
-> Artifact
-> Evaluation
-> Memory Candidate
-> Audit
```

The release goal is not more horizontal features. It is correctness,
permission separation, execution evidence, redaction, local reliability, and
CI-backed repeatability on the exact current HEAD.

## P0 Acceptance Gates

### 1. Agent Plan Is A Hard Execution Contract

Required behavior:

- Every real Agent Gateway run has an `agent_plan_id` and immutable
  `plan_hash`.
- `run_start` rejects missing, failed, superseded, mismatched, or changed plans.
- Existing runs cannot be rebound to a different plan, task, workspace, agent,
  or hash.
- Delivery evidence can trace from run back to the verified plan and its
  evidence manifest.

Primary evidence:

- `scripts/agent_plan_integrity_smoke.py`
- `scripts/run_start_plan_gate_smoke.py`
- `scripts/automatic_plan_evidence_workflow_smoke.py`
- `scripts/safe_closure_evidence_packet_smoke.py`

### 2. Agent Plan Approval Roles Are Separated

Required behavior:

- Agent-scoped write access can create only draft/submitted plans.
- Agents cannot submit a plan as already approved.
- Human/admin/policy paths are the only approval/rejection transitions.
- High-risk or `approval_required` plans create or require a real approval
  anchor before execution.
- Approval decisions are audited with actor, role, plan id, and plan hash.

Primary evidence:

- `scripts/agent_plan_integrity_smoke.py`
- `scripts/approval_semantics_boundary_smoke.py`

### 3. Plan References Have Provenance And Visibility

Required behavior:

- Referenced specs, files, memories, bases, and decisions resolve to canonical
  objects or readable repo paths.
- Candidate/rejected memory is not treated as authority.
- File paths remain inside the allowed repository/workspace boundary.
- Verification stores a result hash consumed by run start and delivery checks.

Primary evidence:

- `scripts/agent_plan_integrity_smoke.py`
- `scripts/knowledge_scope_policy_smoke.py`
- `scripts/agent_gateway_knowledge_scope_smoke.py`

### 4. Approval Wall Uses Exact Prepared Actions

Required behavior:

- Generic approval is not marketed as exact tool-action resume.
- High-risk external side effects create a prepared action with normalized args,
  action hash, checkpoint, policy version, approval id, and idempotency data.
- Approval authorizes exactly one prepared action; resume verifies the action
  hash and consumes the prepared action once.
- Rejection blocks the prepared action and linked run/tool state.

Primary evidence:

- `scripts/prepared_action_approval_wall_smoke.py`
- `scripts/high_risk_toolcall_prepared_action_gate_smoke.py`
- `scripts/customer_worker_external_write_gate_smoke.py`
- `scripts/runtime_probe_prepared_action_gate_smoke.py`
- `scripts/dify_upload_prepared_action_gate_smoke.py`
- `scripts/notion_export_prepared_action_gate_smoke.py`
- `scripts/worker_external_write_preflight_gate_smoke.py`
- `scripts/generic_external_side_effect_gate_smoke.py`
- `scripts/external_connector_runtime_inventory_smoke.py`

Required inventory gate:

```bash
python3 scripts/external_connector_runtime_inventory_smoke.py
```

### 5. Runtime Internal Behavior Is Visible Enough For The Claim

Required behavior:

- Hermes/OpenClaw remain protected/manual runtimes, not universally governed
  per internal tool action unless they emit runtime events.
- Runtime capability manifests state observation level, trust status, risk
  floor, and external-write policy.
- Available runtime-internal events can be recorded through scoped Gateway
  event APIs with summaries/hashes only.
- Public claims do not say universal runtime per-action governance is complete.

Primary evidence:

- `scripts/agent_gateway_runtime_event_smoke.py`
- `scripts/runtime_connector_trust_smoke.py`
- `scripts/protected_live_runtime_ids_smoke.py`
- `docs/PUBLIC_CLAIMS_AND_LIMITATIONS.md`

### 6. Redaction And Non-Local Auth Fail Closed

Required behavior:

- Server, CLI, worker, adapter logs, and smokes share one redaction contract.
- Token-like values, API keys, raw prompts, raw responses, full transcripts,
  and local DB files are not written into repo or release evidence.
- Shared/hosted/production-style deployment modes reject unsafe local-write
  APIs without configured admin credentials or scoped Agent Gateway tokens.

Primary evidence:

- `scripts/redaction_policy_smoke.py`
- `scripts/redaction_fuzz_smoke.py`
- `scripts/secret_scan_smoke.py`
- `scripts/shared_mode_local_write_guard_smoke.py`
- `scripts/agentops_doctor_smoke.py`

### 7. Workspace And Knowledge Visibility Are Exact

Required behavior:

- Scoped tokens cannot cross workspace boundaries by header/query/body spoofing.
- Review queue, approval list, memory list, task/run/artifact readback, and
  knowledge search use structured visibility checks rather than substring
  matching.
- Knowledge search returns provenance, authority class, visibility proof, and
  redacted snippets.

Primary evidence:

- `scripts/workspace_isolation_smoke.py`
- `scripts/agent_gateway_reviewable_lists_smoke.py`
- `scripts/agent_gateway_knowledge_scope_smoke.py`
- `scripts/knowledge_scope_policy_smoke.py`

### 8. SQLite Local Reliability Baseline Exists

Required behavior:

- The central DB factory enables foreign keys, WAL, busy timeout, and
  synchronous=NORMAL.
- Long external runtime calls do not run inside open write transactions.
- Concurrent local reads/writes have a deterministic smoke gate.

Primary evidence:

- `scripts/sqlite_pragmas_smoke.py`
- `scripts/sqlite_concurrency_smoke.py`

### 9. CI And Release Evidence Gate The Exact HEAD

Required behavior:

- CI runs credential-free deterministic backend smokes and UI build.
- Live Hermes/OpenClaw/Dify/Notion work remains manual/protected and out of CI.
- Release evidence names exact branch, exact commit, CI links/status, test
  commands, license/provenance, and public-claim boundaries.
- A branch is not READY_FOR_RC until CI is green on the exact candidate.

Primary evidence:

- `.github/workflows/ci.yml`
- `scripts/public_claims_release_gate_smoke.py`
- `scripts/release_branch_control_smoke.py`
- `scripts/license_provenance_smoke.py`
- `docs/V1_5_MERGE_READINESS_CHECKLIST.md`

## Open-Source Adoption Boundary

Open-source projects may accelerate toolchain, protocol, retrieval, CI, secret
scan, SBOM, Git isolation, and runtime adapter work. They must not become the
source of truth for workspace, task, run, approval, prepared action, memory,
evaluation, artifact, delivery, identity, or audit state.

Borrowed ideas must be wrapped behind first-party MIS modules and documented
with:

```text
Reference:
Borrowed idea:
First-party MIS module touched:
Authority boundary preserved:
Verification:
```

## Product Claim Boundary

Until every P0 gate above is passing on the exact HEAD, public language must
remain:

- local MVP;
- loopback/demo/controlled dogfood;
- protected/manual Hermes/OpenClaw evidence;
- not hosted SaaS;
- not enterprise RBAC;
- not universal runtime per-action governance;
- not commercial art/provenance complete unless a dedicated release gate says so.

## Next Action Rule

When CI or smoke evidence fails, fix the first deterministic failing gate before
adding another product feature. Subagents may work in parallel, but the commander
must merge evidence gate by gate and keep `docs/V1_5_MERGE_READINESS_CHECKLIST.md`
honest.
