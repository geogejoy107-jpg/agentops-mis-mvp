# Release Freeze Protocol

This document defines the v1.5 hardening freeze for AgentOps MIS. It is a
control-plane rule for the release branch, not a generated evidence packet.

## Freeze State

- Freeze status: `ACTIVE_HARDENING_FREEZE`
- Branch: `codex/agent-gateway-kb-demo`
- Started on: `2026-06-22`
- Baseline reviewed SHA: `6e7a0a74afe9ea6dcec4928eaad100310d202638`
- Authoritative current candidate SHA source: `git rev-parse HEAD`
- Authoritative current CI source: GitHub Actions or `gh run list` for the
  current head SHA.

The baseline SHA records where the hardening freeze began. The exact candidate
SHA for release review is still emitted at runtime by
`scripts/release_evidence_packet_smoke.py`, so tracked files do not become stale
release packets when a hardening-only fix lands.

## Allowed During Freeze

- Security, correctness, release-readiness and evidence-gate fixes.
- CI, smoke-test, runbook, checklist, rollback and recovery improvements.
- Documentation that narrows claims, records limitations or improves operator
  verification.
- Dependency or build changes only when required to keep deterministic gates
  passing.

## Forbidden During Freeze

- New product features unrelated to the v1.5 hardening objective.
- New live provider behavior or broader Hermes/OpenClaw execution defaults.
- Raw credentials or raw credentials-like material, private prompts, customer
  document bodies, transcripts, local databases, unsafe logs or runtime state in
  tracked files.
- Public/commercial readiness claims that are not proven by current gates.

## Merge Checks

The branch is not `READY_TO_MERGE` until remote repository protection or an
equivalent ruleset requires successful checks before merge. Local CI existence
is not enough for this final claim.

Strict final checks:

```bash
python3 scripts/release_freeze_protocol_smoke.py --require-clean --require-green-ci --require-remote-checks
python3 scripts/release_evidence_packet_smoke.py --require-clean --require-green-ci
python3 scripts/merge_readiness_status_smoke.py --require-ready-to-merge
```

Default CI checks may pass while remote protection is unavailable to the local
checker; strict final checks must prove required-check enforcement before
`READY_TO_MERGE`.
