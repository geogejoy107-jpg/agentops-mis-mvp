# Operator Loop Bootstrap Timeout Fallback Acceptance

## Scope

This slice fixes a post-merge main CI failure in the offline
`operator_loop_bootstrap_smoke.py` path. It does not change server runtime
behavior, execute Hermes/OpenClaw, mutate ledgers, or add a new product surface.

## Failure

GitHub Actions main run `28729691993` failed in `Offline safety smokes` after
PR #97 merged. The failing smoke was `operator_loop_bootstrap_smoke.py`.

The timeout fixture can produce a `GET /api/operator/start-check timed out`
error while still entering the stale-endpoint fallback. That stale fallback did
not include the fast bootstrap packet fields expected by the timeout test:

- `mode: fast`
- fast bootstrap steps
- fast service-closure command
- bounded loop confirm command
- `error_type: local_mis_endpoint_timeout`

## Fix

`agentops_mis_cli/agentops.py` now treats timeout text inside
`_operator_loop_bootstrap_stale_endpoint` as a timeout fallback and returns the
same fast bootstrap packet used by the direct timeout branch.

The fallback remains safe:

- read-only;
- no server shell;
- no service mutation;
- no ledger mutation;
- no live Hermes/OpenClaw execution;
- raw prompt/response/token omitted.

## Verification

```bash
python3 -m py_compile agentops_mis_cli/agentops.py scripts/operator_loop_bootstrap_smoke.py
python3 scripts/operator_loop_bootstrap_smoke.py
git diff --check
python3 scripts/secret_scan_smoke.py
```

Local result:

```text
operator_loop_bootstrap_smoke: ok
secret_scan_smoke: ok
```
