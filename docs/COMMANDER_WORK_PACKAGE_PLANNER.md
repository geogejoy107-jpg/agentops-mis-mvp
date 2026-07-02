# Commander Work Package Planner

## Purpose

The Commander Work Package Planner turns one customer or operator goal into a bounded set of MIS work-package tasks for an AI team.

It is the product version of the current development workflow: a commander decomposes work, assigns lanes, keeps scope boundaries visible, and lets workers execute through Agent Gateway CLI/API instead of browser clicks.

## Safety Model

- Preview is the default and does not mutate the ledger.
- Real task creation requires `confirm_create:true` or `--confirm-create`.
- The planner does not execute Hermes, OpenClaw, Dify, Notion, shell, or browser actions.
- Work-package dispatch is explicit and targeted by `task_id`; it runs through the Agent Gateway worker loop, not an ad hoc backend shortcut.
- Mock dispatch is safe for local demos. Hermes/OpenClaw dispatch requires explicit `confirm_run:true` / `--confirm-run`.
- Failed benchmark remediation can enter the same loop: `agentops eval remediate-case-run --case-run-id ... --confirm-create` creates a normal task whose description follows the Commander work-package contract.
- Stored text is redacted and bounded; raw prompts, credentials, tokens, raw model responses, and private transcripts are not stored.
- Confirmed planning writes normal MIS task rows plus runtime/audit evidence and
  a `commander_repo_map_localization` artifact for each package. The artifact
  stores candidate paths, hashes, provenance and omission proof only; it does
  not store raw source files or snippets.

## API

Read the local coding project template before turning a coding goal into
work packages:

```bash
curl -s "http://127.0.0.1:8787/api/commander/coding-project-template?q=P1-02+local+coding+project+template" | jq .
```

The template is read-only. It links the Commander WorkPackage contract,
`commander_repo_map_localization`, branch/worktree naming, patch capture,
verifier commands, required artifacts, plan-evidence manifest and the strict
merge-readiness gate. It does not create a worktree, write a patch or mutate
the ledger.

Create local coding project work packages through the workflow template:

```bash
agentops workflow run-template --template-id tpl_local_coding_project
```

This creates Commander work packages and task-bound repo-map localization
artifacts, but still only plans the branch/worktree, patch, verifier and merge
gate. It does not run Hermes/OpenClaw live, merge, push, or store raw source.

Preview:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/plan \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Use AgentOps MIS to coordinate a customer AI-team project.",
    "max_packages": 5
  }' | jq .
```

Create planned work-package tasks:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/plan \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Use AgentOps MIS to coordinate a customer AI-team project.",
    "max_packages": 5,
    "confirm_create": true
  }' | jq .
```

Read persisted work packages:

```bash
curl -s "http://127.0.0.1:8787/api/commander/work-packages?project_id=proj_x&limit=25" | jq .
```

The readback endpoint is read-only. It reconstructs work-package state from
normal MIS `tasks`, links the latest run, counts evidence rows, and returns a
recommended next action for each lane. For confirmed Commander packages it also
returns the latest repo-map localization artifact so a worker can see the
intended file scope before dispatch.

Failed evaluation-case runs can be converted into one-package Commander
remediation plans:

```bash
curl -s -X POST http://127.0.0.1:8787/api/evaluation-case-runs/ecr_123/remediation-task \
  -H "Content-Type: application/json" \
  -d '{"confirm_create":true}' | jq .

curl -s "http://127.0.0.1:8787/api/commander/work-packages?project_id=proj_evalcase_remediation_x&limit=5" | jq .
```

This conversion creates a planned work package only after confirmation. It
does not rerun the benchmark, approve the failure, or execute Hermes/OpenClaw.

Dispatch one persisted package through the mock worker:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/tsk_cmd_example_strategy/dispatch \
  -H "Content-Type: application/json" \
  -d '{"adapter":"mock"}' | jq .
```

Confirmed live dispatch uses the same endpoint but must be explicit:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/tsk_cmd_example_strategy/dispatch \
  -H "Content-Type: application/json" \
  -d '{"adapter":"openclaw","confirm_run":true}' | jq .
```

If `adapter` is `hermes` or `openclaw` and confirmation is omitted, MIS writes a
confirm-required runtime/audit event and does not create a run.

Preview a coding worktree for a package:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/tsk_cmd_example_strategy/coding-workspace \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
```

The preview returns branch naming, a worktree path hash, current git status,
and safety proof. It does not create a worktree or mutate the ledger unless
`confirm_create:true` is supplied.

Record patch/test/verifier/merge-gate evidence after a package has a run:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/tsk_cmd_example_strategy/coding-evidence \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run_gw_example",
    "confirm_record": true,
    "changed_files": ["server.py"],
    "verification_commands": ["git diff --check"]
  }' | jq .
```

This records `commander_worktree_workspace`, `commander_patch_manifest`,
`commander_test_log`, `commander_verifier_report`, and
`commander_merge_gate_receipt` artifacts plus evaluation/runtime/audit
evidence. It stores summaries, hashes, repo-relative paths and omission proof
only; raw source, raw patches and raw test logs are not stored. If an explicit
worktree was created, `collect_from_worktree:true` can collect sanitized git
status/diff metadata from that worktree without merging or pushing.

Queue several planned packages as async workflow jobs:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/dispatch-batch \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_x",
    "status": "planned",
    "limit": 5,
    "adapter": "mock"
  }' | jq .
```

The batch endpoint creates `workflow_jobs` rows and returns immediately. Each job
then executes the exact target work-package `task_id` through the same Agent
Gateway worker loop. Hermes/OpenClaw batch dispatch is rejected unless
`confirm_run:true` is present.

Synthesize returned packages into a review report:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/synthesize \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_x",
    "status": "ready_for_review",
    "limit": 10
  }' | jq .
```

Preview is read-only. To persist a bounded report artifact for human review,
pass `confirm_create:true`. The report stores a redacted summary, artifact URI,
content hash evidence, runtime event, audit log, and a pending
`commander_synthesis` approval visible in the human review queue. It does not
execute live adapters and does not store raw prompts, private transcripts,
credentials, or tokens.

Promote an approved synthesis into downstream review/delivery evidence:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/synthesis/promote \
  -H "Content-Type: application/json" \
  -d '{
    "artifact_id": "art_cmd_synthesis_x",
    "approval_id": "ap_cmd_synthesis_x",
    "mode": "both",
    "confirm_promote": true
  }' | jq .
```

Promotion fails closed until the `commander_synthesis` approval is approved.
Without `confirm_promote:true`, the endpoint is preview-only. Confirmed
promotion creates a memory candidate and/or customer delivery artifact with
runtime/audit evidence; it still does not execute live adapters or store raw
package transcripts.

## CLI

Preview:

```bash
./scripts/agentops commander plan \
  --goal "Use AgentOps MIS to coordinate a customer AI-team project." \
  --max-packages 5
```

Create tasks:

```bash
./scripts/agentops commander plan \
  --goal "Use AgentOps MIS to coordinate a customer AI-team project." \
  --max-packages 5 \
  --confirm-create
```

Read persisted packages:

```bash
./scripts/agentops commander packages --project-id proj_x --limit 25
```

Preview an isolated coding worktree:

```bash
./scripts/agentops commander coding-workspace --task-id tsk_cmd_example_strategy
```

Create it only when the operator explicitly confirms:

```bash
./scripts/agentops commander coding-workspace \
  --task-id tsk_cmd_example_strategy \
  --confirm-create
```

After a worker dispatch has produced a run, record coding evidence:

```bash
./scripts/agentops commander coding-evidence \
  --task-id tsk_cmd_example_strategy \
  --run-id run_gw_example \
  --changed-file server.py \
  --verification-command "git diff --check" \
  --confirm-record
```

Cleanup is also preview-first:

```bash
./scripts/agentops commander coding-workspace-cleanup --task-id tsk_cmd_example_strategy
```

Create a Commander-compatible remediation package from a failed benchmark:

```bash
./scripts/agentops eval remediate-case-run --case-run-id ecr_123
./scripts/agentops eval remediate-case-run --case-run-id ecr_123 --confirm-create
./scripts/agentops commander packages --project-id proj_evalcase_remediation_x --limit 5
./scripts/agentops operator action-plan --limit 20
```

The operator action plan exposes this as a `remediation_loop` lane with counts
for packages, ready-for-review packages, pending synthesis reviews, and
promoted deliveries. `/workspace/agents` renders those actions in the Operator
Action Queue without executing workers or approving gates.

After a remediation package is dispatched and synthesized, the same approval
and promotion commands close the loop:

```bash
./scripts/agentops commander dispatch-package --task-id tsk_evalcase_fix_ecr_123 --adapter mock
./scripts/agentops commander synthesize --project-id proj_evalcase_remediation_x --status ready_for_review --confirm-create
./scripts/agentops approval inspect --approval-id ap_cmd_synthesis_x
./scripts/agentops approval approve --approval-id ap_cmd_synthesis_x
./scripts/agentops commander promote-synthesis \
  --artifact-id art_cmd_synthesis_x \
  --approval-id ap_cmd_synthesis_x \
  --mode both \
  --confirm-promote
./scripts/agentops operator close-evidence-gap \
  --run-id run_123 \
  --decision accepted_remediation \
  --confirm-close
./scripts/agentops operator action-plan --limit 20
./scripts/agentops workflow delivery-board --limit 12
```

Once promoted, `operator action-plan` reports the remediation source as
`promoted`, increments `remediation_promoted_memories` and
`remediation_promoted_deliveries`, and stops asking for duplicate synthesis of
that already promoted remediation project.

The same operator plan also exposes an `execution_evidence` audit source. It is
read-only and points the commander at completed/failed runs that still lack a
plan binding, verified plan-evidence manifest, or tool/evaluation/artifact/audit
evidence, so remediation packages do not become customer-facing output before
the loop ledger is complete. The next command is
`agentops operator remediate-evidence-gap --run-id <run_id>`; it previews a
Commander work package by default, and `--confirm-create` writes a deterministic
planned task that can then be dispatched through the normal Commander package
path. After dispatch writes a full evidence chain including
`plan_evidence_manifests`, the operator source marks that gap
`remediation_status=verified` so the command center can review the legacy debt
without keeping it in the blocked lane. The next operator action is then the
normal synthesis/review/promotion chain. Once promotion succeeds, the source run
still requires `agentops operator close-evidence-gap --decision
accepted_remediation --confirm-close` (or an explicit `waived`/`reopen`
decision) so approved remediation becomes memory/customer-delivery evidence
without silently erasing the historical gap.

Dispatch a package:

```bash
./scripts/agentops commander dispatch-package \
  --task-id tsk_cmd_example_strategy \
  --adapter mock
```

Confirmed live dispatch:

```bash
./scripts/agentops commander dispatch-package \
  --task-id tsk_cmd_example_strategy \
  --adapter openclaw \
  --confirm-run
```

Queue planned packages in parallel:

```bash
./scripts/agentops commander dispatch-batch \
  --project-id proj_x \
  --status planned \
  --limit 5 \
  --adapter mock
```

Then poll returned jobs:

```bash
./scripts/agentops workflow job-status --job-id wfjob_x --wait
./scripts/agentops commander packages --project-id proj_x --limit 25
```

Synthesize ready packages into a review artifact:

```bash
./scripts/agentops commander synthesize \
  --project-id proj_x \
  --status ready_for_review \
  --limit 10 \
  --confirm-create
```

Then review the generated gate:

```bash
./scripts/agentops review queue --limit 10
./scripts/agentops approval inspect --approval-id ap_cmd_synthesis_x
./scripts/agentops approval approve --approval-id ap_cmd_synthesis_x
```

Approving or rejecting a Commander synthesis approval records the report review
decision without changing the already completed worker run/task status. The
operator can then promote approved findings into memory candidates or customer
delivery artifacts through the normal review/delivery flows.

Promote approved synthesis evidence:

```bash
./scripts/agentops commander promote-synthesis \
  --artifact-id art_cmd_synthesis_x \
  --approval-id ap_cmd_synthesis_x \
  --mode both \
  --confirm-promote
```

Omit `--confirm-promote` for a dry preview.

Promotion is explicit and fails closed until the linked `commander_synthesis`
approval is approved. `--mode memory` creates a `candidate` memory only;
`--mode delivery` creates a `customer_delivery_report` artifact visible in the
delivery board; `--mode both` does both. Promotion never executes live adapters
and stores only bounded summaries, URI references, hashes, runtime events, and
audit logs.

Mission control visibility:

```bash
./scripts/agentops commander board
./scripts/agentops local readiness
```

Both read-only surfaces expose the Commander synthesis lifecycle: synthesis
artifact count, pending/approved reviews, promoted memory candidates, promoted
delivery artifacts, recent synthesis rows, and the next CLI action. This lets
operators see whether the loop is still waiting on review, ready to promote, or
already visible in customer delivery.

`agentops review queue` also treats the lifecycle as a first-class review lane:
pending synthesis approvals and approved-but-not-promoted synthesis reports are
prioritized ahead of ordinary memory review. The `/workspace/agents` operator
action queue reads the same lifecycle next actions from local readiness, so the
Commander can continue the loop without hunting through separate pages.

## Default Lanes

- Strategy: clarify goal, acceptance gates, approvals, and scope.
- Research: gather grounded repo/product evidence without ingesting private transcripts.
- Implementation: make the smallest useful bounded product increment.
- QA: verify ledger evidence, smoke tests, and safety gates.
- Ops: prepare customer-facing handoff and runbook notes.

Each generated task includes:

- owner agent
- collaborators
- scope
- avoid scope
- dependencies
- verification commands
- return checklist
- acceptance criteria

## UI

Open `/workspace/agents` and use **Commander Work Package Planner**.

The panel supports:

- reading the local coding project template through `agentops commander coding-template`
- previewing the work-package split
- confirming task creation
- opening created task detail pages
- reading persisted work-package status after refresh
- seeing each package's repo-map localization artifact and evidence count
- dispatching a persisted package through mock, Hermes, or OpenClaw worker adapters
- reading machine-facing lane packets through `agentops commander lane-packets`
- previewing/creating an isolated coding worktree through CLI/API
- recording worktree/patch/test/verifier/merge-gate evidence through CLI/API
- cleaning isolated worktree/branch residue through CLI/API after evidence capture
- queueing currently planned packages as mock async workflow jobs
- synthesizing ready package outputs into a ledger-backed review artifact through CLI/API
- seeing safety proof for no live execution and token omission

## Verification

```bash
python3 scripts/commander_coding_project_template_smoke.py
python3 scripts/commander_coding_workspace_smoke.py
python3 scripts/commander_lane_packet_smoke.py
python3 scripts/commander_work_package_plan_smoke.py
python3 scripts/commander_work_package_dispatch_smoke.py
AGENTOPS_BASE_URL=http://127.0.0.1:8787 python3 scripts/local_coding_project_template_smoke.py
python3 scripts/commander_work_package_batch_dispatch_smoke.py
python3 scripts/commander_work_package_synthesis_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
cd ui/start-building-app && npm run build
```
