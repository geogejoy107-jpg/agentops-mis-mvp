# Codex Read-Only Worker Acceptance

## Scope

This slice makes Codex an actual AgentOps worker for bounded analysis and
review tasks. It is separate from the existing `repo_local_supervisor` handoff
consumer: the supervisor reads loop packets, while the worker claims a task,
invokes Codex, and writes governed evidence back to MIS.

The first product boundary is deliberately read-only. It does not let Codex
edit the repository, run commands, call MCP tools, browse the web, commit,
push, deploy, approve its own work, or perform external writes.

## Execution Contract

`agentops-worker --adapter codex` invokes the official non-interactive Codex
CLI with:

- `codex exec --json --ephemeral`
- `--ignore-user-config`
- `--sandbox read-only`
- strict config with shell, unified exec, apps, browser, computer use, plugins,
  multi-agent, hooks, goals, image generation, and web search disabled
- task input over stdin, never argv
- a child environment that omits AgentOps enrollment/session credentials

The wrapper retains only the final redacted summary, usage counts, event-type
counts, and hashes. Raw prompts, responses, JSONL events, credentials, and
transcripts are not written to MIS.

If Codex emits a command, file-change, MCP, web-search, browser, or computer-use
event, the adapter marks the run failed with `CodexProhibitedToolEvent`. A
non-empty model answer alone is not allowed to override that failure.

## Remote-Shaped Flow

The acceptance path uses the normal remote worker boundary:

1. Create a scoped enrollment token for a Codex worker.
2. Pass the token to `agentops-worker` through its process environment, not
   argv.
3. Mint a 15-minute Agent Gateway session before task processing.
4. Claim the assigned task.
5. Retrieve project knowledge and create or reuse a verified Agent Plan.
6. Start a `runtime_type=codex` run under the existing run-start supervision
   gate.
7. Execute Codex in the bounded read-only contract.
8. Record runtime summary, tool call, evaluation, artifact, memory candidate,
   audit entries, and a verified plan-evidence manifest.
9. Revoke the parent enrollment token after the acceptance run.

## Operator Commands

Read-only preflight:

```bash
agentops worker preflight --adapter codex
```

One governed local task:

```bash
agentops workflow run-task \
  --adapter codex \
  --confirm-run \
  --use-session \
  --title "Review a customer delivery packet" \
  --description "Return a read-only risk and evidence assessment." \
  --risk low
```

Remote-shaped real runtime acceptance:

```bash
python3 scripts/remote_agent_token_worker_smoke.py \
  --base-url http://127.0.0.1:8787 \
  --adapter codex \
  --confirm-run \
  --evidence-class real_runtime
```

## Verification

CI-safe deterministic fixture:

```bash
python3 scripts/codex_worker_adapter_smoke.py
```

The fixture must prove short-lived session use, completed task/run state,
tool/evaluation/runtime/artifact/memory/audit evidence, verified Agent Plan and
plan-evidence manifest, prohibited-event fail-closed behavior, and no token
leak. It must report `product_readiness_proof=false` because a fake Codex
binary is not live product evidence.

Product-readiness claims require a separate run with the installed Codex CLI,
`evidence_class=real_runtime`, a completed run id, and the same ledger checks.

## Known Limits

- This slice supports real customer analysis/review work, not autonomous code
  edits. A later workspace-write slice needs a dedicated clean worktree,
  independent test verification, diff hashes, crash-safe idempotent evidence
  closure, and explicit merge/publish approval.
- The browser Worker Console does not start Codex. Codex remains an external
  CLI/remote-shaped worker so the MIS server does not spawn a coding agent.
- Codex may be installed as an externally managed launchd/systemd worker, but
  the MIS local supervisor intentionally omits it from `worker start`,
  `worker stop`, `worker restart`, and `worker logs`.
- The current generic worker evaluation checks successful bounded execution
  plus knowledge retrieval. Domain-specific quality scoring remains a separate
  evaluator responsibility.
