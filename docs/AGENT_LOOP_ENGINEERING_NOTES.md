# Agent Loop Engineering Notes

## Scope

These notes capture current external patterns for building a governed agent loop:

`observe -> plan -> execute -> trace -> evaluate -> human review -> memory/promotion -> regression`.

The goal for AgentOps MIS is not unchecked self-improvement. The goal is a local-first loop where every improvement candidate has evidence, review state, rollback context, and durable audit.

## External Signals

- LangGraph's production pattern for human-in-the-loop work is persistent interruption: pause execution, surface a review payload, then resume from saved state after a human decision. This maps to MIS approvals plus resumable workflow jobs.
- LangChain's Human-in-the-Loop middleware treats risky tool calls as policy decisions before execution. This maps to MIS approval rules, risk levels, and tool-call gates.
- Langfuse and Phoenix show the dominant open-source observability shape: traces, spans, evaluations, prompt/output metadata, datasets, and self-hosting. MIS should stay runtime-neutral and keep raw private content out of the ledger by default.
- OpenLLMetry shows the likely integration standard: emit OpenTelemetry/OpenInference-style spans so external observability systems can ingest MIS activity without bespoke adapters.
- Reflexion and Voyager support the "experience -> memory/skill -> retry" loop, but both imply a gate: only useful, verified experience should become reusable memory or skill.
- Recent agent-evaluation surveys emphasize realistic, continuously updated tasks and fine-grained metrics for planning, tool use, memory, safety, robustness, and cost-efficiency.
- Self-evolving agent work such as EvolveR is promising but increases misevolution risk: memory, tools, workflows, and policies can degrade unless promotion is reviewed and reversible.

## Implications For AgentOps MIS

- Keep `agent_plan`, plan-evidence manifests, review queue, and audit logs as the core loop objects.
- Promote only through explicit lifecycle transitions: candidate -> approved/rejected/stale/superseded.
- Treat Commander synthesis as the control-plane summary layer: merge worker outputs, require approval, then promote to memory or customer delivery.
- Add OpenTelemetry/OpenInference export later as an adapter, not as the primary source of truth.
- Prefer small regression datasets from approved failures and delivery reviews before adding vector databases or autonomous prompt mutation.
- Make action queues priority-aware so approved-but-not-promoted artifacts cannot disappear behind ordinary memory review.

## Local Implementation

- `evaluation_case_candidates` is the first regression/golden-case ledger. It can be proposed from an existing evaluation, run, artifact, customer delivery, Commander synthesis, or manual source.
- Proposal defaults to preview-only. `confirm_create` / `agentops eval propose-case --confirm-create` is required to write the candidate.
- Candidate review is explicit through `agentops review queue`, `agentops eval approve-case`, `agentops eval reject-case`, or the `/workspace/agents` review queue.
- `evaluation_case_runs` is the first execution ledger for approved cases. `agentops eval run-cases` previews by default, and `--confirm-run` writes a local-only benchmark evidence chain across `runs`, `evaluations`, `artifacts`, `runtime_events`, and `audit_logs`.
- The v1 runner is intentionally conservative: `rule` / `llm_mock` checks validate case readiness and expected-output evidence without calling Hermes/OpenClaw live. Live runtime replay should be a later, approval-gated adapter.
- `/admin/evaluations` is now the operator-facing loop console for this slice: it loads candidate cases, approved benchmark cases, and recent case-run evidence; operators can approve/reject candidates and preview or confirm local benchmark execution from the UI.
- Failed `evaluation_case_runs` are projected into `agentops review queue` and `/workspace/agents` as read-only risk items with run/task links and CLI readback commands. They are not approval objects; the operator can use `agentops eval remediate-case-run --case-run-id ...` to preview a planned Commander-compatible MIS remediation task, then `--confirm-create` to write the task plus runtime/audit evidence. The resulting task appears in `agentops commander packages` and can be dispatched/synthesized through the Commander loop. No Hermes/OpenClaw live execution or code change happens in the conversion step.
- Approved Commander synthesis reports from that remediation loop can now be promoted through `agentops commander promote-synthesis --mode both --confirm-promote`. Promotion creates a memory candidate plus customer delivery artifact, keeps raw private content out of the ledger, and makes `agentops operator action-plan` report `remediation_loop=promoted` with promoted memory/delivery counts instead of asking for duplicate synthesis.
- Agent Gateway `runs/start` is now a pre-execution hard gate: it rejects unplanned execution with `agent_plan_required`, verifies the selected Agent Plan, stores `agent_plan_id` and `plan_hash` on the run, and lets the worker loop start only after plan verification. This closes the old gap where an agent could create a plan but execute an unrelated run.
- `agentops operator action-plan` now has a read-only `execution_evidence` source. It audits recent completed/failed runs for missing plan bindings, missing or unverified plan-evidence manifests, and missing tool/evaluation/artifact/audit rows, then surfaces `agentops operator remediate-evidence-gap --run-id ...` as a preview-only next command. `--confirm-create` turns the gap into a deterministic Commander work package for dispatch instead of directly mutating plan/manifests. After dispatch writes a full worker evidence chain with verified plan evidence, the source gap reports `remediation_status=verified` and leaves the blocked lane while preserving the legacy debt; the next actions then move through Commander synthesis, approval, promotion into memory/delivery evidence, and a final `agentops operator close-evidence-gap --decision accepted_remediation --confirm-close` audit decision. `waived` and `reopen` are explicit decisions too, so the loop can close legacy debt without silently rewriting history.
- Operator Health recovery is now projected into the backend action-plan as a non-recursive `operator_health` lane for local readiness, security readiness, worker fleet health, and human-review pressure. `/workspace/agents` still displays the compact health score from `agentops operator health`, but executable queue items come from `agentops operator action-plan`, keeping CLI/API/UI operators on the same receipt-governed command source.
- Confirmed Action Queue receipts now have an operator-level evaluation ledger: `verified` and `failed` receipts write `operator_action_evaluations` plus an `operator.action_queue_evaluation` audit row, while preview and `recorded` receipts remain non-evaluating. Action-plan receipt matches expose the latest receipt evaluation so recovery work can be audited as action + verification + scored result.
- The bounded loop runner policy now lives in `agentops_mis_cli/advance_loop_policy.py` and is exposed by `agentops operator advance-loop-policy`. CLI execution, backend handoff, UI display, and smoke tests reference the same `advance_loop_local_bounded_v1` contract so Hermes/OpenClaw/Codex can inspect the allowlist, denylists, server-shell boundary, and sample decisions before advancing a loop.
- `agentops operator loop-self-check` is the pre-advance check for agent loop work. It is read-only and aggregates the bounded policy contract, selected action allowlist decision, handoff health, receipt coverage, receipt evaluations, and audit-ledger proof so agents can inspect the loop boundary before running `advance-loop`.

## Source Leads

- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangChain HITL middleware: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- Langfuse GitHub: https://github.com/langfuse/langfuse
- Arize Phoenix GitHub: https://github.com/Arize-ai/phoenix
- OpenLLMetry GitHub: https://github.com/traceloop/openllmetry
- Reflexion paper: https://arxiv.org/abs/2303.11366
- Voyager paper: https://arxiv.org/abs/2305.16291
- Survey on Evaluation of LLM-based Agents: https://arxiv.org/abs/2503.16416
- EvolveR / experience-driven lifecycle: https://arxiv.org/abs/2510.16079
- Misevolution risk paper: https://openreview.net/forum?id=Fd1jgQQW28
