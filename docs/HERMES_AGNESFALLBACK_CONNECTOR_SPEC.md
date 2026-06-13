# Hermes / Agnesfallback Connector Spec

## Goal

Show that AgentOps MIS can manage a real local runtime adapter shape while staying safe enough for classroom demo.

## Status API

`GET /api/integrations/hermes/status` returns:

- Hermes profile, gateway URL, API listening state and runtime mode.
- Agnesfallback CLI path, binary existence, gateway URL and API listening state.
- Whether real runs are enabled and whether confirmation is required.

## Probe API

- `POST /api/integrations/hermes/probe`: records Hermes health as available or unavailable.
- `GET /api/integrations/hermes/models`: tries local `/v1/models`; unavailable is recorded as a normal connector event.
- `POST /api/integrations/hermes/cli-probe`: dry-run plan unless explicitly confirmed.
- `POST /api/integrations/hermes/chat-completion-probe`: dry-run plan unless explicitly confirmed.

## Fixed Prompts

The fixed probes use constant, non-sensitive prompts:

- CLI: reply with `AGNESFALLBACK_OK`.
- API: reply with `HERMES_AGNES_API_OK`.

The stored ledger keeps prompt hashes and redacted short output summaries only.

## Non-Goals

- No default `--yolo`.
- No arbitrary prompt execution in v1.2.1.
- No background cron execution.
- No remote deployment or public network binding.
