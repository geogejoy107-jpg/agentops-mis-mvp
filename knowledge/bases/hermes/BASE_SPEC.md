# Hermes Base Spec

Hermes is a local gateway/runtime adapter for confirmed live agent execution. MIS records safe summaries and evidence, not raw gateway payloads.

## Reuse

- OpenAI-compatible local gateway probes.
- Live worker adapter when confirmed.
- Runtime connector health events.

## Boundaries

- Do not default to live execution.
- Do not store raw prompts or responses.
- Keep gateway URLs and credentials in environment/config.
