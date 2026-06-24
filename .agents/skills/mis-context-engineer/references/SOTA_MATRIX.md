# MIS Context Engineer — Code-Informed Reference Matrix

> Observed: 2026-06-21  
> Status: research evidence for a prototype; not an approved architecture decision.  
> Rule: pin an exact upstream commit and review its license/security before copying or modifying any implementation. This prototype vendors no upstream code.

## Selection Principle

No single memory framework owns AgentOps MIS project truth. Upstream systems may provide retrieval, extraction, temporal, graph, or context-packing techniques. MIS retains authority, permission, approval, lifecycle, evidence, and audit semantics.

```text
Upstream memory/context technique
-> adapter or algorithm candidate
-> MIS scope/authority gate
-> Context Manifest
-> Agent Run
-> candidate-only Memory Write Proposal
-> human review
```

## Matrix

| System | Code/design inspected | Strong idea to adopt | MIS adaptation | Do not inherit blindly |
|---|---|---|---|---|
| Mem0 | `mem0/memory/main.py` | Pluggable LLM/embedder/vector/reranker factories; user/agent/run filters; lexical, semantic and entity signals; validation and sensitive-field handling | Keep retrieval backends replaceable; require project/workspace scope; use multi-signal rank fusion after hard gates | External memory store as project authority; telemetry or raw content without MIS privacy policy; automatic promotion |
| Letta | root `README.md` stateful-agent and `memory_blocks` API | Explicit persistent state and labeled memory blocks that can be assembled into Agent context | Model Project Core, Workstream Shared, Task, Run-local and Archive context layers | Treating an Agent's mutable personal memory as approved project state |
| Graphiti | `graphiti_core/graphiti.py` | Episodic/entity/community separation; group IDs; driver abstraction; hybrid/RRF/cross-encoder recipes; ingestion-time versus event-time watermarks | Add optional temporal/relationship backend after FTS baseline; preserve `observed_at`, `valid_from`, `valid_to`, provenance and group/workspace scope | Neo4j as a P0 dependency; default raw episode storage; graph similarity bypassing authority/ACL |
| LangMem | root `README.md` | Storage-agnostic core primitives; hot-path memory tools; background extraction/consolidation | Split immediate retrieval from asynchronous candidate extraction; force all writes through Memory Write Proposal review | Letting an Agent decide that its own extracted memory is canonical |
| Aider | `aider/repomap.py` | Tree-sitter symbols; definition/reference graph; PageRank-style ranking; caching; strict map token budget | Implement an optional Repo Map retriever for coding tasks; emit selected symbols/tests as manifest items | Dumping a whole repository into context; using repo ranking without exact commit and visibility proof |

## Upstream Source References

- Mem0: `https://github.com/mem0ai/mem0/blob/main/mem0/memory/main.py`
- Letta: `https://github.com/letta-ai/letta/blob/main/README.md`
- Graphiti: `https://github.com/getzep/graphiti/blob/main/graphiti_core/graphiti.py`
- LangMem: `https://github.com/langchain-ai/langmem/blob/main/README.md`
- Aider Repo Map: `https://github.com/Aider-AI/aider/blob/main/aider/repomap.py`

## Algorithm Candidates

### 1. Authority-aware hybrid retrieval

Use hard gates first:

```text
source exists
AND scope visible
AND authority eligible
AND redaction safe
AND temporal window matches
AND unresolved conflict does not invalidate use
```

Then combine available rankings:

```text
lexical/BM25
semantic similarity (optional)
entity/graph proximity (optional)
repository symbol relevance (coding tasks)
authority/freshness/evidence quality
```

RRF is a good default fusion candidate because it combines rank positions without requiring scores from heterogeneous retrievers to be directly comparable. It remains a soft-ranking mechanism and must never override scope or authority gates.

### 2. Temporal claim model

Represent the difference between ingestion and event time:

```yaml
observed_at: when MIS saw the source
valid_from: when the claim became true
valid_to: when it stopped being true
source_created_at: upstream creation time
source_version: commit/hash/version
```

A current-state question should prefer a currently valid, non-superseded claim. A historical `as_of` question may include an older claim whose validity window overlaps the requested time.

### 3. Relationship model

```text
new
 duplicate_of
 updates
 supersedes
 conflicts_with
 derived_from
```

The relation is part of the evidence model, not just a prose note. `conflicts_with` remains unresolved until an approved decision or implementation evidence resolves it.

### 4. Context packing

Reserve budget for mandatory authority context and safety constraints, then select supporting items by marginal task utility per token. Add diversity penalties to avoid multiple near-identical summaries.

A simple v0 ordering is:

```text
mandatory authority
-> acceptance criteria
-> exact implementation/test evidence
-> approved memory
-> diverse supporting retrieval
-> candidate research
```

### 5. Candidate-only consolidation

Hot-path retrieval and background consolidation should be separate:

```text
Agent request
-> read-only context assembly
-> Agent execution
-> bounded evidence
-> asynchronous candidate extraction
-> dedup/conflict/scope checks
-> human review
```

## Proposed Backend Interfaces

These are conceptual contracts, not v0 runtime requirements.

```python
class RetrieverBackend:
    def search(self, request) -> list[Candidate]: ...

class RelationResolver:
    def classify(self, candidates) -> list[Relation]: ...

class ContextPacker:
    def pack(self, candidates, token_budget) -> ContextManifest: ...

class MemoryProposalWriter:
    def propose(self, evidence) -> list[MemoryWriteProposal]: ...
```

Initial implementations should remain local:

```text
LexicalRetriever      SQLite FTS5/BM25
ProjectDocRetriever   versioned Markdown
ApprovedMemoryReader  MIS memories table, approved only
RepoMapRetriever      optional later adapter
SemanticRetriever     disabled by default
GraphRetriever        deferred until evaluation evidence supports it
```

## Evaluation Before Adoption

Do not adopt an upstream mechanism based on a benchmark headline alone. Test it on named AgentOps MIS cases and compare against the current FTS baseline.

Minimum comparative metrics:

```text
authority precision
scope violation count
retrieval coverage
stale-memory selection rate
conflict detection rate
duplicate proposal rate
token cost
latency
reproducibility at exact commit/config
```

An added backend is justified only when it improves named cases without weakening permission, authority, privacy, or auditability.
