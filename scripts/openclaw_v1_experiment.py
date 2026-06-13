#!/usr/bin/env python3
"""
Run the AgentOps MIS v1 OpenClaw experiment.

This script intentionally records only operational metadata: model names,
durations, token counts, cron/job counts, and safe file paths. It does not read
credentials, message transcripts, or full session contents.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sqlite3
import subprocess
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "agentops_mis.db"
OUTPUT_PATH = ROOT / "outputs" / "V1_OPENCLAW_EXPERIMENT.md"
OPENCLAW_HOME = Path.home() / ".openclaw"
OPENCLAW_BIN = Path("/opt/homebrew/bin/openclaw")


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def stable_hash(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def audit(conn, actor_type, actor_id, action, entity_type, entity_id, before=None, after=None, metadata=None):
    conn.execute(
        """INSERT INTO audit_logs(audit_id, actor_type, actor_id, action, entity_type, entity_id, before_hash, after_hash, metadata_json, tamper_chain_hash, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            new_id("aud"),
            actor_type,
            actor_id,
            action,
            entity_type,
            entity_id,
            stable_hash(before) if before is not None else None,
            stable_hash(after) if after is not None else None,
            json.dumps(metadata or {}, ensure_ascii=False),
            stable_hash({"entity_type": entity_type, "entity_id": entity_id, "after": after, "at": now_iso()}),
            now_iso(),
        ),
    )


def upsert_agent(conn, row):
    before = conn.execute("SELECT * FROM agents WHERE agent_id=?", (row["agent_id"],)).fetchone()
    if before:
        conn.execute(
            """UPDATE agents
            SET name=:name, role=:role, description=:description, runtime_type=:runtime_type,
                model_provider=:model_provider, model_name=:model_name, status=:status,
                permission_level=:permission_level, allowed_tools=:allowed_tools,
                budget_limit_usd=:budget_limit_usd, owner_user_id=:owner_user_id, updated_at=:updated_at
            WHERE agent_id=:agent_id""",
            row,
        )
        action = "agent.update"
    else:
        conn.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)""",
            row,
        )
        action = "agent.create"
    audit(conn, "system", "openclaw-v1-experiment", action, "agents", row["agent_id"], dict(before) if before else None, row)


def upsert_task(conn, row):
    before = conn.execute("SELECT * FROM tasks WHERE task_id=?", (row["task_id"],)).fetchone()
    if before:
        conn.execute(
            """UPDATE tasks
            SET title=:title, description=:description, requester_id=:requester_id,
                owner_agent_id=:owner_agent_id, collaborator_agent_ids=:collaborator_agent_ids,
                status=:status, priority=:priority, due_date=:due_date,
                acceptance_criteria=:acceptance_criteria, risk_level=:risk_level,
                budget_limit_usd=:budget_limit_usd, updated_at=:updated_at
            WHERE task_id=:task_id""",
            row,
        )
        action = "task.update"
    else:
        conn.execute(
            """INSERT INTO tasks(task_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
            VALUES(:task_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)""",
            row,
        )
        action = "task.create"
    audit(conn, "system", "openclaw-v1-experiment", action, "tasks", row["task_id"], dict(before) if before else None, row)


def safe_openclaw_snapshot():
    config = read_json(OPENCLAW_HOME / "openclaw.json", {})
    jobs = read_json(OPENCLAW_HOME / "cron" / "jobs.json", {}).get("jobs", [])
    subagent_runs = read_json(OPENCLAW_HOME / "subagents" / "runs.json", {})

    defaults = config.get("agents", {}).get("defaults", {})
    model = defaults.get("model", {}).get("primary", "unknown")
    enabled_jobs = [job for job in jobs if job.get("enabled")]
    if isinstance(subagent_runs, dict) and isinstance(subagent_runs.get("runs"), list):
        subagent_count = len(subagent_runs["runs"])
    elif isinstance(subagent_runs, list):
        subagent_count = len(subagent_runs)
    else:
        subagent_count = 0

    return {
        "model": model,
        "thinking_default": defaults.get("thinkingDefault"),
        "max_concurrent": defaults.get("maxConcurrent"),
        "subagents_max_concurrent": defaults.get("subagents", {}).get("maxConcurrent"),
        "sandbox_mode": defaults.get("sandbox", {}).get("mode"),
        "workspace": defaults.get("workspace"),
        "cron_jobs_total": len(jobs),
        "cron_jobs_enabled": len(enabled_jobs),
        "enabled_cron_names": [job.get("name") for job in enabled_jobs],
        "subagent_runs_count": subagent_count,
        "safe_sources": [
            str(OPENCLAW_HOME / "openclaw.json"),
            str(OPENCLAW_HOME / "cron" / "jobs.json"),
            str(OPENCLAW_HOME / "subagents" / "runs.json"),
        ],
    }


def run_live_probe(skip: bool):
    if skip:
        return {"ok": False, "skipped": True, "summary": "skipped"}
    if not OPENCLAW_BIN.exists():
        return {"ok": False, "error": f"missing {OPENCLAW_BIN}"}
    cmd = [
        str(OPENCLAW_BIN),
        "agent",
        "--agent",
        "main",
        "-m",
        "请只回复 OPENCLAW_MIS_V1_OK",
        "--timeout",
        "180",
        "--json",
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=210)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    result = payload.get("result", {})
    meta = result.get("meta", {})
    agent_meta = meta.get("agentMeta", {})
    visible = meta.get("finalAssistantVisibleText") or result.get("payloads", [{}])[0].get("text")
    return {
        "ok": proc.returncode == 0 and visible == "OPENCLAW_MIS_V1_OK",
        "returncode": proc.returncode,
        "run_id": payload.get("runId"),
        "status": payload.get("status"),
        "summary": payload.get("summary"),
        "visible_text": visible,
        "duration_ms": meta.get("durationMs"),
        "provider": agent_meta.get("provider"),
        "model": agent_meta.get("model"),
        "session_id": agent_meta.get("sessionId"),
        "input_tokens": agent_meta.get("usage", {}).get("input", 0),
        "output_tokens": agent_meta.get("usage", {}).get("output", 0),
        "total_tokens": agent_meta.get("usage", {}).get("total", 0),
        "fallback_used": meta.get("executionTrace", {}).get("fallbackUsed"),
        "delivery_succeeded": result.get("deliverySucceeded"),
        "stderr_tail": proc.stderr[-1000:] if proc.stderr else "",
    }


def insert_experiment(conn, snapshot, probe):
    at = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    created = now_iso()
    main_agent_id = "agt_openclaw_main"
    subagent_pool_id = "agt_openclaw_subagents"
    task_id = "tsk_v1_openclaw_observability"
    run_id = f"run_v1_openclaw_probe_{at}"

    model_provider, _, model_name = (probe.get("provider") or "openclaw").partition("/")
    if not model_name:
        model_name = probe.get("model") or snapshot["model"]

    upsert_agent(
        conn,
        {
            "agent_id": main_agent_id,
            "name": "OpenClaw Main Agent",
            "role": "Runtime Orchestrator",
            "description": "Live OpenClaw main agent observed by AgentOps MIS v1.",
            "runtime_type": "openclaw",
            "model_provider": probe.get("provider") or "openclaw",
            "model_name": probe.get("model") or snapshot["model"],
            "status": "idle" if probe.get("ok") else "error",
            "permission_level": "manager",
            "allowed_tools": json.dumps(["openclaw.agent", "config.read", "cron.read", "subagents.read"], ensure_ascii=False),
            "budget_limit_usd": 20.0,
            "owner_user_id": "usr_founder",
            "created_at": created,
            "updated_at": created,
        },
    )
    upsert_agent(
        conn,
        {
            "agent_id": subagent_pool_id,
            "name": "OpenClaw Subagent Pool",
            "role": "Delegated Worker Pool",
            "description": "Logical pool for OpenClaw subagent runs and delegated tasks.",
            "runtime_type": "openclaw",
            "model_provider": "openclaw",
            "model_name": snapshot["model"],
            "status": "idle",
            "permission_level": "standard",
            "allowed_tools": json.dumps(["subagents.read", "run_log.read"], ensure_ascii=False),
            "budget_limit_usd": 12.0,
            "owner_user_id": "usr_founder",
            "created_at": created,
            "updated_at": created,
        },
    )
    upsert_task(
        conn,
        {
            "task_id": task_id,
            "title": "AgentOps MIS v1 OpenClaw observability experiment",
            "description": "Map a live OpenClaw probe plus safe config/cron/subagent metadata into MIS control-plane objects.",
            "requester_id": "usr_founder",
            "owner_agent_id": main_agent_id,
            "collaborator_agent_ids": json.dumps([subagent_pool_id], ensure_ascii=False),
            "status": "completed" if probe.get("ok") else "failed",
            "priority": "high",
            "due_date": None,
            "acceptance_criteria": "OpenClaw live probe is recorded as a run; safe config, cron, and subagent metadata are recorded as tool calls; evaluation is created.",
            "risk_level": "medium",
            "budget_limit_usd": 3.0,
            "created_at": created,
            "updated_at": created,
        },
    )

    conn.execute(
        """INSERT INTO runs(run_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            task_id,
            main_agent_id,
            "openclaw",
            "completed" if probe.get("ok") else "failed",
            created,
            now_iso(),
            probe.get("duration_ms"),
            "Live OpenClaw v1 probe and safe metadata snapshot.",
            "OpenClaw replied OPENCLAW_MIS_V1_OK." if probe.get("ok") else "OpenClaw probe failed or was skipped.",
            model_provider or probe.get("provider") or "openclaw",
            model_name,
            int(probe.get("input_tokens") or 0),
            int(probe.get("output_tokens") or 0),
            0,
            0.0,
            None if probe.get("ok") else "OpenClawProbeFailed",
            None if probe.get("ok") else (probe.get("error") or probe.get("summary") or "Probe did not return expected marker."),
            probe.get("run_id"),
            None,
            probe.get("session_id"),
            0,
            created,
        ),
    )
    audit(conn, "system", "openclaw-v1-experiment", "run.record", "runs", run_id, None, {"probe_ok": probe.get("ok"), "trace_id": probe.get("run_id")})

    tool_specs = [
        ("openclaw.config.snapshot", "file", "low", str(OPENCLAW_HOME / "openclaw.json"), {"model": snapshot["model"], "sandbox_mode": snapshot["sandbox_mode"]}),
        ("openclaw.cron.snapshot", "file", "low", str(OPENCLAW_HOME / "cron" / "jobs.json"), {"enabled": snapshot["cron_jobs_enabled"], "total": snapshot["cron_jobs_total"]}),
        ("openclaw.subagents.snapshot", "file", "low", str(OPENCLAW_HOME / "subagents" / "runs.json"), {"runs_count": snapshot["subagent_runs_count"]}),
        ("openclaw.agent.probe", "custom", "medium", "openclaw://agent/main", {"expected": "OPENCLAW_MIS_V1_OK", "ok": probe.get("ok")}),
    ]
    for name, category, risk, target, args in tool_specs:
        tc_id = new_id("tc")
        conn.execute(
            """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                tc_id,
                run_id,
                main_agent_id,
                name,
                "v1",
                category,
                json.dumps(args, ensure_ascii=False),
                target,
                risk,
                "completed" if (name != "openclaw.agent.probe" or probe.get("ok")) else "failed",
                "Safe metadata captured." if name != "openclaw.agent.probe" else probe.get("summary", "probe"),
                None,
                created,
                now_iso(),
                created,
            ),
        )
        audit(conn, "system", "openclaw-v1-experiment", "tool_call.record", "tool_calls", tc_id, None, {"tool_name": name, "risk": risk}, {"run_id": run_id})

    score = 0.95 if probe.get("ok") else 0.45
    eval_id = new_id("eval")
    rules = {
        "live_probe_ok": bool(probe.get("ok")),
        "safe_metadata_sources": len(snapshot["safe_sources"]),
        "cron_jobs_enabled": snapshot["cron_jobs_enabled"],
        "no_credentials_or_transcripts_read": True,
    }
    conn.execute(
        """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            eval_id,
            task_id,
            run_id,
            main_agent_id,
            "rule",
            score,
            "pass" if probe.get("ok") else "fail",
            json.dumps(rules, ensure_ascii=False),
            "v1 OpenClaw observability gate",
            now_iso(),
        ),
    )
    audit(conn, "system", "openclaw-v1-experiment", "evaluation.record", "evaluations", eval_id, None, rules, {"run_id": run_id})

    mem_id = new_id("mem")
    conn.execute(
        """INSERT INTO memories(memory_id,scope,memory_type,canonical_text,source_type,source_ref,project_id,task_id,agent_id,confidence,review_status,owner_user_id,ttl_review_due_at,supersedes_memory_id,access_tags,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            mem_id,
            "project",
            "agent_lesson",
            "AgentOps MIS v1 can represent OpenClaw as runtime_type=openclaw using live probe metadata for runs and safe config/cron/subagent snapshots as tool calls.",
            "run_log",
            run_id,
            "proj_mvp",
            task_id,
            main_agent_id,
            0.86 if probe.get("ok") else 0.58,
            "candidate",
            "usr_founder",
            (dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=30)).isoformat(),
            None,
            json.dumps(["v1", "openclaw", "agentops"], ensure_ascii=False),
            now_iso(),
            now_iso(),
        ),
    )
    audit(conn, "system", "openclaw-v1-experiment", "memory.propose", "memories", mem_id, None, {"source_ref": run_id}, {"task_id": task_id})

    return {"run_id": run_id, "task_id": task_id, "evaluation_id": eval_id, "memory_id": mem_id, "pass": bool(probe.get("ok"))}


def write_report(result, snapshot, probe):
    status = "PASS" if result["pass"] else "FAIL"
    lines = [
        "# V1 OpenClaw Experiment",
        "",
        f"- Status: {status}",
        f"- MIS task: `{result['task_id']}`",
        f"- MIS run: `{result['run_id']}`",
        f"- Evaluation: `{result['evaluation_id']}`",
        f"- Memory candidate: `{result['memory_id']}`",
        "",
        "## OpenClaw Probe",
        "",
        f"- OK: `{probe.get('ok')}`",
        f"- Provider/model: `{probe.get('provider') or 'unknown'}` / `{probe.get('model') or snapshot['model']}`",
        f"- Duration ms: `{probe.get('duration_ms')}`",
        f"- Tokens: input `{probe.get('input_tokens', 0)}`, output `{probe.get('output_tokens', 0)}`, total `{probe.get('total_tokens', 0)}`",
        f"- Trace/run id: `{probe.get('run_id')}`",
        "",
        "## Safe Snapshot",
        "",
        f"- OpenClaw default model: `{snapshot['model']}`",
        f"- Thinking default: `{snapshot['thinking_default']}`",
        f"- Max concurrent: `{snapshot['max_concurrent']}`",
        f"- Subagent max concurrent: `{snapshot['subagents_max_concurrent']}`",
        f"- Sandbox mode: `{snapshot['sandbox_mode']}`",
        f"- Enabled cron jobs: `{snapshot['cron_jobs_enabled']}` of `{snapshot['cron_jobs_total']}`",
        f"- Subagent run index count: `{snapshot['subagent_runs_count']}`",
        "",
        "## Privacy Boundary",
        "",
        "- Read safe metadata only: OpenClaw config defaults, cron job names/status counts, subagent run index counts.",
        "- Did not read credentials, channel message bodies, or session transcript contents.",
    ]
    OUTPUT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-live-probe", action="store_true", help="Do not call openclaw; record only safe metadata.")
    args = parser.parse_args()

    snapshot = safe_openclaw_snapshot()
    probe = run_live_probe(args.skip_live_probe)
    with db() as conn:
        result = insert_experiment(conn, snapshot, probe)
        conn.commit()
    write_report(result, snapshot, probe)
    print(json.dumps({"result": result, "report": str(OUTPUT_PATH), "probe_ok": probe.get("ok")}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
