# Performance and token-efficiency design

## Objective

Reduce latency and token use while preserving authority, scope, provenance, safety and acceptance coverage. The target is useful verified context per token, not the smallest prompt.

## Cost model

```text
latency = source discovery + retrieval + optional reranking + packing + validation + model/tool work + refinement iterations
```

```text
full tokens  = stable prefix + mandatory authority + task delta + implementation evidence + optional support
delta tokens = changed stable segments + changed task/evidence items + invalidated reused items
```

## Optimizations

1. **Hard gates first.** Apply scope, source existence, Git context, redaction, authority, temporal and conflict checks before expensive ranking.
2. **Stable prefix.** Put the short repository map, authority rules, safety contract, tool definitions and output schemas before variable task context.
3. **Content-addressed reuse.** Cache by source hash/version, scope fingerprint, Harness hash, Loop hash, retriever version and query fingerprint.
4. **Delta context.** Reuse unchanged project context and send only the work package, branch/commit delta, evidence delta and unresolved questions.
5. **Tier budgets.** Reserve capacity for output, safety and mandatory authority before implementation or optional support.
6. **Adaptive retrieval.** Start with mandatory plus lexical retrieval; escalate only when a named coverage gap remains.
7. **Early exit.** Stop when coverage passes, no item has positive marginal utility, cost exceeds remaining budget, or only duplicates/lower-authority items remain.
8. **Bounded summaries.** Keep source refs, hashes and selected snippets instead of copying complete documents or transcripts.
9. **Model routing.** Use deterministic code for scope, hashing, dedupe and budgeting; use a model only for unresolved classification or synthesis.
10. **Bounded parallel I/O.** Parallelize independent reads and evaluation dimensions, not dependent state changes.

## Example token allocation

```yaml
total: 8000
reserved_output: 1200
stable_prefix: 900
mandatory_authority: 1600
task_and_acceptance: 1000
implementation_evidence: 1800
approved_memory: 700
optional_support: 800
```

Unused capacity may flow downward. Optional tiers may not evict safety or mandatory authority.

## Metrics

```yaml
wall_time_ms:
retrieval_time_ms:
packing_time_ms:
retrieval_calls:
candidate_count:
gated_count:
included_count:
cache_hits:
cache_hit_rate:
full_context_tokens:
delta_context_tokens:
estimated_cacheable_tokens:
token_utilization:
token_efficiency:
coverage:
authority_precision:
scope_violations:
loop_iterations:
stop_reason:
```

Definitions:

```text
token_utilization = full_context_tokens / available_input_budget
token_efficiency  = useful_included_tokens / full_context_tokens
cache_hit_rate    = reused_items / eligible_reuse_items
marginal_gain     = current_coverage - previous_coverage
```

Provider-reported token and latency data should replace estimates when available.

## Prototype acceptance targets

- deterministic build needs no network or model call;
- packing never exceeds the input budget;
- loop iterations never exceed policy maximum;
- identical inputs produce identical output hashes;
- a repeated request reports reuse and lower or equal delta tokens;
- scope-denied items never reach ranking or packing;
- bundled small benchmarks finish in under one second on a typical development machine;
- optional semantic or graph retrieval is skipped when lexical coverage passes.

These are prototype gates, not production service objectives.
