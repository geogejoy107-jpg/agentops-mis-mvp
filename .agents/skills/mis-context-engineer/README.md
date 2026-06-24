# MIS Context Engineer v0.2.0

A dependency-light prototype for producing auditable, authority-aware, scope-safe, bounded-loop and token-efficient project context for AgentOps MIS.

## New in v0.2

- Explicit HarnessProfile and bounded LoopPolicy contracts.
- Stable-prefix and dynamic task-context separation.
- Full-versus-delta token accounting and cache metrics.
- Early exit, marginal-gain, latency, token and iteration limits.
- Deterministic local context-builder CLI and benchmark cases.
- Candidate-only memory writeback.

## Quick start

```bash
python3 scripts/mis_context_engineer_smoke.py
python3 scripts/mis_context_engineer_cli.py build --request .agents/skills/mis-context-engineer/examples/sample-request.json --output /tmp/context-manifest.json
python3 scripts/mis_context_engineer_cli.py benchmark --cases .agents/skills/mis-context-engineer/evals/performance_cases.json
```

The CLI uses only the Python standard library. Optional `jsonschema` and `PyYAML` packages provide additional validation.

## Architecture

```text
HarnessProfile -> bounded LoopPolicy -> TRACE -> Context Manifest -> Agent Run -> evidence -> candidate memory review
```

This package does not replace GitHub, AgentOps MIS SQLite/API, or the Notion Project Ledger. It does not auto-approve plans, execute external writes, or promote memory.

## Runtime integration status

Prototype only. It does not change `server.py`, the MIS database schema, live runtime adapters, or canonical project state. Runtime adoption remains gated by current P0/P1 priorities and human review.
