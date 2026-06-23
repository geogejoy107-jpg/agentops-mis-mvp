#!/usr/bin/env python3
"""
Run a safe local Agent Gateway demo for a customer task:
build a formal AI knowledge base / Q&A bot.

The script does not upload documents, call Dify/OpenAI/AnythingLLM, or store
credentials. External ingestion is represented as an approval-gated tool call.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


class AgentOpsClient:
    def __init__(self, base_url: str, api_key: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or ""

    def request(self, method: str, path: str, payload: dict | None = None, query: dict | None = None):
        url = f"{self.base_url}{path}"
        if query:
            url = f"{url}?{urlencode(query, doseq=True)}"
        data = None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-AgentOps-Api-Key"] = self.api_key
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=15) as res:
                raw = res.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc

    def get(self, path: str, query: dict | None = None):
        return self.request("GET", path, query=query)

    def post(self, path: str, payload: dict):
        return self.request("POST", path, payload=payload)


def count_rows(client: AgentOpsClient, db_path: Path) -> dict:
    tables = ["agents", "tasks", "runs", "tool_calls", "approvals", "memories", "evaluations", "audit_logs", "runtime_events", "artifacts"]
    if db_path.exists():
        with sqlite3.connect(db_path) as conn:
            return {table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables}

    paths = {
        "agents": "/api/agents",
        "tasks": "/api/tasks",
        "runs": "/api/runs",
        "tool_calls": "/api/tool-calls",
        "approvals": "/api/approvals",
        "memories": "/api/memories",
        "evaluations": "/api/evaluations",
        "audit_logs": "/api/audit",
        "runtime_events": "/api/runtime-events",
        "artifacts": "/api/artifacts",
    }
    counts = {}
    for key, path in paths.items():
        value = client.get(path)
        if isinstance(value, list):
            counts[key] = len(value)
        elif isinstance(value, dict):
            counts[key] = len(value.get(key, []))
        else:
            counts[key] = 0
    return counts


def register_agents(client: AgentOpsClient, workspace_id: str) -> list[dict]:
    agents = [
        ("agt_gw_kb_planner", "Knowledge Base Project Planner", "Project Planner", ["agent_gateway.task", "agent_gateway.audit"]),
        ("agt_gw_doc_cleaner", "Document Cleaning Agent", "Document Cleaner", ["file.read", "file.write", "memory.propose"]),
        ("agt_gw_kb_builder", "Knowledge Base Builder Agent", "Knowledge Base Builder", ["dify.plan", "openai.file_search.plan", "approval.request"]),
        ("agt_gw_qa_evaluator", "Q&A Evaluation Agent", "Q&A Evaluator", ["eval.submit", "citation.check"]),
        ("agt_gw_customer_reporter", "Customer Report Writer Agent", "Customer Report Writer", ["artifact.summarize", "audit.emit"]),
    ]
    registered = []
    for agent_id, name, role, tools in agents:
        registered.append(client.post("/api/agent-gateway/register", {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "description": "AI digital employee for the knowledge-base bot customer demo.",
            "runtime_type": "mock",
            "model_provider": "local",
            "model_name": "agent-gateway-demo",
            "permission_level": "standard",
            "allowed_tools": tools,
            "budget_limit_usd": 3,
        }))
        client.post("/api/agent-gateway/heartbeat", {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "status": "idle",
            "summary": "Ready for customer knowledge-base project demo.",
        })
    return registered


def create_task(client: AgentOpsClient, project_id: str, index: int, task: dict) -> dict:
    task_id = f"tsk_kb_bot_{project_id}_{index:02d}"
    payload = {
        "task_id": task_id,
        "title": task["title"],
        "description": task["description"],
        "requester_id": "usr_founder",
        "owner_agent_id": task["agent_id"],
        "collaborator_agent_ids": task.get("collaborators", []),
        "status": "planned",
        "priority": task.get("priority", "high"),
        "acceptance_criteria": task["acceptance"],
        "risk_level": task.get("risk", "medium"),
        "budget_limit_usd": task.get("budget", 1.0),
    }
    return client.post("/api/tasks", payload)


def create_agent_plan(client: AgentOpsClient, workspace_id: str, task_id: str, task: dict, project_id: str) -> dict:
    risk = task.get("risk", "medium")
    return client.post("/api/agent-gateway/agent-plans", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "agent_id": task["agent_id"],
        "task_understanding": (
            f"Execute KB bot project step for project {project_id}: {task['title']}. "
            "Use summary/hash-only evidence and keep external writes behind approvals."
        ),
        "referenced_specs": [
            "docs/AGENT_GATEWAY_CLI_SPEC.md",
            "docs/API_SPEC.md",
            "docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md",
        ],
        "referenced_memories": [
            "kb_bot_demo_requires_summary_hash_only_evidence",
            "external_knowledge_upload_requires_human_approval",
        ],
        "referenced_bases": [
            "agent_gateway_cli_api_mcp_contract",
            "local_first_customer_delivery_ledger",
        ],
        "proposed_files_to_change": [
            "tasks",
            "runs",
            "tool_calls",
            "evaluations",
            "artifacts",
            "audit_logs",
        ],
        "risk_level": risk,
        "approval_required": risk in {"high", "critical"} or any(tool.get("requires_approval") for tool in task.get("tool_calls", [])),
        "execution_steps": [
            "Claim the customer project task through Agent Gateway.",
            "Record summarized tool evidence without raw documents or credentials.",
            "Submit evaluation, memory candidate, artifact and audit evidence for operator review.",
        ],
        "verification_plan": "Verify task/run/tool/evaluation/artifact/audit evidence through MIS ledger readback.",
        "rollback_plan": "Leave the task blocked with audit evidence; do not perform external writes or store raw customer material.",
        "status": "submitted",
    })


def run_task(client: AgentOpsClient, workspace_id: str, task_id: str, task: dict, project_id: str) -> dict:
    agent_id = task["agent_id"]
    client.post(f"/api/agent-gateway/tasks/{task_id}/claim", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
    })
    plan = create_agent_plan(client, workspace_id, task_id, task, project_id)["agent_plan"]
    plan_id = plan["plan_id"]
    run = client.post("/api/agent-gateway/runs/start", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "runtime_type": "mock",
        "input_summary": task["description"],
        "delegation_id": f"kb-bot-demo:{project_id}:{agent_id}",
    })["run"]
    run_id = run["run_id"]

    approval_id = None
    tool_call_ids = []
    for tool in task.get("tool_calls", []):
        tool_payload = {
            "workspace_id": workspace_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "tool_name": tool["name"],
            "tool_category": tool.get("category", "custom"),
            "risk_level": tool.get("risk", "low"),
            "status": tool.get("status", "completed"),
            "target_resource": tool.get("target_resource"),
            "args": {
                "project_id": project_id,
                "summary_only": True,
                "raw_document_storage": "not_in_mis",
                "credential_storage": "env_or_external_secret_manager_only",
            },
            "result_summary": tool["summary"],
        }
        tool_result = client.post("/api/agent-gateway/tool-calls", tool_payload)["tool_call"]
        tool_call_ids.append(tool_result["tool_call_id"])
        if tool.get("requires_approval"):
            approval = client.post("/api/agent-gateway/approvals/request", {
                "workspace_id": workspace_id,
                "task_id": task_id,
                "run_id": run_id,
                "tool_call_id": tool_result["tool_call_id"],
                "requested_by_agent_id": agent_id,
                "reason": tool["approval_reason"],
            })["approval"]
            approval_id = approval["approval_id"]

    client.post(f"/api/agent-gateway/runs/{run_id}/heartbeat", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "status": "completed",
        "duration_ms": task.get("duration_ms", 42000),
        "output_summary": task["output_summary"],
        "output_tokens": task.get("output_tokens", 520),
        "cost_usd": task.get("cost_usd", 0.0),
    })
    evaluation = client.post("/api/agent-gateway/evaluations/submit", {
        "workspace_id": workspace_id,
        "run_id": run_id,
        "task_id": task_id,
        "agent_id": agent_id,
        "evaluator_type": "rule",
        "score": task.get("score", 0.9),
        "pass_fail": "pass",
        "rubric": task["rubric"],
        "notes": task["eval_notes"],
    })["evaluation"]
    memory = client.post("/api/agent-gateway/memories/propose", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "memory_type": task.get("memory_type", "artifact_summary"),
        "canonical_text": task["memory"],
        "source_ref": f"run://{run_id}",
        "access_tags": ["kb-bot-demo", "customer-task", "review"],
        "confidence": 0.78,
    })["memory"]
    artifact_id = None
    if task.get("artifact"):
        artifact = task["artifact"]
        summary = artifact["summary"].format(project_id=project_id)
        artifact_type = "customer_delivery_report"
        artifact_title = artifact["title"]
        artifact_id = f"art_kb_bot_delivery_{project_id}"
        artifact_uri = f"agentops://kb-bot-demo/{project_id}/delivery-summary"
    else:
        summary = task["output_summary"]
        artifact_type = "workflow_step_summary"
        artifact_title = f"KB bot step summary: {task['title']}"
        artifact_id = f"art_kb_bot_step_{project_id}_{task_id.rsplit('_', 1)[-1]}"
        artifact_uri = f"agentops://kb-bot-demo/{project_id}/steps/{task_id}"
    content_hash = hashlib.sha256(summary.encode("utf-8")).hexdigest()
    recorded = client.post("/api/agent-gateway/artifacts", {
        "workspace_id": workspace_id,
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "title": artifact_title,
        "uri": artifact_uri,
        "summary": summary,
        "content_hash": content_hash,
    })["artifact"]
    artifact_id = recorded["artifact_id"]
    client.post("/api/agent-gateway/audit", {
        "workspace_id": workspace_id,
        "agent_id": agent_id,
        "action": "customer_project.kb_bot_step_completed",
        "entity_type": "runs",
        "entity_id": run_id,
        "run_id": run_id,
        "task_id": task_id,
        "metadata": {
            "project_id": project_id,
            "approval_id": approval_id,
            "artifact_id": artifact_id,
            "plan_id": plan_id,
            "summary": task["output_summary"],
        },
    })

    manifest_id = None
    manifest_status = None
    manifest_pass = None
    if all(tool.get("status", "completed") == "completed" for tool in task.get("tool_calls", [])):
        manifest_payload = client.post("/api/agent-gateway/plan-evidence-manifests", {
            "workspace_id": workspace_id,
            "plan_id": plan_id,
            "task_id": task_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "mismatch_policy": "block",
            "tool_call_ids": tool_call_ids,
            "evaluation_ids": [evaluation["evaluation_id"]],
            "artifact_ids": [artifact_id],
        })
        manifest = manifest_payload["manifest"]
        manifest_id = manifest["manifest_id"]
        manifest_status = manifest.get("status")
        manifest_pass = (manifest_payload.get("verification") or {}).get("pass")
    return {
        "task_id": task_id,
        "run_id": run_id,
        "agent_id": agent_id,
        "plan_id": plan_id,
        "plan_evidence_manifest_id": manifest_id,
        "plan_evidence_status": manifest_status,
        "plan_evidence_pass": manifest_pass,
        "approval_id": approval_id,
        "artifact_id": artifact_id,
        "evaluation_id": evaluation["evaluation_id"],
        "memory_id": memory["memory_id"],
    }


def demo_tasks() -> list[dict]:
    return [
        {
            "agent_id": "agt_gw_kb_planner",
            "title": "AI 知识库/问答机器人项目拆解",
            "description": "确认客户目标、资料来源、交付边界和审批策略，把项目拆成可执行 AI 团队任务。",
            "acceptance": "交付角色分工、阶段计划、审批边界和验收清单。",
            "tool_calls": [
                {"name": "agent_gateway.task.decompose", "category": "custom", "risk": "low", "summary": "Created safe project decomposition for the knowledge-base bot."},
            ],
            "output_summary": "项目拆解完成：资料清洗、知识库选型、分块/Embedding 设计、问答评估、交付报告五段推进。",
            "rubric": {"decomposition": True, "approval_boundaries": True, "customer_value": True},
            "eval_notes": "Pass: plan is actionable and approval boundaries are explicit.",
            "memory": "知识库机器人项目必须把外部上传和凭证使用作为审批动作，MIS 只保存摘要、hash 和审计证据。",
            "memory_type": "policy",
        },
        {
            "agent_id": "agt_gw_doc_cleaner",
            "title": "原始资料清洗与格式标准",
            "description": "定义 Markdown/PDF/DOCX 清洗规则、元数据字段和隐私处理，不把原文全文写入 MIS。",
            "acceptance": "输出清洗规则、元数据 schema、脱敏策略和样例摘要。",
            "tool_calls": [
                {"name": "file.plan_cleaning", "category": "file", "risk": "low", "summary": "Planned Markdown/PDF/DOCX cleaning pipeline with metadata fields."},
            ],
            "output_summary": "清洗标准完成：标题、来源、日期、权限标签、chunk hint；PII/凭证脱敏；MIS 只记录 200 字摘要和 hash。",
            "rubric": {"privacy": True, "format_schema": True, "raw_text_omitted": True},
            "eval_notes": "Pass: raw documents are not persisted in MIS.",
            "memory": "资料清洗产物应保留 source_id、title、source_uri_hash、access_tag、chunk_hint，原文留在客户授权资料库。",
            "memory_type": "sop",
        },
        {
            "agent_id": "agt_gw_kb_builder",
            "title": "Dify / OpenAI File Search / AnythingLLM 选型与连接计划",
            "description": "比较三种知识库方案，设计 connector trust registry 和外部上传审批。",
            "acceptance": "输出选型建议、连接配置字段、审批门槛和回滚策略。",
            "risk": "high",
            "tool_calls": [
                {
                    "name": "openai.file_search.upload",
                    "category": "custom",
                    "risk": "high",
                    "status": "waiting_approval",
                    "target_resource": "openai://file-search/vector-store",
                    "summary": "Prepared external upload plan only; no file was uploaded.",
                    "requires_approval": True,
                    "approval_reason": "External knowledge-base upload may move customer documents to OpenAI/Dify/AnythingLLM and must be approved by a human.",
                },
            ],
            "output_summary": "选型完成：Dify 适合低代码工作流；OpenAI File Search 适合开发者 API；AnythingLLM 适合私有/自托管。上传动作已进入审批。",
            "rubric": {"connector_choice": True, "approval_required": True, "no_external_write": True},
            "eval_notes": "Pass: connector plan is complete; real upload is blocked behind pending approval.",
            "memory": "Dify/OpenAI File Search/AnythingLLM 上传属于外部写入，必须有 pending approval 或 approved decision 才能执行。",
            "memory_type": "risk",
            "score": 0.88,
        },
        {
            "agent_id": "agt_gw_kb_builder",
            "title": "分块、Embedding 与向量库设计",
            "description": "设计 chunk size、overlap、metadata filter、citation mapping 和检索流程。",
            "acceptance": "输出分块策略、向量元数据、召回/重排流程和引用来源策略。",
            "tool_calls": [
                {"name": "retrieval.design", "category": "custom", "risk": "low", "summary": "Designed chunking, embedding metadata and citation mapping."},
            ],
            "output_summary": "推荐 600-900 tokens chunk、80-120 overlap；metadata 包含 source_id/page/section/access_tag；回答必须返回引用。",
            "rubric": {"chunking": True, "metadata": True, "citations": True},
            "eval_notes": "Pass: retrieval plan is clear enough for Dify/OpenAI/AnythingLLM implementation.",
            "memory": "知识库问答默认要求 answer + citations + confidence + missing_context，不允许无来源断言。",
            "memory_type": "sop",
        },
        {
            "agent_id": "agt_gw_qa_evaluator",
            "title": "问答机器人质量评估",
            "description": "定义评估集、引用检查、幻觉检查、权限标签检查和失败样例。",
            "acceptance": "输出评估 rubric 和至少 5 类测试问题。",
            "tool_calls": [
                {"name": "eval.rubric.design", "category": "custom", "risk": "low", "summary": "Created QA rubric with citation, refusal and permission checks."},
            ],
            "output_summary": "评估 rubric 完成：正确性、引用覆盖、权限过滤、拒答边界、上下文不足提示；建议每次上线前跑 20 题 smoke。",
            "rubric": {"accuracy": True, "citation_check": True, "permission_check": True},
            "eval_notes": "Pass: rubric covers quality and safety gates.",
            "memory": "知识库机器人上线前必须跑引用覆盖率、权限过滤、拒答边界和上下文不足测试。",
            "memory_type": "sop",
        },
        {
            "agent_id": "agt_gw_customer_reporter",
            "title": "客户交付摘要与下一步",
            "description": "汇总客户可读交付：架构、工具选择、实施步骤、审批事项和风险清单。",
            "acceptance": "输出 1 页交付摘要，能用于课堂 demo 讲解。",
            "tool_calls": [
                {"name": "artifact.delivery_summary", "category": "custom", "risk": "low", "summary": "Prepared customer-facing delivery summary."},
            ],
            "output_summary": "交付摘要完成：本地 MIS 已管理任务、运行、工具、审批、评估、记忆和审计；外部知识库写入等待人工批准。",
            "artifact": {
                "title": "AI 知识库/问答机器人客户交付摘要",
                "summary": "项目 {project_id} 已完成本地 MIS 闭环：AI 团队拆解需求、设计资料清洗规则、比较 Dify/OpenAI File Search/AnythingLLM、规划 chunking/embedding/citation、建立质量评估 rubric，并把外部上传保留为 pending approval。MIS 账本包含 tasks、runs、tool_calls、approval、evaluations、memory candidates、audit logs；未保存原始资料、凭证或完整私聊 transcript。",
            },
            "rubric": {"customer_readable": True, "ledger_links": True, "next_steps": True},
            "eval_notes": "Pass: summary is demo-ready and points to MIS evidence.",
            "memory": "客户交付报告应该展示 MIS 账本证据：任务、运行、工具调用、审批、评估、审计，而不只是最终文本。",
            "memory_type": "artifact_summary",
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local AI knowledge-base bot customer demo through Agent Gateway.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--api-key", default=os.environ.get("AGENTOPS_API_KEY", ""))
    parser.add_argument("--workspace-id", default=os.environ.get("AGENTOPS_WORKSPACE_ID", "local-demo"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH", "agentops_mis.db"))
    args = parser.parse_args()

    client = AgentOpsClient(args.base_url, args.api_key)
    db_path = Path(args.db_path)
    project_id = now_stamp()
    before = count_rows(client, db_path)
    register_agents(client, args.workspace_id)

    results = []
    for index, task in enumerate(demo_tasks(), start=1):
        created = create_task(client, project_id, index, task)
        results.append(run_task(client, args.workspace_id, created["task_id"], task, project_id))

    after = count_rows(client, db_path)
    output = {
        "project_id": project_id,
        "scenario": "formal_ai_knowledge_base_qa_bot",
        "safe_defaults": {
            "external_upload_performed": False,
            "credentials_stored": False,
            "raw_documents_stored": False,
            "external_upload_requires_approval": True,
        },
        "before_counts": before,
        "after_counts": after,
        "created_or_updated": {key: after.get(key, 0) - before.get(key, 0) for key in after},
        "results": results,
        "open_pages": {
            "pixel_office": f"{args.base_url.replace(':8787', ':19001')}/workspace/pixel-office",
            "tasks": f"{args.base_url.replace(':8787', ':19001')}/workspace/tasks",
            "runs": f"{args.base_url.replace(':8787', ':19001')}/admin/runs",
            "approvals": f"{args.base_url.replace(':8787', ':19001')}/workspace/approvals",
            "evaluations": f"{args.base_url.replace(':8787', ':19001')}/admin/evaluations",
            "audit": f"{args.base_url.replace(':8787', ':19001')}/admin/audit",
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
