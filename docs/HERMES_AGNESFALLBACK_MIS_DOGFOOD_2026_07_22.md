# Hermes / Agnesfallback MIS Dogfood Acceptance (2026-07-22)

## Result

PASS for a confirmed, one-shot real Hermes task through the installed local
AgentOps Host. This is real runtime evidence, not a mock, dry-run, or fixed
health probe.

The acceptance does not yet prove that a launchd-managed Hermes Worker loop is
installed and supervised. That remains a separate service receipt/readback
gate.

## Runtime Shape

- Installed AgentOps Host: `http://127.0.0.1:18878`
- Default Hermes gateway: `127.0.0.1:8642`, left running and unchanged
- Agnesfallback API-only profile: `127.0.0.1:8643`
- Agnesfallback model profile: `agnes-2.0-flash` via its existing local provider
- `/health`: HTTP 200
- `/v1/models`: HTTP 200
- Real execution confirmation: explicit `--confirm-run`
- Worker session: short-lived, scoped Agent Gateway session

The API-only profile explicitly disables its Discord adapter so it does not
compete with the default Hermes gateway for the same messaging credential. Its
Figma MCP entry is retained but disabled for this API-only runtime, avoiding an
unrelated `npx` startup wait. No credential value was read into acceptance
output or committed state.

## Command Shape

The successful run used the installed CLI with the local Host URL supplied
explicitly:

```bash
AGENTOPS_BASE_URL=http://127.0.0.1:18878 \
  agentops workflow run-task \
  --adapter hermes \
  --confirm-run \
  --use-session \
  --hermes-gateway-url http://127.0.0.1:8643 \
  --hermes-timeout 180 \
  --hermes-max-tokens 256 \
  --risk low \
  --title '<bounded acceptance task>' \
  --description '<bounded non-sensitive task summary>' \
  --acceptance '<ledger acceptance criteria>'
```

The local CLI configuration was then corrected from a stale development port
to `http://127.0.0.1:18878`; the existing API key was preserved without
printing it.

## Ledger Evidence

| Object | Evidence |
| --- | --- |
| Task | `tsk_1c514a0cc90c`, completed |
| Run | `run_gw_060b45283ca3`, completed |
| Agent | `agt_accept_cli_20260716191958832520_c7c1b033` |
| Agent Plan | `plan_2d0e7373664e2d61`, verified |
| Plan evidence | `pem_ba9570bc1ac6b6a0`, verified |
| Runtime event | `rte_e2b1a7a47542` |
| Audit | `aud_10dffc6050e6` |
| Memory candidate | `mem_gw_438a590d0024a8b6` |

The workflow readback reported one tool call, one evaluation, one artifact,
one audit row, and verified plan evidence. The adapter completed on its first
attempt. Only a redacted 200-character output summary and hashes entered the
ledger; raw prompt/response and credentials were omitted.

## Companion OpenClaw Evidence

The same installed Host previously completed a real OpenClaw task:

- task `tsk_68dafc084ada`
- run `run_gw_53b043f16632`
- agent `agt_worker_local_stack_openclaw`

Together, these two runs prove that Codex can act as commander while MIS
dispatches governed work to two independently configured local model runtimes.

## Remaining Product Gate

The Hermes one-shot task is product-usable, but the run's supervision readback
correctly remained `attention` for the service-managed loop. Product-level
unattended operation still requires:

1. install or package the Agnesfallback API-only gateway as a bounded local service;
2. install the Hermes Worker service against port 8643;
3. record an exact service-control receipt and verified readback;
4. run a second MIS task through that continuously supervised Worker;
5. upgrade the installed Host from Preview 38 to the current source release once the local storage floor is satisfied.

## Safety

- No token, `.env`, database, raw prompt, raw response, transcript, runtime log,
  model cache, or generated export is committed.
- Default Hermes and OpenClaw services were not removed.
- The Agnesfallback gateway binds only to `127.0.0.1`.
- Real execution required an explicit confirmation flag.
