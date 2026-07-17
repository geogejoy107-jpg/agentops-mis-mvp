# Codex Workspace-Write Acceptance

## Product Boundary

Codex remains read-only by default. Workspace-write is a separate high-risk
workflow and never edits the caller's source worktree directly. AgentOps creates
a managed detached Git worktree from an approved clean HEAD and retains a
successful diff for human review. Commit, merge, push, deploy, and publication
are outside this authorization and require their own later approval.

Only the attested Codex binary bundled with the installed ChatGPT application
may receive product workspace-write authority. Deterministic fake binaries are
accepted only by the isolated test helper and always report
`product_readiness_proof=false`.

## Governance Sequence

The operator flow is deliberately multi-stage:

1. Create or reuse a task and a high-risk Agent Plan.
2. Human-approve the exact Agent Plan.
3. Re-run preparation to bind task, run, plan hash, verification hash, source
   repository hash, baseline HEAD, allowed paths, runtime attestation, expiry,
   and rollback policy into a PreparedAction hash.
4. Human-approve that exact PreparedAction.
5. Resume with both execution confirmations. MIS atomically inserts a unique
   execution lease before Codex starts; a second claimant receives `409`.
6. Codex runs with `workspace-write` only in the managed detached worktree.
   Network search, MCP, browser, apps, computer use, plugins, hooks, goals,
   image generation, and multi-agent features remain disabled.
7. AgentOps independently verifies unchanged HEAD, changed-path scope,
   symlink/submodule exclusion, size limits, `git diff --check`, secret markers,
   and hashed diff evidence.
8. Tool, evaluation, artifact, audit, memory-candidate, and verified plan
   evidence are recorded before the PreparedAction is consumed and the run is
   marked complete.

Any runtime, protocol, scope, secret, Git, evidence, or lease failure deletes
the managed worktree, marks the lease failed, blocks the task/run, and requires
a new Agent Plan/PreparedAction for another execution. The old approval cannot
be replayed.

## Operator Commands

Prepare a new task and Agent Plan:

```bash
agentops workflow codex-workspace-write \
  --title "Implement the approved change" \
  --description "Complete the task inside the bounded file scope." \
  --source-repo /absolute/path/to/clean/repository \
  --allow-path src/feature \
  --allow-path tests/test_feature.py \
  --confirm-run
```

Approve the returned Agent Plan approval, then repeat preparation with the
returned task id:

```bash
agentops approval approve --approval-id ap_plan_...

agentops workflow codex-workspace-write \
  --task-id tsk_... \
  --source-repo /absolute/path/to/clean/repository \
  --allow-path src/feature \
  --allow-path tests/test_feature.py \
  --confirm-run
```

Approve the returned PreparedAction, then execute it exactly once:

```bash
agentops approval approve --approval-id ap_prepared_action_...

agentops workflow codex-workspace-write \
  --prepared-action-id pa_... \
  --source-repo /absolute/path/to/clean/repository \
  --allow-path src/feature \
  --allow-path tests/test_feature.py \
  --confirm-run \
  --confirm-workspace-write \
  --allow-high-risk
```

The successful result returns changed paths, counts, diff/evidence hashes,
evaluation, artifact, memory-candidate, audit, lease, and plan-manifest receipts.
It does not return or store the raw patch, prompt, response, source content, or
credentials.

## Verification

CI-safe deterministic acceptance:

```bash
python3 scripts/codex_workspace_write_smoke.py \
  --base-url http://127.0.0.1:8787
```

The smoke verifies the read-only default, unattested-binary rejection, bounded
managed-worktree writes, dirty preflight, oversized/scope/protocol rollback,
omission of raw content, expiry-bound action hashes, exclusive execution lease,
verified-manifest completion of the lease/run, and second-claim rejection.
Fixture evidence is not product-readiness evidence.

Product acceptance additionally requires a real run using the installed
ChatGPT-bundled Codex and full MIS task/plan/approval/run/tool/evaluation/
artifact/memory/audit/manifest readback.
