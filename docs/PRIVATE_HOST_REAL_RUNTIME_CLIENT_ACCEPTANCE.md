# Private Host Real Runtime Client Acceptance

Status: deterministic human-auth and cold-start gates passed; fresh live Runtime rerun pending

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
