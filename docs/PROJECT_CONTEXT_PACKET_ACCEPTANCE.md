# Project Context Packet Acceptance

## Purpose

This slice closes the difference between proving that knowledge retrieval ran
and giving an AI worker enough reviewed project context to perform useful work.
It does not ingest Codex/OpenClaw conversation archives or turn raw transcripts
into project authority.

## Product Contract

- `agentops knowledge evidence-packet` remains metadata-only retrieval proof.
- `agentops knowledge context-packet` returns bounded redacted summaries for
  transient model use.
- Context may come from versioned Markdown or an `approved` Memory row.
- Candidate/rejected/stale Memory is not model authority.
- Agent Gateway workspace and task visibility still apply.
- The default packet allows five knowledge summaries, three approved memories,
  480 characters per block and 4000 characters total.
- Tool Call, Evaluation, Audit and Worker result payloads store context IDs,
  approved Memory IDs, packet/block hashes and counts, not summary text.
- Raw task text, source bodies, source refs, prompts, responses, credentials,
  private messages and full transcripts remain omitted.

## Runtime Flow

```text
MIS task
  -> task-aware Knowledge Index search
  -> bounded versioned summaries + approved Memory summaries
  -> transient Hermes/OpenClaw/Codex prompt context
  -> model result
  -> Run / Tool / Evaluation / Audit store hashes and IDs only
```

The bundled `knowledge/shared/agentops_mis_project_context.md` gives a newly
installed Host a concise product and authority baseline. Dynamic continuity
still comes from reviewed Memory rows and task state rather than editing a raw
conversation archive into the bundle.

## Verification

```bash
python3 -m py_compile server.py agentops_mis_cli/agentops.py agentops_mis_cli/worker.py
python3 scripts/worker_knowledge_evidence_consumption_smoke.py
python3 scripts/agent_gateway_knowledge_scope_smoke.py
python3 scripts/knowledge_scope_policy_smoke.py
python3 scripts/knowledge_retrieval_quality_smoke.py
python3 scripts/module_boundary_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

The Worker smoke creates an isolated workspace and task, indexes versioned
knowledge, proposes and explicitly approves one project-context Memory, reads a
task-bound context packet, and runs a Mock Worker. It must prove that the Worker
used both bounded knowledge and approved Memory while the unique Memory marker
is absent from Tool, Evaluation, Audit and returned Worker evidence.

Local verification on 2026-07-23 passed all commands above. The retrieval
quality fixture reported Recall@5 `1.0` and MRR `1.0`; the gateway scope smoke
proved that Context Packet summaries stay inside the bound workspace and that
workspace header/query spoofing returns `403`; the secret scan found zero
findings across 816 tracked files.

Mock execution verifies deterministic protocol behavior only. Product-level
Hermes/OpenClaw evidence requires a current exact Host package, an explicitly
authorized task and a real persistent Worker run.

## Known Limitations

- Summaries are local FTS/redaction output, not semantic embeddings.
- The current packet is bounded text, not a long-term automatic compaction
  policy for Codex/OpenClaw session archives.
- Old Hosts expose evidence-only retrieval until upgraded.
- Physical second-device acceptance remains a separate Private Host gate.
