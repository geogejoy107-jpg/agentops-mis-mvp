# Architecture Rules

- MIS is the control plane and ledger.
- Agent runtimes execute work; they do not become the source of truth.
- Browser UI is for human supervision. Agents should use Agent Gateway CLI/API.
- Ledger rows store summaries, hashes, IDs, and structured evidence.
- Runtime-specific integrations must stay behind connector boundaries.
- Prefer small, testable additions over rewrites.
