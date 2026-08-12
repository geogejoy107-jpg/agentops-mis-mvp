# Research Lab API, CLI and UI contract

API version: `template-platform-api/v1`

Route prefix: `/api/v1/templates/research_lab`

UI prefix: `/solutions/research_lab/`

The manifest registers concrete method/path contracts for all Research read
models plus project and experiment creation. Controllers receive shared-auth Core references and call
the domain service; authorization is inherited from MIS Core and domain code
never authenticates identities itself. Stable domain errors use the
`research.*` namespace.

Collection and deep-link handlers are implemented for Experiment, Trial,
JobAttempt, logs, metrics and Checkpoints. The React extension resolves the
governed record ID from `?id=` and percent-encodes it before calling the typed
route. Missing IDs fall back to the collection rather than manufacturing a
detail record.

The shared CLI registers:

- `agentops template research-lab validate-manifest`
- `agentops template research-lab migration-dry-run <records.json>`
- `agentops template research-lab checkpoint-validate <checkpoint>`
- `agentops template research-lab api-contracts`
- `agentops template research-lab bdci-build <spec.json>`
- `agentops template research-lab operation <name> <refs.json> <body.json>`

Domain verification command:

```text
python3.11 -m unittest discover -s tests/templates/research_lab -t . -p 'test_*.py'
```

The domain package supplies `templates/research_lab/ui/ResearchLabExtension.tsx`.
After C0 satisfies `C0_INTEGRATION_CHANGE_REQUEST.md`, its 18 deep-linkable
surfaces call the typed API with same-origin credentials and
render loading, empty, ready, degraded, error/recovery and permission-denied
states. Project and Experiment forms POST to the API rather than mutating local
state. Governed action controls call the operations adapter; privileged execution
actions remain Core PreparedAction/Approval gated. The current C1 worktree alone
does not claim that C0-owned server, CLI or AppShell mounting has happened.
All 41 method/path contracts are registered individually through the SDK; C0
must read them back and mount them before product availability can be claimed.

UI actions use shared MIS approval semantics:

```text
prepare -> Core PreparedAction -> Core Approval -> execute once -> readback -> receipt
```
