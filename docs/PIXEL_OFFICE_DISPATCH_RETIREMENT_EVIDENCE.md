# Pixel Office / Dispatch Retirement Evidence

Contract: `pixel_office_dispatch_retirement_evidence_v1`

Gate: `gate_4_ui_api_parity_before_nextjs`

Machine-readable contract:
`docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json`

## Decision

This packet records explicit visual and behavior evidence for the
`pixel_office_and_dispatch` Gate 4 route pair. It does not retire the Vite
`/workspace/pixel-office` route by itself.

The current state is:

- Vite `/workspace/pixel-office` remains the compatibility route until an
  explicit route retirement commit.
- Next `/workspace/pixel-office` renders the commercial-safe Pixel Operating
  Map and owner dispatch workflow bridge.
- Next `/workspace/dispatch` renders the owner task composer, customer task
  templates, customer-task form fallback, template async job fallback,
  customer-worker dispatch, async customer-worker jobs, and prepared-action
  resume queue.
- `retirement_allowed` remains `false` until a route-pair-specific retirement
  commit preserves deep links, updates the matrix, and reruns Vite plus Next
  browser evidence.

## Evidence

The packet binds these visual checks:

- Vite browser evidence:
  `python3 scripts/vite_playwright_snapshot_smoke.py`
- Next browser evidence:
  `python3 scripts/nextjs_playwright_snapshot_smoke.py`

It also binds focused Next behavior checks:

- `python3 scripts/nextjs_pixel_office_floor_smoke.py`
- `python3 scripts/nextjs_pixel_office_dispatch_smoke.py`
- `python3 scripts/local_brief_prepared_action_smoke.py`
- `python3 scripts/nextjs_local_brief_smoke.py`
- `python3 scripts/nextjs_customer_worker_dispatch_smoke.py`
- `python3 scripts/nextjs_customer_worker_async_job_smoke.py`
- `python3 scripts/nextjs_customer_worker_prepared_action_smoke.py`

## Retirement Commit Requirements

Every future retirement commit must name the exact route pair, keep
`/workspace/pixel-office` deep links working through a redirect or compatibility
route, update the UI/API parity matrix, and rerun Vite plus Next browser
evidence after the route change.

The commit must not change Agent Gateway CLI/API/MCP contracts and must not
commit local databases, generated artifacts, raw prompts, raw responses, private
transcripts, or secrets.

## Verification

```bash
python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
```
