# Private Host Console Disconnect Acceptance

## Scope

This slice proves that the private Host and a mock Agent Worker do not depend
on a live human browser connection. It does not call Hermes, OpenClaw, Dify,
Notion, or any other external runtime or service.

## Scenario

`scripts/private_host_console_disconnect_smoke.py` uses a temporary SQLite
database, a free loopback port, ephemeral in-memory fixture credentials, and a
private-host server process. The smoke:

1. bootstraps an Owner browser session;
2. creates a mock Worker identity and a planned task through authenticated
   human APIs with CSRF protection;
3. logs out, clears, and discards the first browser client;
4. confirms an unauthenticated client cannot read the task;
5. starts an independent mock Worker process after the browser is gone;
6. forces one retryable mock attempt before success to produce controlled
   background progress;
7. verifies that the original Host PID remains alive and unchanged;
8. signs in through a fresh browser client and reads the completed task, run,
   tool-call, evaluation, and runtime-event evidence.

The smoke does not claim OS service persistence, process survival after a Host
restart, or real-runtime completion. Those remain separate acceptance gates.

## Verification

```bash
python3 -m py_compile scripts/private_host_console_disconnect_smoke.py
python3 scripts/private_host_console_disconnect_smoke.py
git diff --check -- scripts/private_host_console_disconnect_smoke.py \
  docs/PRIVATE_HOST_CONSOLE_DISCONNECT_ACCEPTANCE.md
```

Expected result:

- `ok: true`;
- `isolated_private_host: true`;
- `temporary_database: true`;
- `real_runtime_called: false`;
- `browser_connection_required_for_worker: false`;
- the first Session is revoked and anonymous readback returns `401`;
- the Host PID remains stable while the Worker runs;
- the mock Worker reports two attempts and a completed run;
- a fresh Session reads the completed task/run evidence;
- no fixture credential value appears in Host or Worker output.

## Observed Result

Verified on 2026-07-12 against branch `codex/local-host-remote-console`:

- smoke exit code: `0`;
- `ok: true` with no failures;
- disconnected anonymous read: `401`;
- Host PID stable: `true`;
- mock Worker attempts: `2`;
- task and run status: `completed`;
- evidence: 1 tool call, 1 passing evaluation, and 8 runtime events;
- fresh reconnect Session: `true`;
- real Runtime calls: `false`.

All state was created below a temporary directory and removed when the smoke
finished. The temporary task/run identifiers are intentionally not retained as
release evidence.

## Product Meaning

The browser is an authenticated operator surface, not the execution owner.
Tasks are durable in the MIS ledger, and Workers use the separate Agent
Gateway machine path. Closing or revoking a browser Session therefore removes
human access without canceling Host-side work. Reconnection creates a new
human Session and resumes observation of the same ledger state.

## Limitations

- The Worker uses the deterministic mock adapter as an offline/CI fallback.
- The Worker is a bounded subprocess started by the smoke, not a launchd or
  systemd daemon.
- Browser network loss is represented by explicit logout plus disposal of the
  cookie jar; abrupt TCP loss is not separately instrumented.
- Real Hermes/OpenClaw disconnect evidence remains part of the later private
  Host real-runtime acceptance.
