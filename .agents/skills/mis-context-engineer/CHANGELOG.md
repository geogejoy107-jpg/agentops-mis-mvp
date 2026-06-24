# Changelog

## 0.2.0 — 2026-06-22

### Added

- `HarnessProfile` schema and default profile.
- `LoopPolicy` schema and bounded default loop.
- Deterministic local context-builder CLI.
- Stable-prefix, delta-context, cache-key and token-efficiency metrics.
- Adaptive retrieval and marginal-gain early exit.
- Loop iteration trace and explicit stop reasons.
- Performance benchmark cases.
- Loop/Harness and performance/token reference documents.
- Package manifest and third-party notices.

### Changed

- Upgraded `SKILL.md` from TRACE-only v0.1 to a Harness + Loop + TRACE operating model.
- Extended the Context Manifest to v0.2 with performance, cache and loop evidence.
- Extended evaluation coverage from ten governance cases to governance plus efficiency/loop cases.
- Updated the smoke test to validate and execute the packaged prototype.

### Unchanged

- No MIS runtime, database schema, live adapter, or canonical project-state change.
- Memory writeback remains candidate-only.
- Embeddings, semantic retrieval and graph databases remain optional and disabled by default.

## 0.1.0 — 2026-06-21

- Initial authority-aware TRACE workflow.
- Context Manifest and Memory Write Proposal schemas.
- SOTA reference matrix.
- Ten governance evaluation cases.
