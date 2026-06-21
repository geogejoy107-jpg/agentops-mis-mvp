# Secret Registry

This registry records where secrets may live. It must never contain real secret values.

## Rules

- Do not commit tokens, API keys, OAuth refresh tokens, private transcripts, or raw customer data.
- Store only safe references, environment variable names, connector IDs, status, hashes, and redacted summaries.
- Agent Gateway responses must keep `token_omitted=true` when token metadata is returned.
- New connector credentials require human review before live writeback or upload.

## Known Secret Locations

- Codex auth: `~/.codex/auth.json`
- Hermes auth/config: `~/.hermes/`
- OpenClaw config: `~/.openclaw/openclaw.json`
- AgentOps CLI config: `~/.agentops/config.json`
- Runtime environment variables: `AGENTOPS_API_KEY`, `AGENTOPS_ADMIN_KEY`, `HERMES_GATEWAY_URL`, `NOTION_TOKEN`

## Ledger Policy

The MIS ledger may store:

- token IDs, safe refs, status, TTL, scopes, and heartbeat timestamps
- hashes of payloads or artifacts
- redacted summaries

The MIS ledger must not store:

- bearer tokens
- raw prompts/responses
- private conversation transcripts
- connector credentials
- full customer documents unless explicitly approved and scoped
