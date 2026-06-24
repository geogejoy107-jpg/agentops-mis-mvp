# Loop Engineering and Harness Engineering

## Roles

```text
Harness Engineering: defines the operating environment around an Agent.
Loop Engineering: defines bounded iteration, evaluation and stopping.
AgentOps MIS: governs project authority, scope, evidence, review and audit.
```

## HarnessProfile

A versioned HarnessProfile defines:

- authority and source order;
- workspace, project and task scope;
- retrievers and tool capabilities;
- filesystem, network and write boundaries;
- stable-prefix and cache policy;
- token budgets and model routing;
- metrics, validation and candidate-only writeback.

The Harness applies scope and redaction before ranking, pins repository facts to an exact commit, prefers a local lexical path first, records deterministic policy/source hashes, and degrades safely when an optional backend is unavailable.

## LoopPolicy

```text
PREPARE -> RETRIEVE -> ASSESS -> PACK -> EVALUATE -> REFINE or STOP
```

Each iteration records the retrieval mode, item counts, token use, coverage, authority precision, scope violations, marginal gain, latency, checkpoint hash and decision.

Stop reasons include success, missing Git context, scope block, unresolved conflict, insufficient budget, token or latency budget, maximum iterations, marginal gain, no more sources, validation failure and human escalation.

Every iteration must add evidence or improve a named metric. Evaluation cannot weaken scope or authority rules. The result carries a Context Manifest, metrics and evidence references.

## Parallelism

Parallelize independent source reads, searches, evaluation dimensions and isolated Codex worktrees. Do not allow multiple writers on one branch, uncontrolled shared mutable state, or dependent tasks without a dependency gate.

For coding, one conversation normally owns one worktree, branch and PR. A Commander synthesizes evidence from the resulting PRs and artifacts.

## MIS mapping

```text
HarnessProfile  -> template, capability and policy
LoopPolicy      -> workflow, checkpoint and evaluation
ContextManifest -> artifact
Loop iteration  -> run step or runtime event
Memory proposal -> candidate memory
Human decision  -> review and audit
```

The MIS ledger remains authoritative.
