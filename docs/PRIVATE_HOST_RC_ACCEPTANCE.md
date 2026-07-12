# Private Host Release Candidate Acceptance

Status: in progress; not yet a Release Candidate

This matrix is the requirement-by-requirement completion record for
`LOCAL_HOST_REMOTE_CONSOLE_SPEC.md`. A deterministic smoke proves only the
bounded behavior it names. Cross-device and real-runtime rows require fresh
physical evidence and cannot be closed by mock output.

## Functional Acceptance Matrix

| # | Requirement | Current evidence | Status |
|---|---|---|---|
| 1 | Clean Host installs from a versioned asset without cloning | `PRIVATE_HOST_BUNDLE_ACCEPTANCE.md` proves an integrity-checked offline archive install in a temporary HOME. No GitHub Private Host prerelease or second-Mac download/install receipt exists yet. | Partial |
| 2 | `agentops host start` serves production UI/API/ledger/knowledge and actionable worker state | `PRIVATE_HOST_LIFECYCLE_ACCEPTANCE.md` plus bundle smoke cover installed CLI, production UI, init, doctor, start/status/stop and fail-closed Runtime readiness. | Passed locally |
| 3 | Dependency-free second computer opens private HTTPS console and authenticates | Human Session, CSRF, trusted Origin and Tailscale lifecycle are deterministic-smoke covered. Real second-device HTTPS login is missing. | External evidence required |
| 4 | Unauthenticated UI/API data fails closed | `human_browser_auth_smoke.py`, artifact-download smoke and lifecycle acceptance cover anonymous denial, role/session separation and CSRF/Origin checks. | Passed locally |
| 5 | Remote task, observation, approval, evaluation/audit review and approved artifact download | Customer dispatch and ledger views exist; Audit and Memory use live APIs; memory decisions write through the approver route; approved artifact download is Session/workspace/approval checked and audited. A second-device end-to-end receipt remains open. | Partial |
| 6 | Explicitly confirmed Hermes/OpenClaw task writes complete bounded evidence | `PRIVATE_HOST_REAL_RUNTIME_CLIENT_ACCEPTANCE.md` records fresh completed Hermes and OpenClaw runs through an Owner Session. | Passed on Host |
| 7 | Console disconnect does not stop Host Worker or lose task | `PRIVATE_HOST_CONSOLE_DISCONNECT_ACCEPTANCE.md` proves independent mock Worker completion and reconnect readback. Real tailnet/browser loss during a live Runtime task is missing. | Partial |
| 8 | Host restart preserves ledger and knowledge state | `PRIVATE_HOST_RESTART_PERSISTENCE_ACCEPTANCE.md` covers Session, task and a 194-document local Markdown/FTS index remaining searchable after managed restart. | Passed locally |
| 9 | Backup and restore pass on isolated database | `PRIVATE_HOST_BACKUP_RESTORE_ACCEPTANCE.md` covers strict manifest/hash/schema/integrity/foreign-key checks, atomic replacement and access revocation. | Passed locally |
| 10 | Release/Git contain no credentials, DB, raw prompt/response or generated dependencies | Bundle forbidden-member scan, secret scan and tracked-file selection pass. The two local sample-export drifts remain explicitly excluded from commits. | Passed locally; repeat at RC |

## Release Gates

The RC may be declared only after all of the following are attached to one
exact commit and version tag:

- push and pull-request CI are green at the exact tag commit;
- `.zip`, `.tar.gz` and `.sha256.json` are attached to a GitHub prerelease;
- another Mac downloads, verifies and installs that exact asset without a
  repository, Node or Git;
- Host and console are connected through private HTTPS without replacing an
  unrelated Tailscale Serve target;
- the second computer completes login, task dispatch, observation, approval,
  evaluation/audit review and approved artifact download;
- closing the browser or disconnecting tailnet does not stop a fresh confirmed
  Hermes/OpenClaw task, and reconnect shows the same task/run evidence;
- backup/restore, restart/knowledge persistence, upgrade/rollback, secret scan,
  bundle scan and production UI build pass at the same commit.

## Evidence Rules

- Record bounded IDs, counts, statuses, exact commit, tag and checksums only.
- Do not record passwords, setup codes, Session/Agent tokens, raw prompts,
  raw responses, private messages, full transcripts, database files or Host
  paths from another user account.
- Label mock/loopback smokes as deterministic fallback; never use them as the
  physical second-device or real Runtime proof.
- A failed row remains open even when adjacent implementation tests pass.
