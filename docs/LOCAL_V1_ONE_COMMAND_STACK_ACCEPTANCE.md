# Local v1 One-Command Stack Acceptance

## Scope

This slice turns `scripts/run_local_stack.py` into the product-facing local
entry point for the AgentOps MIS backend, Vite workspace, and bounded worker
processes.

The safe default starts:

- the loopback backend and Agent Gateway on `127.0.0.1:8787`;
- the workspace/admin UI on `127.0.0.1:19001`;
- one mock worker for offline/local fallback.

The real local mode starts Hermes and OpenClaw workers only with an explicit
live confirmation:

```bash
python3 scripts/run_local_stack.py \
  --worker hermes \
  --worker openclaw \
  --confirm-live-workers \
  --configure-cli
```

## Product Behavior

- The backend is considered ready only when the Agent Gateway status endpoint
  identifies an AgentOps MIS server; an unrelated process on the port fails the
  startup.
- UI proxy traffic targets the selected backend port.
- Worker processes receive the selected base URL and stable local-stack agent
  IDs without reading or printing raw tokens.
- Hermes/OpenClaw are rejected before process startup unless
  `--confirm-live-workers` is present.
- Ordinary startup does not mutate `~/.agentops/config.json`.
- `--configure-cli` is an explicit, separate opt-in for saving the local base
  URL and workspace.
- Ctrl-C terminates only the backend, UI, and workers started by this command.

## Verification

```bash
python3 -m py_compile scripts/run_local_stack.py scripts/run_local_stack_smoke.py
python3 scripts/run_local_stack_smoke.py
python3 scripts/clean_machine_rc_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

`run_local_stack_smoke.py` uses a temporary SQLite database, temporary CLI
config path, free loopback port, no UI dependency installation, and a mock
worker. It verifies backend readiness, worker registration, no user-config
write, and the live-worker confirmation wall. It does not call Hermes,
OpenClaw, Dify, Notion, or another external provider.

## Persistent Service Boundary

The one-command stack is foreground-managed and stops its child processes on
Ctrl-C. Reboot-persistent operation remains the existing reviewed
`agentops-worker service-install`, `service-check`, and preview-first
`service-control` launchd/systemd path. Local v1 release acceptance requires
both this foreground stack smoke and the existing OS-service smokes.

## Known Limits

- The stack does not install or mutate launchd/systemd service files.
- The safe default mock worker is CI/offline fallback, not real-runtime proof.
- Product-level completion still requires fresh Hermes and OpenClaw customer
  task evidence on the same release commit.
