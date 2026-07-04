# Agent Task Harness Engineering Spec

## Purpose

This spec defines the AgentOps MIS task harness discipline for real local
Hermes/OpenClaw work, CI fallback work, and future remote agents.

It complements the Harness company/control-plane research docs:

- `docs/research/HARNESS_ENGINEERING_RESEARCH_BRIEF.md`
- `docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md`
- `docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`
- `docs/HARNESS_STYLE_AGENTOPS_OPERATING_SPEC.md`
- `docs/LOCAL_TASK_HARNESS_ACCEPTANCE.md`
- `docs/OPENCLAW_LOCAL_HARNESS_DOGFOOD_2026_07_04.md`

The goal is not another dashboard or another runtime. The goal is a repeatable
task harness that turns agent work into a governed, replayable, auditable MIS
evidence chain.

## Fresh Research Inputs

Checked on 2026-07-04:

- Promptfoo coding-agent evaluation guide:
  `https://www.promptfoo.dev/docs/guides/evaluate-coding-agents/`
- Inspect AI framework:
  `https://inspect.aisi.org.uk/`
- SWE-bench repository:
  `https://github.com/swe-bench/SWE-bench`
- Harness-Bench paper:
  `https://arxiv.org/html/2605.27922v1`
- Arize traces and evals harness article:
  `https://arize.com/blog/improve-ai-agents-traces-evals-harness/`
- OpenAI Evals API guide and deprecation note:
  `https://developers.openai.com/api/docs/guides/evals`
- LangChain harness engineering case study:
  `https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering`
- Code as Agent Harness survey:
  `https://arxiv.org/html/2605.18747v1`

Key lesson: agent performance is a property of the whole execution harness, not
only the model. The harness controls workspace access, tool permissions,
intermediate trajectory, approvals, verification, cost/latency and evidence.

## Investigation Summary

The current harness engineering literature and tool ecosystem converges on five
practical points that matter for AgentOps MIS:

1. Evaluate the model-harness pair, not the model alone. Harness-Bench argues
   that task environment, budget, timeout, evaluator and native harness behavior
   must be reported together because execution-layer variation changes success,
   cost, robustness and traceability.
2. Treat agent evaluation as system evaluation. Promptfoo's coding-agent guide
   separates plain LLM baselines from SDK/app-server agents because file access,
   shell access, approval behavior, session state and tool traces change the
   capability being tested.
3. Use traces as improvement data, not decoration. LangChain's harness case
   study and observability guidance point to tracing, self-verification and
   feedback loops as the way to debug agent failure modes at scale.
4. Keep the harness executable, inspectable and stateful. The Code as Agent
   Harness survey frames planning, memory, tool use, verification and
   multi-agent coordination as harness mechanisms that need code-level
   interfaces and state, not only prompts.
5. Separate diagnostic proof from deployment claims. Offline sandboxes and mock
   adapters are valuable regression tools, but product claims need live or
   ledger-backed evidence with clear limits.

For AgentOps MIS, this means the harness is the product boundary where a
customer task becomes governed work: packetized input, scoped execution,
approved side effects, traceable runtime behavior, evaluation, report artifact,
memory candidate and audit receipt.

## Positioning

AgentOps MIS should become the local-first task harness for customer work: it
does not run every model itself, but it owns the task packet, execution gate,
ledger evidence, approval wall, evaluation, artifact, memory review and audit
readback.

## Harness Objects

Every product-grade task harness run must make these objects explicit:

| Object | Purpose |
| --- | --- |
| `work_packet` | Compact machine-readable task, authority, command and evidence contract. |
| `runtime_adapter` | `mock`, `hermes`, `openclaw`, `dify`, `codex`, or future remote worker. |
| `execution_lane` | Async lane with owner, phase, blocker, next command and evidence refs. |
| `sandbox_scope` | Filesystem, network, credential and tool boundary for this run. |
| `approval_checkpoint` | Prepared-action checkpoint for external or high-risk side effects. |
| `trajectory` | Tool/runtime/evaluation/audit evidence, not private chain-of-thought. |
| `scorecard` | Pass/warn/fail rules for completion, quality, cost, latency and safety. |
| `replay_receipt` | Enough IDs, hashes and commands to inspect or rerun safely. |
| `claim_limit` | What this proof can and cannot claim. |

## Product Constraint Register

These constraints are hard product rules for AgentOps MIS harness work:

| Constraint | Rule | Why |
| --- | --- | --- |
| MIS authority | Tasks, runs, approvals, artifacts, memory candidates and audit logs remain MIS authority objects. External harnesses may produce evidence, not replace the ledger. | Prevents a useful runtime/tool from becoming an ungoverned source of truth. |
| Agent interface | Agents use CLI/API/MCP work packets, not browser UI scraping. | Browser pages are for humans; agents need stable machine contracts. |
| Runtime proof | Real Hermes/OpenClaw proof requires confirmed or approved execution plus run/tool/runtime/eval/audit/artifact readback. | Avoids calling a terminal success product evidence when it never entered MIS. |
| Mock boundary | Mock and fixture harnesses are CI/offline fallback only and must be labeled. | Keeps classroom/demo confidence without overstating product readiness. |
| Approval wall | External writes, high-risk tools, privileged scopes and irreversible actions require prepared action hash, checkpoint, approval and exact once resume. | Makes human governance auditable instead of merely ceremonial. |
| Redaction | Store summaries, hashes, ids and safe metadata; never store raw prompts, raw responses, credentials, private messages or full transcripts. | Keeps local-first usefulness without turning MIS into a sensitive transcript sink. |
| Reproducibility | Every product-grade claim needs verification commands, evidence ids and a replay/no-replay rationale. | Lets the operator and customer inspect what actually happened. |
| Async lanes | Slow adapters must not block independent docs, verification, readback or another implementation lane. | Matches real team operation and prevents one stuck worker from stopping delivery. |
| External tools | Promptfoo, Inspect, SWE-bench, Harness, Phoenix, LangSmith, Dify or OpenClaw can be references/connectors, but not vendored or trusted by default. | Allows borrowing proven patterns while preserving local safety and licensing boundaries. |
| Customer clarity | Reports must say whether evidence is real runtime, ledger readback, dry-run, mock fallback or pending approval. | Customers need to know whether work really ran. |

## Work Packet Minimum

The task harness must reject product-grade claims when a work packet lacks:

- `packet_id`
- `packet_kind`
- `packet_version`
- `workspace_id`
- `task_id`
- `agent_id`
- `runtime_adapter`
- `runtime_connector_id`
- `objective_summary`
- `source_refs`
- `allowed_commands`
- `forbidden_actions`
- `required_approvals`
- `required_evidence`
- `verification_commands`
- `redaction_rules`
- `claim_limit`

The packet must be usable by CLI/API/MCP workers without scraping browser UI or
reading the original conversation.

## Execution Phases

AgentOps MIS harness runs use this phase model:

```text
INTAKE
-> SCOPE
-> PLAN
-> RETRIEVE
-> EXECUTE
-> OBSERVE
-> VERIFY
-> RECORD
-> REVIEW
-> REPORT
```

Minimum product-grade evidence:

- INTAKE: task/workspace/agent/runtime ids.
- SCOPE: sandbox, credential and network posture.
- PLAN: Agent Plan id, immutable plan hash, validation result.
- RETRIEVE: scoped knowledge/evidence packet or explicit no-retrieval reason.
- EXECUTE: run id, adapter id, start/end timestamps, live/mock flag.
- OBSERVE: tool calls and runtime events with summaries/hashes only.
- VERIFY: evaluation rows and smoke/build/report evidence.
- RECORD: artifacts, audit rows and replay receipt.
- REVIEW: memory candidates and approvals where applicable.
- REPORT: customer-facing or operator-facing report artifact.

## Real Runtime And Mock Boundary

Mock harness evidence is useful for CI and offline regression checks. It is not
real AI product proof.

Real-runtime proof requires all of:

- local Hermes/OpenClaw/runtime availability;
- explicit `confirm_run` or approved prepared action;
- runtime trust/readiness readback;
- completed run;
- tool call or runtime-event evidence;
- evaluation evidence;
- audit evidence;
- artifact or explicit no-artifact rationale;
- redaction proof for prompt, raw response, token and private transcript
  omission.

Acceptable claim language:

```text
mock_ci_fallback_verified
real_runtime_verified_for_adapter_run_id
summary_only_opaque_runtime
approval_prepared_not_executed
```

Forbidden claim language:

```text
mock evidence proves real AI work
opaque runtime has full internal tool governance
raw prompt/response stored as evidence
browser UI is the agent interface
all external writes are safe without prepared actions
```

## Trajectory Without Private Thought

The harness must record behavior, not hidden reasoning.

Allowed:

- tool name;
- normalized args hash;
- status;
- duration;
- output summary;
- output hash;
- source URI/path when safe;
- runtime event type;
- evaluation result and score;
- audit action and policy decision.

Forbidden:

- raw prompt;
- raw model response;
- chain-of-thought;
- credentials;
- private messages;
- full transcript;
- unredacted customer document contents.

## Scorecard

Each harness run should produce a scorecard with these fields:

| Check | Rule |
| --- | --- |
| `task_completed` | Run ended `completed` or equivalent adapter success. |
| `tool_trace_present` | Tool call or runtime event exists. |
| `eval_passed` | At least one pass evaluation or explicit manual-review status. |
| `approval_satisfied` | Required prepared actions were approved and resumed exactly once. |
| `artifact_recorded` | Artifact/report exists or no-artifact rationale is recorded. |
| `cost_latency_bounded` | Cost/duration within configured threshold or marked warn/fail. |
| `secret_leak_absent` | Secret scan/redaction rules found no leaked token-like values. |
| `memory_reviewable` | Any learned memory is candidate-only until approved. |
| `claim_limit_clear` | Result states real-runtime, mock, opaque, or summary-only boundary. |

## Integration With Current AgentOps MIS

The existing local task harness is the first implementation surface:

```bash
python3 scripts/local_task_harness.py --adapter mock
python3 scripts/local_task_harness.py --adapter hermes
python3 scripts/local_task_harness.py --adapter openclaw --confirm-run
```

The next product slice should add a read-only local harness proof projection
that answers:

- which adapters have fresh proof;
- which run ids prove it;
- which evidence counts are present;
- whether the proof is real runtime or CI/mock fallback;
- which gate is missing when proof is incomplete.

This readback must not call live runtimes. It only reads MIS ledger evidence.

Implemented surface:

```bash
agentops operator local-harness-proof --freshness-hours 72 --limit 8
GET /api/operator/local-harness-proof?freshness_hours=72&limit=8
agentops local readiness
GET /api/local/readiness
```

The readback classifies `mock` as `mock_ci_fallback` and Hermes/OpenClaw as
`real_runtime_ledger_readback` only for returned run ids that have completed
run/tool/evaluation/runtime/audit/artifact/verified-plan-evidence rows.

The readback also exposes a governed launch packet: new proof runs should start
through `agentops workflow customer-worker-task`, while
`scripts/local_task_harness.py` remains a developer fallback. Hermes/OpenClaw
launch commands still require explicit `--confirm-run`.

Local readiness now embeds this proof as `local_harness_proof_readiness`, adds
summary counters to `evidence`, and exposes a non-blocking `local_harness_proof`
gate. This makes harness proof visible in the normal operator readiness flow
without turning it into the stricter customer-worker live acceptance gate.

## OpenClaw/Hermes Product Constraint

OpenClaw and Hermes should run customer or dogfood work through Agent Gateway
task pull/claim/start/writeback, not through ad hoc terminal calls that never
enter MIS.

For product-level dogfood:

```text
MIS task
-> local_task_harness work packet
-> Agent Gateway worker path
-> Hermes/OpenClaw adapter
-> run/tool/runtime/eval/audit/artifact evidence
-> evidence graph/readback
-> report/memory candidate
```

## Async Commander Constraint

The harness must support multiple independent lanes:

- lane id;
- owner runtime;
- task id;
- current phase;
- last evidence id;
- blocker;
- next safe command;
- verification command;
- merge/readiness status.

Waiting for all lanes to finish before merging usable evidence is a harness
failure. A slow adapter lane should not block documentation, verification,
smoke, proof-readback or another independent implementation lane.

## Product Roadmap

1. Keep `scripts/local_task_harness.py` as the minimal local entrypoint.
2. Add read-only `/api/operator/local-harness-proof` and CLI readback.
3. Add isolated CI smoke that verifies mock proof as fallback.
4. Add manual OpenClaw/Hermes dogfood runbook for real-runtime proof.
5. Add scorecard rows to run detail and operator command center.
6. Add remote worker harness mode after scope enforcement and enrollment
   revocation are visible.

## Non-Goals

- Do not vendor Promptfoo, Inspect AI, SWE-bench, Harness, Arize or any external
  harness into the local product in this slice.
- Do not add new model/provider dependencies.
- Do not execute live Hermes/OpenClaw from this spec.
- Do not change database schema from this spec.
- Do not treat Pixel Office as a machine interface for agents.
