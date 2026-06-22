# AgentOps MIS Open Source Base Index v1.1

> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Product baseline: `codex/agent-gateway-kb-demo` @ `3fe3c6376f914ecd275786978d8d1e6df3037f98`  
> Research branch: `research-osbi-v1-1-current-head`  
> Verified: 2026-06-22  
> Registry entries: 66  
> Canonical: false — research and integration guidance, not automatic approval

## Executive conclusion

AgentOps MIS should be the **first-party control plane and evidence ledger** above replaceable runtimes. Open source
should be adopted aggressively for protocols, retrieval, coding workspaces, CI, security scanning, observability,
sandboxes, experiment tracking and compute scheduling. It must not own workspace, identity, Task, AgentPlan, Run,
ToolCall, PreparedAction, Approval, Artifact, Evaluation, reviewed Memory, Audit or customer Delivery.

The final research baseline is the current `READY_TO_MERGE` product head. CI, Agent Plan hard gates, PreparedAction
Approval Wall, Knowledge ACL/provenance, SQLite reliability, Repo Map, Local Coding Project Template, Command Center
BFF and Runtime Capability Manifest are no longer treated as missing. P1-05 module splitting remains in progress;
P1-06 retrieval evaluation is the next prepared productization lane.

## Decision vocabulary

- `ADOPT_NOW`: use now as a tool/standard, or keep an implemented native adaptation.
- `PILOT`: bounded proof required before product commitment.
- `REFERENCE`: borrow ideas without making the project a dependency or authority.
- `WATCH`: useful later; current cost/maturity does not justify a PoC.
- `REJECT`: do not start as a separate integration.
- `integration_status` is independent from the recommendation.

## Current first-party baseline

- `method_block_v0` — **IMPLEMENTED**: PROJECT_SPEC.md, AGENT_WORKFLOW.md, agent plan and knowledge APIs
- `plan_integrity_and_run_gate` — **IMPLEMENTED_KEEP_GREEN**: P0-01/P0-02; agent_plan_integrity_smoke.py and run_start_plan_gate_smoke.py
- `prepared_action_approval_wall` — **IMPLEMENTED_KEEP_GREEN**: P0-04; prepared-action and external-side-effect smokes
- `knowledge_acl_and_provenance` — **IMPLEMENTED_KEEP_GREEN**: P0-07; knowledge scope and retrieval-quality smokes
- `sqlite_reliability` — **IMPLEMENTED_KEEP_GREEN**: P0-08; WAL/pragmas/concurrency smokes
- `github_actions_ci` — **IMPLEMENTED_KEEP_GREEN**: PR #1 exact-head CI success at 3fe3c637...
- `repo_map` — **IMPLEMENTED**: P1-01 Done
- `local_coding_project_template` — **IMPLEMENTED**: P1-02 Done
- `command_center_bff` — **IMPLEMENTED**: P1-03 Done
- `runtime_capability_manifest` — **IMPLEMENTED**: P1-04 Done
- `module_strangler_split` — **IN_PROGRESS**: P1-05
- `knowledge_chunking_hybrid_eval` — **READY**: P1-06

## Recommended sequencing

### P1 — immediately after the v1.5 merge

1. P1-06 FTS5 retrieval benchmark, heading-aware chunking, bilingual Recall@5/MRR/p95.
2. Complete OpenAPI contracts; prototype a scoped MCP server over Agent Gateway.
3. Formalize Agent Skills metadata, hashes, source/license and allowed-tool trust.
4. Pilot promptfoo for deterministic agent/RAG regression and red-team cases.
5. Compare Syft/Gitleaks/Trivy against existing custom release gates.
6. Design OpenTelemetry/OpenInference export without raw prompt/response retention.

### P2 — differentiation

1. JiuwenSwarm dry-run adapter with parent/child MIS evidence.
2. Research Lab template using MLflow, DVC and DCGM metrics.
3. A2A bridge for approved remote agents.
4. gVisor sandbox PoC for controlled customer or hosted execution.
5. Graphiti or hybrid vector retrieval only after P1-06 evidence.

### P3 — ecosystem

Marketplace, billing/reputation, hosted multi-tenancy, microVM isolation, signed releases, large-scale distributed
Swarm and research compute.

## Full registry

| Base | Category | Decision | Status | Phase | Adoption |
|---|---|---|---|---|---|
| [GitHub Spec Kit](https://github.com/github/spec-kit) | `harness_method` | `REFERENCE` | `NOT_INTEGRATED` | `P1` | `method_adaptation` |
| [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) | `harness_loop` | `PILOT` | `NOT_INTEGRATED` | `P2` | `runtime_adapter_poc` |
| [PydanticAI](https://github.com/pydantic/pydantic-ai) | `harness_loop` | `PILOT` | `NOT_INTEGRATED` | `P1/P2` | `reference_adapter` |
| [LangGraph](https://github.com/langchain-ai/langgraph) | `harness_loop` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `optional_runtime_adapter` |
| [CrewAI](https://github.com/crewAIInc/crewAI) | `harness_swarm` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `role_workflow_pattern` |
| [Microsoft AutoGen](https://github.com/microsoft/autogen) | `harness_swarm` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `handoff_team_pattern` |
| [JiuwenSwarm](https://github.com/openJiuwen-ai/jiuwenswarm) | `distributed_swarm` | `PILOT` | `NOT_INTEGRATED` | `P2` | `staged_adapter_poc` |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | `coding_harness` | `REFERENCE` | `NOT_INTEGRATED` | `P1/P2` | `agent_computer_interface_pattern` |
| [OpenHands](https://github.com/All-Hands-AI/OpenHands) | `coding_runtime` | `PILOT` | `NOT_INTEGRATED` | `P2` | `sandbox_workspace_adapter` |
| [Hugging Face smolagents](https://github.com/huggingface/smolagents) | `harness_loop` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `lightweight_agent_pattern` |
| [Git worktree](https://git-scm.com/docs/git-worktree) | `coding_workspace` | `ADOPT_NOW` | `IMPLEMENTED` | `implemented` | `direct_tool` |
| [Agent Skills specification](https://agentskills.io/specification) | `skill_protocol` | `ADOPT_NOW` | `PARTIAL` | `P1` | `skill_package_standard` |
| [Model Context Protocol](https://modelcontextprotocol.io/specification) | `protocol` | `ADOPT_NOW` | `PROPOSED` | `P1/P2` | `agent_gateway_tool_resource_interface` |
| [A2A Protocol](https://a2a-protocol.org/latest/specification/) | `protocol` | `PILOT` | `NOT_INTEGRATED` | `P2` | `remote_agent_interop_adapter` |
| [Agent Communication Protocol (ACP)](https://github.com/i-am-bee/acp) | `protocol` | `REJECT` | `SUPERSEDED` | `none` | `none` |
| [OpenAPI Specification](https://github.com/OAI/OpenAPI-Specification) | `protocol` | `ADOPT_NOW` | `PARTIAL` | `P1` | `api_contract_generation` |
| [AsyncAPI Specification](https://github.com/asyncapi/spec) | `protocol` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `event_contract_reference` |
| [CloudEvents](https://github.com/cloudevents/spec) | `protocol` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `normalized_event_envelope` |
| [SQLite FTS5](https://sqlite.org/fts5.html) | `knowledge_search` | `ADOPT_NOW` | `IMPLEMENTED` | `implemented` | `direct_tool` |
| [Aider Repo Map](https://aider.chat/docs/repomap.html) | `repo_localization` | `REFERENCE` | `IMPLEMENTED` | `implemented` | `native_method_adaptation` |
| [Anthropic Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval) | `knowledge_search` | `REFERENCE` | `NOT_INTEGRATED` | `P1` | `retrieval_experiment_pattern` |
| [pgvector](https://github.com/pgvector/pgvector) | `vector_store` | `WATCH` | `NOT_INTEGRATED` | `P2` | `future_postgres_extension` |
| [Qdrant](https://github.com/qdrant/qdrant) | `vector_store` | `WATCH` | `NOT_INTEGRATED` | `P2` | `future_sidecar` |
| [Microsoft GraphRAG](https://github.com/microsoft/graphrag) | `knowledge_graph` | `WATCH` | `NOT_INTEGRATED` | `P2/P3` | `offline_research_pipeline` |
| [Graphiti](https://github.com/getzep/graphiti) | `temporal_knowledge_graph` | `PILOT` | `NOT_INTEGRATED` | `P2` | `temporal_memory_sidecar` |
| [Mem0](https://github.com/mem0ai/mem0) | `agent_memory` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `memory_pattern_only` |
| [Letta](https://github.com/letta-ai/letta) | `agent_memory` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `stateful_agent_pattern` |
| [Tantivy](https://github.com/quickwit-oss/tantivy) | `search_engine` | `WATCH` | `NOT_INTEGRATED` | `P3` | `future_embedded_search` |
| [Open Policy Agent](https://www.openpolicyagent.org/docs) | `policy_engine` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `policy_vocabulary_and_future_sidecar` |
| [Cedar Policy Language](https://docs.cedarpolicy.com/) | `policy_engine` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `authorization_model_reference` |
| [OpenFGA](https://github.com/openfga/openfga) | `authorization` | `WATCH` | `NOT_INTEGRATED` | `P3` | `future_relationship_authz` |
| [gVisor](https://gvisor.dev/docs/) | `sandbox` | `PILOT` | `NOT_INTEGRATED` | `P2/P3` | `container_sandbox` |
| [Firecracker](https://github.com/firecracker-microvm/firecracker) | `sandbox` | `WATCH` | `NOT_INTEGRATED` | `P3` | `microvm_sandbox` |
| [SOPS](https://github.com/getsops/sops) | `secret_management` | `PILOT` | `NOT_INTEGRATED` | `P2` | `encrypted_config_tool` |
| [Gitleaks](https://github.com/gitleaks/gitleaks) | `secret_scan` | `ADOPT_NOW` | `NOT_INTEGRATED` | `P1` | `ci_scanner` |
| [Trivy](https://github.com/aquasecurity/trivy) | `security_scan` | `ADOPT_NOW` | `NOT_INTEGRATED` | `P1/P2` | `ci_scanner` |
| [Syft](https://github.com/anchore/syft) | `sbom` | `ADOPT_NOW` | `NOT_INTEGRATED` | `P1` | `sbom_generator` |
| [Cosign](https://github.com/sigstore/cosign) | `artifact_signing` | `WATCH` | `NOT_INTEGRATED` | `P3` | `release_signing` |
| [OpenTelemetry](https://opentelemetry.io/docs/) | `observability` | `ADOPT_NOW` | `PARTIAL` | `P1/P2` | `telemetry_standard` |
| [OpenInference](https://github.com/Arize-ai/openinference) | `observability` | `PILOT` | `NOT_INTEGRATED` | `P2` | `otel_ai_semantic_conventions` |
| [Langfuse](https://github.com/langfuse/langfuse) | `observability_eval` | `PILOT` | `NOT_INTEGRATED` | `P2` | `optional_self_hosted_sidecar` |
| [promptfoo](https://github.com/promptfoo/promptfoo) | `evaluation_security` | `ADOPT_NOW` | `NOT_INTEGRATED` | `P1/P2` | `ci_eval_and_redteam` |
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | `evaluation` | `PILOT` | `NOT_INTEGRATED` | `P2` | `research_eval_harness` |
| [Ragas](https://github.com/explodinggradients/ragas) | `retrieval_evaluation` | `REFERENCE` | `NOT_INTEGRATED` | `P1/P2` | `retrieval_eval_library` |
| [DeepEval](https://github.com/confident-ai/deepeval) | `evaluation` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `test_library` |
| [Arize Phoenix](https://github.com/Arize-ai/phoenix) | `observability_eval` | `WATCH` | `NOT_INTEGRATED` | `P2` | `optional_sidecar` |
| [TanStack Query](https://github.com/TanStack/query) | `frontend_performance` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `server_state_cache_pattern` |
| [TanStack Virtual](https://github.com/TanStack/virtual) | `frontend_performance` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `large_list_virtualization` |
| [Vite](https://github.com/vitejs/vite) | `frontend_build` | `ADOPT_NOW` | `IMPLEMENTED` | `implemented` | `direct_tool` |
| [SQLite WAL](https://sqlite.org/wal.html) | `storage_performance` | `ADOPT_NOW` | `IMPLEMENTED` | `implemented` | `direct_tool` |
| [Server-Sent Events](https://html.spec.whatwg.org/multipage/server-sent-events.html) | `ux_streaming` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `progress_stream_pattern` |
| [Prometheus](https://github.com/prometheus/prometheus) | `metrics` | `PILOT` | `NOT_INTEGRATED` | `P2/P3` | `metrics_sidecar` |
| [MLflow](https://github.com/mlflow/mlflow) | `research_lab` | `PILOT` | `NOT_INTEGRATED` | `P2` | `experiment_tracking_adapter` |
| [DVC](https://github.com/treeverse/dvc) | `research_lab` | `PILOT` | `NOT_INTEGRATED` | `P2` | `dataset_model_version_adapter` |
| [Ray](https://github.com/ray-project/ray) | `research_compute` | `PILOT` | `NOT_INTEGRATED` | `P2/P3` | `distributed_job_adapter` |
| [SkyPilot](https://github.com/skypilot-org/skypilot) | `research_compute` | `PILOT` | `NOT_INTEGRATED` | `P2/P3` | `infrastructure_job_adapter` |
| [Slurm](https://slurm.schedmd.com/overview.html) | `research_compute` | `REFERENCE` | `NOT_INTEGRATED` | `P2/P3` | `hpc_scheduler_adapter` |
| [NVIDIA DCGM Exporter](https://github.com/NVIDIA/dcgm-exporter) | `gpu_observability` | `ADOPT_NOW` | `NOT_INTEGRATED` | `P2` | `gpu_metrics_adapter` |
| [Optuna](https://github.com/optuna/optuna) | `research_optimization` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `hyperparameter_study_adapter` |
| [Hydra](https://github.com/facebookresearch/hydra) | `research_configuration` | `REFERENCE` | `NOT_INTEGRATED` | `P2` | `config_composition_pattern` |
| [JupyterHub](https://github.com/jupyterhub/jupyterhub) | `research_workspace` | `REFERENCE` | `NOT_INTEGRATED` | `P2/P3` | `multi_user_notebook_sidecar` |
| [OpenLineage](https://github.com/OpenLineage/OpenLineage) | `research_provenance` | `WATCH` | `NOT_INTEGRATED` | `P3` | `lineage_event_reference` |
| [SPDX](https://spdx.dev/) | `license_provenance` | `ADOPT_NOW` | `PARTIAL` | `P1` | `sbom_and_license_identifier_standard` |
| [CycloneDX](https://cyclonedx.org/) | `license_provenance` | `REFERENCE` | `NOT_INTEGRATED` | `P1/P2` | `alternative_sbom_format` |
| [OpenSSF Scorecard](https://github.com/ossf/scorecard) | `supply_chain` | `PILOT` | `NOT_INTEGRATED` | `P2` | `upstream_risk_signal` |
| [SLSA](https://slsa.dev/spec/v1.2/) | `supply_chain` | `REFERENCE` | `NOT_INTEGRATED` | `P2/P3` | `release_provenance_model` |

## Architecture mapping

```text
Human Workspace / Command Center / Review Queue
                     │
            Agent Gateway CLI/API/MCP
                     │
 Native MIS authority, permissions, evidence and approval
                     │
 HarnessAdapter / RuntimeAdapter / ProtocolBridge
                     │
Codex | Hermes | OpenClaw | JiuwenSwarm PoC | Research compute
                     │
Sandbox | tools | models | MLflow/DVC | GPU metrics
```

## Non-negotiable gates

- Every base has source, date, license/provenance, recommendation and actual integration status.
- Recommendation never implies implementation.
- Every adapter declares filesystem, shell, network, Git, secret, external-write, trust and observability capability.
- A status change is not execution evidence.
- No Agent self-approves high-risk work or promotes its own candidate memory.
- External writes use PreparedAction, approval, idempotency and execute-once evidence.
- Raw secrets, customer content, private transcripts and model prompts/responses stay outside MIS by default.
- MCP/A2A/framework state maps into MIS; it never becomes the canonical ledger.
- Current supervised collaboration is not marketed as distributed Swarm.
- JiuwenSwarm remains `PILOT / NOT_INTEGRATED` until adapter code and tests exist.

## Evidence companion

`docs/research/evidence/OSBI_V1_1_EVIDENCE_COMPENDIUM.md` contains R1–R11 findings and the MIS lifecycle crosswalk.
The machine-readable source is `docs/research/OPEN_SOURCE_BASE_REGISTRY_V1_1.yaml`.
