# Agent Loop Engineering Notes

## Scope

These notes capture current external patterns for building a governed agent loop:

`observe -> plan -> execute -> trace -> evaluate -> human review -> memory/promotion -> regression`.

The goal for AgentOps MIS is not unchecked self-improvement. The goal is a local-first loop where every improvement candidate has evidence, review state, rollback context, and durable audit.

## External Signals

- LangGraph's production pattern for human-in-the-loop work is persistent interruption: pause execution, surface a review payload, then resume from saved state after a human decision. This maps to MIS approvals plus resumable workflow jobs.
- LangChain's Human-in-the-Loop middleware treats risky tool calls as policy decisions before execution. This maps to MIS approval rules, risk levels, and tool-call gates.
- OpenAI Agents SDK frames production agents around agent definitions, handoffs, guardrails, human review, results/state, integrations, and observability. This supports keeping MIS loop objects separate: task/run/plan/evidence/governance first, runtime adapter second.
- AutoGen AgentChat's human-in-the-loop pattern exposes user feedback during a team run or via a user proxy. This maps to MIS review queue and approval lanes rather than agent-to-agent freeform chat as the source of authority.
- CrewAI Flows model human feedback as an explicit pause/review/resume step. This reinforces that Hermes/OpenClaw loop progress should be represented as receipted steps, not implicit background autonomy.
- Langfuse and Phoenix show the dominant open-source observability shape: traces, spans, evaluations, prompt/output metadata, datasets, and self-hosting. MIS should stay runtime-neutral and keep raw private content out of the ledger by default.
- OpenTelemetry GenAI semantic conventions are converging on a shared vocabulary for model calls, tool calls, usage, and retrieval metadata. MIS should export to that shape later while keeping SQLite/MIS ledgers authoritative.
- OpenLLMetry shows the likely integration standard: emit OpenTelemetry/OpenInference-style spans so external observability systems can ingest MIS activity without bespoke adapters.
- Reflexion and Voyager support the "experience -> memory/skill -> retry" loop, but both imply a gate: only useful, verified experience should become reusable memory or skill.
- Self-Refine supports iterative feedback/refinement without training, which maps to a bounded local loop only when each iteration has a verification record and a stop condition.
- SWE-agent's Agent-Computer Interface result is a useful reminder that agents need a purpose-built command surface. For MIS this means `loop-launch-packet`, compact launch briefs, worker preflight, readback commands, and receipt recording are product features, not internal plumbing.
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
- Operator Health recovery is now projected into the backend action-plan as a non-recursive `operator_health` lane for local readiness, security readiness, `local_ui_write_guard`, worker fleet health, and human-review pressure. `/workspace/agents` still displays the compact health score from `agentops operator health`, but executable queue items come from `agentops operator action-plan`, keeping CLI/API/UI operators on the same receipt-governed command source. The local UI/API write guard also appears in `operator loop-self-check`, so bounded advance can inspect the shared-mode write boundary before running the next loop action.
- Confirmed Action Queue receipts now have an operator-level evaluation ledger: `verified` and `failed` receipts write `operator_action_evaluations` plus an `operator.action_queue_evaluation` audit row, while preview and `recorded` receipts remain non-evaluating. Action-plan receipt matches expose the latest receipt evaluation so recovery work can be audited as action + verification + scored result.
- The bounded loop runner policy now lives in `agentops_mis_cli/advance_loop_policy.py` and is exposed by `agentops operator advance-loop-policy`. CLI execution, backend handoff, UI display, and smoke tests reference the same `advance_loop_local_bounded_v1` contract so Hermes/OpenClaw/Codex can inspect the allowlist, denylists, server-shell boundary, and sample decisions before advancing a loop. The allowlist includes read-only `operator runtime-doctor` and unconfirmed `operator execution-mode` so agents can inspect adapter health and dispatch mode before acting; `--confirm-run` remains denied. After the evidence-report work order is receipted, unscoped `advance-loop` may run the read-only `operator remediate-evidence-gap --run-id ...` preview and record the `handoff.evidence_remediation` receipt; `--confirm-create`, close-gap, approvals, dispatch, and other mutating steps remain explicit operator paths.
- `agentops operator loop-self-check` is the pre-advance check for agent loop work. It is read-only and aggregates the bounded policy contract, selected action allowlist decision, handoff health, receipt coverage, receipt evaluations, and audit-ledger proof so agents can inspect the loop boundary before running `advance-loop`.
- `agentops workflow run-task` now returns compact Agent Plan and plan-evidence readback for worker execution: `readback.agent_plan_verified`, `readback.plan_evidence_verified`, top-level `agent_plan`, and top-level `plan_evidence` with evidence counts. This makes the one-command Hermes/OpenClaw/mock worker path prove it followed READ/PLAN/RETRIEVE/COMPARE/EXECUTE/VERIFY/RECORD instead of merely returning a model summary.

## Source Leads

- LangGraph interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts
- LangChain HITL middleware: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- OpenAI Agents SDK: https://developers.openai.com/api/docs/guides/agents
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- AutoGen Human-in-the-Loop: https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/tutorial/human-in-the-loop.html
- CrewAI Human Feedback in Flows: https://docs.crewai.com/en/learn/human-feedback-in-flows
- Langfuse GitHub: https://github.com/langfuse/langfuse
- Arize Phoenix GitHub: https://github.com/Arize-ai/phoenix
- OpenTelemetry GenAI attributes: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/
- OpenLLMetry GitHub: https://github.com/traceloop/openllmetry
- Reflexion paper: https://arxiv.org/abs/2303.11366
- Self-Refine paper: https://arxiv.org/abs/2303.17651
- Voyager paper: https://arxiv.org/abs/2305.16291
- SWE-agent paper: https://arxiv.org/abs/2405.15793
- Survey on Evaluation of LLM-based Agents: https://arxiv.org/abs/2503.16416
- EvolveR / experience-driven lifecycle: https://arxiv.org/abs/2510.16079
- Misevolution risk paper: https://openreview.net/forum?id=Fd1jgQQW28
