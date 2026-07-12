# Private Host Real Runtime Client Acceptance

Status: deterministic auth gates and fresh local Private Host live Runtime acceptance passed

## Purpose

`scripts/customer_worker_real_runtime_acceptance.py` can now exercise the
customer task endpoint through the same human Session and CSRF boundary used by
the browser console. This removes the prior need to bypass Private Host auth for
manual Hermes/OpenClaw acceptance.

## Credential Boundary

The client reads credentials only from operator-selected environment variables:

```text
AGENTOPS_ACCEPTANCE_PASSWORD
AGENTOPS_OWNER_SETUP_CODE
```

The password and one-time setup code are not accepted as CLI arguments and are
not emitted in result JSON. The human browser Session remains separate from the
Agent Gateway machine credential used internally by the Worker.

## Deterministic Verification

```bash
python3 -m py_compile \
  scripts/customer_worker_real_runtime_acceptance.py \
  scripts/private_host_acceptance_client_smoke.py
python3 scripts/private_host_acceptance_client_smoke.py
git diff --check
```

The isolated smoke proves Owner bootstrap, Session cookie persistence,
authenticated task read, CSRF-protected task creation, and machine-token
separation. It does not call a Runtime and is labeled accordingly.

## Explicit Live Command

After an operator initializes and starts an isolated Private Host, export the
one-time setup code and a temporary acceptance password in the current shell,
then run:

```bash
python3 scripts/customer_worker_real_runtime_acceptance.py \
  --base-url http://127.0.0.1:<host-port> \
  --human-auth \
  --confirm-live \
  --adapter hermes \
  --adapter openclaw \
  --request-timeout 900 \
  --hermes-timeout 600 \
  --hermes-max-tokens 512
```

The live claim is accepted only when both adapters produce fresh task, plan,
run, tool, runtime event, evaluation, approval, artifact, memory, audit, and
verified plan-evidence IDs in the isolated Host ledger. Raw prompts, raw
responses, credential values, private messages, and full transcripts remain
excluded from output and committed state.

The authenticated readback uses the same temporary Owner password environment
variable and a separate browser Session:

```bash
python3 scripts/v1_5_live_product_readiness_smoke.py \
  --base-url http://127.0.0.1:<host-port> \
  --human-auth \
  --require-adapter hermes \
  --require-adapter openclaw
```

It does not accept a machine token as a browser credential and refuses to
bootstrap an Owner because this verification step is read-only.

## Fresh Live Result

On commit `b03235652165b804a8dffb83b3cda94a2680f6f9`, a new isolated Private
Host accepted an Owner Session and completed one explicitly confirmed task per
adapter:

| Adapter | Task | Run | Evidence |
|---|---|---|---|
| Hermes | `tsk_customer_worker_task_hermes_hermes_worker_20260712183626_20260712103626589050` | `run_gw_4eadf2ba75bf` | 1 tool call, 1 evaluation, 15 runtime events, 12 audit events, 2 artifacts, 2 memory proposals, 1 approval, 1 verified plan-evidence manifest |
| OpenClaw | `tsk_customer_worker_task_openclaw_openclaw_worker_20260712183736_20260712103736141541` | `run_gw_f7a007436e36` | 1 tool call, 1 evaluation, 15 runtime events, 12 audit events, 2 artifacts, 2 memory proposals, 1 approval, 1 verified plan-evidence manifest |

Both runs finished with `status=completed`; the acceptance client returned
`ok=true`, `human_session_used=true`, and no failures. The first standalone
readback attempt returned `401` because the read-only client did not yet support
Private Host login. That client gap is now covered by
`private_host_acceptance_client_smoke.py` without making Runtime calls.

This proves host-local authenticated dispatch and ledger closure. It does not
yet prove access from a second physical computer, private-network HTTPS, or
browser disconnect/reconnect behavior.

## Exact-Package Preview 3 Result

On exact commit `642471f571d9943f9c4c217b3912e32f6728dfce`, the installed
`v1.6.0-private-host-preview.3` package ran with an isolated AgentOps install,
Host data directory and SQLite ledger while preserving the authorized local
Runtime environment. Both adapters completed a new explicitly confirmed
customer task:

| Adapter | Run | Approval | Authority receipt | Bounded evidence |
|---|---|---|---|---|
| Hermes | `run_gw_0c16ac907390` | `ap_customer_worker_delivery_run_gw_0c16ac907390` | `phr_429aeebd31ea54e9ed7817f2` | 1 tool call, 1 evaluation, 15 runtime events, 12 audit events, 2 artifacts, 2 memory proposals and 1 verified plan-evidence manifest |
| OpenClaw | `run_gw_c0dabe5b3e3b` | `ap_customer_worker_delivery_run_gw_c0dabe5b3e3b` | `phr_ced9731c645f5becbec2f158` | 1 tool call, 1 evaluation, 15 runtime events, 12 audit events, 2 artifacts, 2 memory proposals and 1 verified plan-evidence manifest |

The live client returned `ok=true` with no failures. Each delivery initially
remained pending and receipt generation failed closed until a human Owner
approved it. A second Owner Session then read and downloaded each receipt; the
downloaded canonical payload hashes matched the stored authority hashes. No
credential, Cookie, raw prompt, raw response, private message, transcript or
database file was captured in this acceptance record.

This closes the host-local exact-package Runtime and authority-receipt gate. It
does not close the physical second-device HTTPS or disconnect/reconnect gates.
