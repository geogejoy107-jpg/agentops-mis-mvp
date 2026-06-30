# Commercial Config Operator Action UI Acceptance

## Scope

This slice completes the follow-up from
`docs/COMMERCIAL_CONFIG_STATUS_UI_ACCEPTANCE.md`: the Admin Connectors
commercial config panel now gives operators a safe next action.

It adds:

- `commercial-config-operator-action` in `RuntimeConnectors.tsx`
- `scripts/commercial_config_operator_action_ui_smoke.py`
- CI and release-evidence wiring for that read-only UI contract

## Product Behavior

The operator action strip shows:

- exact CLI verification command: `agentops commercial config-status`
- evidence doc path: `docs/COMMERCIAL_CONFIG_STATUS_UI_ACCEPTANCE.md`
- production boundary reminder that the panel performs no billing, cleanup,
  hosted-readiness or live-runtime action

This makes the commercial config status panel actionable for local operators
without turning it into a billing or destructive-operation surface.

## Safety Boundary

This UI is read-only. It does not mutate SQLite, call billing providers, execute
cleanup, run live runtimes, create hosted-readiness claims, display secrets, or
add a second commercial authority system.

## Verification

Commands:

```bash
python3 scripts/commercial_config_operator_action_ui_smoke.py
python3 scripts/commercial_config_status_ui_smoke.py
python3 scripts/commercial_config_status_smoke.py
python3 -m py_compile scripts/commercial_config_operator_action_ui_smoke.py scripts/commercial_config_status_ui_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
cd ui/start-building-app && npm run build
```

Expected result:

- `/admin/connectors` source contains `data-testid="commercial-config-operator-action"`
- the strip renders `agentops commercial config-status`
- the strip points to `docs/COMMERCIAL_CONFIG_STATUS_UI_ACCEPTANCE.md`
- the strip states that billing, cleanup, hosted-readiness and live-runtime
  actions are not performed
- no token-like material or runtime confirmation marker is introduced

## Next Slice

The next commercial slice should avoid growing this local UI into hosted
billing. A safe next step is a read-only commercial evidence packet summary page
or a clean-room breakdown plan for PR #22, because that branch is too large to
merge as a single product slice.
