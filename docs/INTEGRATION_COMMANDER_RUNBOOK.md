# AgentOps MIS Integration Commander Runbook

## Role

This thread is the integration commander for AgentOps MIS v1.5. It should not
own a feature branch unless integration requires a small fix. Its job is to keep
the product direction coherent while parallel Codex threads work on their own
branches.

The product direction is local-first:

- Make the open-source local version useful first.
- Keep hosted/SaaS, billing, and commercial deployment choices out of the
  critical path.
- Exclude Dify and Notion live sync from v1.5 completion, while keeping safe
  connector boundaries documented.

## Core Contract

Every branch must preserve this contract:

- Humans use the browser UI for dispatch, supervision, approval, and delivery
  review.
- Agents execute through Agent Gateway CLI/API/MCP.
- Hermes/OpenClaw live execution requires readiness, trust, and explicit
  `confirm_run`.
- Worker results must land in the MIS ledger: runs, tool calls, evaluations,
  audit logs, artifacts, memories, and approvals where relevant.
- Raw prompts, raw model responses, private transcripts, credentials, `.env`,
  local DBs, `dist`, `node_modules`, runtime logs, and generated service files
  must not be committed.

## Active Branches

Use `docs/PARALLEL_PRODUCT_DELIVERY_BRANCH_PLAN.md` as the source of truth for
branch ownership and handoff prompts.

Current branch lanes:

- `codex/local-first-ops`: local open-source usable product profile.
- `codex/rbac-workspace-hardening`: scoped token, session, and workspace safety.
- `codex/remote-worker-deploy`: remote worker deployment and service handoff.
- `codex/worker-fleet-console`: management UI and worker fleet observability.
- `codex/customer-task-flow`: customer task, async job, delivery report flow.
- `codex/product-docs-demo`: classroom/demo and product documentation.

## Merge Order

Default merge order:

1. `codex/local-first-ops`
2. `codex/rbac-workspace-hardening`
3. `codex/remote-worker-deploy`
4. `codex/worker-fleet-console`
5. `codex/customer-task-flow`
6. `codex/product-docs-demo`

Change the order only when a branch depends on another branch's API, schema, or
UI contract. Merge docs/demo last so they reflect the actual product.

## Branch Return Checklist

When a parallel thread reports back, ask it for:

- Branch name and latest commit SHA.
- Files changed.
- User-facing behavior changed.
- API/CLI contract changed, if any.
- Verification commands and outputs.
- Known limitations.
- Any secret/local artifact checks performed.
- Whether it touched files outside its lane, and why.

Do not merge a branch based only on a narrative summary.

## Review Steps

For each returned branch:

1. Fetch the branch.
2. Inspect diff scope against `PARALLEL_PRODUCT_DELIVERY_BRANCH_PLAN.md`.
3. Check for secret-like or local artifact additions.
4. Run the branch-specific smoke tests.
5. Run the shared checks that match the blast radius.
6. If it changes UI, run `cd ui/start-building-app && npm run build`.
7. If it changes core worker/runtime behavior, run adapter readiness and at
   least one safe worker smoke.
8. If it changes Hermes/OpenClaw live paths, confirm the default path remains
   dry-run/safe and live execution still requires explicit confirmation.
9. Merge only after evidence is stronger than the claim.

Useful checks:

```bash
git diff --check
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
python3 scripts/worker_adapter_readiness_smoke.py
python3 scripts/agentops_worker_status_smoke.py
python3 scripts/agentops_doctor_smoke.py
```

Secret/local artifact scan:

```bash
git diff --cached --name-only
git diff --cached | rg -n "agtok_|agtsess_|sk-|ntn_|Authorization: Bearer|agentops_mis.db|\\.env|node_modules|dist/"
```

## Integration Acceptance

The integrated v1.5 local-first product is not complete until current evidence
proves:

- A local user can open the UI and understand where to create work, supervise
  workers, review approvals, inspect runs, and read delivery reports.
- A normal MIS task can execute through a local worker adapter and write
  ledger evidence.
- Hermes/OpenClaw are available as real adapters, with safe default gates.
- Remote worker enrollment/session/heartbeat has a tested path, even if no
  hosted server is required.
- Scoped token/session/workspace checks protect the Agent Gateway MVP.
- Worker fleet status shows local daemon, remote heartbeat/session, stuck task,
  and async job health.
- Memory/knowledge review remains explicit: candidates can be reviewed, and
  raw private transcripts are not imported.
- Demo/product docs match the real behavior and do not oversell SaaS features.

## When To Use Live Dogfood

Live OpenClaw/Hermes dogfood is optional during normal branch work. Use it for
integration proof or demo readiness only when the local runtimes are intended to
execute.

```bash
python3 scripts/customer_worker_live_dogfood.py \
  --adapter openclaw \
  --adapter hermes \
  --request-timeout 720 \
  --hermes-timeout 600
```

Expected proof is not merely command success. The resulting run IDs must have
tool call, evaluation, runtime event, audit, artifact, memory, and approval
evidence in MIS.

## Commander Non-Goals

The integration commander should not:

- Redesign Pixel Office while another branch owns customer task flow.
- Rewrite Agent Gateway auth while the RBAC branch is active.
- Change remote worker install behavior while the remote deploy branch is
  active.
- Add hosted/SaaS/billing work to v1.5.
- Treat browser automation as agent execution.
- Mark the goal complete without requirement-by-requirement evidence.
