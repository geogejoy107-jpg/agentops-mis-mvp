# Notion, Open Source Base, and Local Loop Convergence Plan

## Purpose

This plan connects three currently separate lanes:

1. Notion Project Memory as the Web GPT / human collaboration layer.
2. Local Open Source Experiment Base as the safe way to borrow open-source methods and run local experiments.
3. Local Hermes/OpenClaw loop convergence as the operator path that turns experiments into governed agent work.

The goal is not to add another product feature. The goal is to make the current local-first system easier to coordinate across Codex, Web GPT, Notion, GitHub, and the MIS runtime ledger.

## Current Lane Board

| Lane | Branch / PR | Current state | Merge posture |
| --- | --- | --- | --- |
| Local Open Source Experiment Base | PR #25 `codex/local-open-source-experiment-base-clean` | Clean CI, merge state clean | First merge candidate |
| Notion Project Memory Connector Layer | PR #26 `codex/notion-project-memory-connector-layer` | Clean CI, merge state clean | Second merge candidate |
| Fast Local Loop Bootstrap / Service Closure | `codex/loop-bootstrap-fast-path` | Remote branch has green exact-head push CI at `134d606` | Rebase/open PR after #25/#26 are resolved |
| Commercial migration closed loop | PR #22 `codex/commercial-migration-closed-loop` | Dirty / larger product line | Keep separate until local loop convergence is stable |
| Older open-source research PRs | PR #12 / PR #4 | Superseded or behind | Do not use as merge base |

## Authority Boundary

| Layer | What it owns | What it must not own |
| --- | --- | --- |
| Notion Project Memory | Web GPT collaboration, candidate deltas, reviewed decisions, risks, backlog, handoff | Runtime execution truth, approval wall state, delivery readiness, audit authority |
| GitHub | Code, branch, commit, PR, CI evidence | Runtime ledger facts or private credentials |
| Local Open Source Experiment Base | Reference atlas, knowledge base entries, experiment plans, local evidence packets | External OSS as authority over MIS tasks/runs/approvals/audit |
| AgentOps MIS SQLite/API | Task, run, tool call, approval, artifact, evaluation, audit, connector trust, worker evidence | Raw private transcripts, raw prompts/responses, unmanaged external state |
| Hermes/OpenClaw local loop | Governed execution path through MIS gates | Direct uncontrolled execution outside Method Block / Approval Wall / audit |

## Notion Collaboration Integration

Use Notion as the cross-conversation visibility layer:

1. Codex writes concise Project Ledger entries for significant project deltas.
2. Entries start as `Proposed` or `Inbox`, not canonical runtime truth.
3. Entries include GitHub PR links, branch names, commit hashes, CI run IDs, and MIS ledger IDs when available.
4. Web GPT can read the Notion entry and continue discussion without needing local terminal access.
5. Codex verifies Notion claims against GitHub and MIS before using them for implementation.

Minimum Project Ledger fields for this convergence lane:

- `Title`: short project delta title
- `Type`: `Proposal` or `Handoff`
- `Status`: `Proposed`
- `Authority Class`: `Candidate`
- `Source System`: `AgentOps MIS`
- `Data Domain`: `Project State`
- `Module`: `Project Governance`
- `Priority`: `P1`
- `Canonical`: false
- `Repository`: `geogejoy107-jpg/agentops-mis-mvp`
- `Branch`: active convergence branch
- `Commit`: current branch commit when available
- `Summary`: redacted summary only
- `Next Action`: next safe merge/run step

## GitHub Integration Order

1. Keep PR #25 and PR #26 as separate clean draft PRs until the user is ready to merge.
2. Merge or cherry-pick #25 first because `codex/loop-bootstrap-fast-path` already contains the open-source base commit `a411bc0`.
3. Merge or cherry-pick #26 second because it is independent and only documents/guards Notion collaboration.
4. Rebase `codex/loop-bootstrap-fast-path` on top of the resulting main.
5. Open a focused loop convergence PR from the rebased fast-path branch.
6. Run exact-head CI and the loop-specific local smoke set.
7. Only after the fast path is clean should larger lines such as commercial migration be reconciled.

## Local Loop Convergence Acceptance

Before declaring the local loop line converged, verify:

- `agentops operator loop-bootstrap --adapter hermes --fast`
- `agentops operator loop-bootstrap --adapter openclaw --fast`
- `agentops operator service-closure --adapter hermes --fast --run-service-check`
- `agentops operator service-closure --adapter openclaw --fast --run-service-check`
- `agentops operator loop-driver --adapter hermes --confirm-loop --auto-service-closure --max-steps 1`
- `agentops operator loop-driver --adapter openclaw --confirm-loop --auto-service-closure --max-steps 1`
- `python3 scripts/operator_loop_bootstrap_smoke.py`
- `python3 scripts/operator_service_closure_fast_smoke.py`
- `python3 scripts/operator_loop_driver_smoke.py`
- `python3 scripts/release_evidence_packet_smoke.py`
- `python3 scripts/secret_scan_smoke.py`

Live Hermes/OpenClaw execution should be used for product-readiness claims only when the local runtimes are available and explicitly authorized. Offline CI evidence remains fallback evidence and must be labeled as such.

## Convergence Rules

- Do not merge dirty PRs into the convergence lane.
- Do not let Notion entries auto-promote to canonical runtime facts.
- Do not ingest private messages, full transcripts, raw prompts, raw responses, credentials, DB files, caches, or generated exports.
- Do not use superseded research PRs as an implementation base.
- Keep open-source experiments as local evidence until MIS has a reviewable plan, evidence packet, and evaluation case.
- Keep fast loop bootstrap copy-only/read-only until deep verification passes.

## Next Safe Actions

1. Record this convergence plan in Notion Project Ledger as a `Proposed` project delta.
2. Keep PR #25 and PR #26 visible as clean merge candidates.
3. Open or refresh a focused PR for `codex/loop-bootstrap-fast-path` after the two clean base PRs are settled.
4. Use the local loop acceptance commands above to prove the convergence path on the current machine.
5. Feed any stable result back into Notion as a short Project Ledger update and into MIS as ledger evidence when it involves runtime execution.

