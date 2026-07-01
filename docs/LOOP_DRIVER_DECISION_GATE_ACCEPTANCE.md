# Loop Driver Decision Gate Acceptance

Date: 2026-07-01

Branch: `codex/osbi-loop-driver-decision-mainline`

## Slice

This slice makes `agentops operator loop-driver` consume the compact
`agent_work_packet_decision_v1` projection before confirmed bounded advance and
before every bounded step.

## Boundary

- Uses `GET /api/operator/loop-supervision?decision=1` as a read-only gate.
- Fails closed for `stop`, `blocked`, missing decisions, server-shell evidence,
  live-execution evidence, or `policy.server_may_execute=true`.
- Allows governance-first decisions only through the existing local
  `advance-loop` allowlist path.
- Does not add server endpoints.
- Does not call Hermes/OpenClaw live adapters.
- Does not store raw prompts, raw responses, tokens, or generated artifacts.

## Verification

```bash
python3 scripts/operator_loop_driver_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
git diff --check
```

Results:

- `operator_loop_driver_smoke`: pass, no failures, `secret_leaked=false`
- `py_compile`: pass
- `git diff --check`: pass

## Next Slice

After this lands, run a local dogfood pass where Hermes/OpenClaw read the
decision-gated loop-driver packet from the current local MIS server and copy the
next bounded command sequence without bypassing Approval Wall or live-run
confirmation gates.
