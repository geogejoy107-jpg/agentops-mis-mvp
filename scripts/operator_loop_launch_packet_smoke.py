#!/usr/bin/env python3
"""Verify the read-only Agent Work Method launch packet API and CLI."""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, query: dict | None = None) -> tuple[int, dict]:
    suffix = f"?{urlencode(query or {})}" if query else ""
    req = Request(base_url.rstrip("/") + path + suffix, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=45) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def run_cli(base_url: str, args: list[str], env: dict) -> subprocess.CompletedProcess[str]:
    cli_env = env.copy()
    cli_env["AGENTOPS_BASE_URL"] = base_url
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=cli_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def load_json(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/loop-launch-packet", {"limit": 1})
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            "tasks",
            "runs",
            "tool_calls",
            "memories",
            "approvals",
            "agent_plans",
            "plan_evidence_manifests",
            "audit_logs",
            "runtime_events",
            "knowledge_documents",
        ]
        result = {}
        for table in tables:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate_packet(payload: dict, label: str, task_id: str, agent_id: str, failures: list[str], *, expected_control_operation: str = "operator_loop_control", expected_handoff_mode: str = "lightweight") -> None:
    require(payload.get("operation") == "operator_loop_launch_packet", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("method") == "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD", f"{label} method mismatch: {payload}", failures)
    require(payload.get("task_id") == task_id, f"{label} task mismatch: {payload.get('task_id')} != {task_id}", failures)
    require(payload.get("agent_id") == agent_id, f"{label} agent mismatch: {payload.get('agent_id')} != {agent_id}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing: {payload}", failures)
    summary = payload.get("summary") or {}
    require(summary.get("handoff_mode") == expected_handoff_mode, f"{label} handoff mode wrong: {summary}", failures)
    require(summary.get("operator_control_status") in {"ready", "attention", "blocked", "unknown", None}, f"{label} operator control status unexpected: {summary}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} should not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} should not execute live work: {safety}", failures)
    phases = [item.get("phase") for item in payload.get("launch_sequence") or []]
    require(phases == ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"], f"{label} phases wrong: {phases}", failures)
    draft = payload.get("agent_plan_draft") or {}
    for key in [
        "task_understanding",
        "referenced_specs",
        "referenced_memories",
        "referenced_bases",
        "proposed_files_to_change",
        "risk_level",
        "approval_required",
        "execution_steps",
        "verification_plan",
        "rollback_plan",
    ]:
        require(key in draft, f"{label} draft missing {key}: {draft}", failures)
    require("PROJECT_SPEC.md" in (draft.get("referenced_specs") or []), f"{label} draft missing project spec: {draft}", failures)
    require("base_local_memory" in (draft.get("referenced_bases") or []), f"{label} draft missing memory base: {draft}", failures)
    commands = payload.get("commands") or []
    joined = "\n".join(commands)
    require("agentops agent-plan create" in joined, f"{label} missing agent-plan create command: {commands}", failures)
    require("agentops agent-plan verify" in joined, f"{label} missing plan verify command: {commands}", failures)
    require("agentops knowledge search" in joined, f"{label} missing knowledge search command: {commands}", failures)
    require("agentops commander repo-map" in joined, f"{label} missing commander repo-map command: {commands}", failures)
    require("agentops operator loop-control" in joined, f"{label} missing lightweight loop-control command: {commands}", failures)
    require("agentops operator loop-self-check" in joined, f"{label} missing loop self-check command: {commands}", failures)
    require("agentops operator evidence-report" in joined, f"{label} missing evidence report command: {commands}", failures)
    require("agentops operator action-receipts" in joined, f"{label} missing action receipts command: {commands}", failures)
    require("agentops plan-evidence create" in joined, f"{label} missing plan evidence command: {commands}", failures)
    evaluation_contract = payload.get("evaluation_contract") or {}
    require(evaluation_contract.get("operation") == "loop_evaluation_contract", f"{label} evaluation contract missing: {evaluation_contract}", failures)
    require(evaluation_contract.get("status") in {"ready", "attention", "blocked", "unknown"}, f"{label} evaluation status wrong: {evaluation_contract}", failures)
    require(evaluation_contract.get("token_omitted") is True, f"{label} evaluation token omission missing: {evaluation_contract}", failures)
    for ledger in ["agent_plans", "plan_evidence_manifests", "tool_calls", "evaluations", "artifacts", "audit_logs", "operator_action_receipts", "operator_action_evaluations"]:
        require(ledger in (evaluation_contract.get("required_ledgers") or []), f"{label} evaluation required ledger missing {ledger}: {evaluation_contract}", failures)
    criteria = "\n".join(evaluation_contract.get("minimum_exit_criteria") or [])
    require("Agent Plan verifies" in criteria, f"{label} evaluation criteria missing plan verify: {criteria}", failures)
    require("plan_evidence_manifest" in criteria, f"{label} evaluation criteria missing manifest: {criteria}", failures)
    audit_contract = payload.get("audit_contract") or {}
    require(audit_contract.get("operation") == "loop_audit_contract", f"{label} audit contract missing: {audit_contract}", failures)
    require(audit_contract.get("tamper_chain_required") is True, f"{label} tamper chain requirement missing: {audit_contract}", failures)
    require(audit_contract.get("record_required") is True, f"{label} record requirement missing: {audit_contract}", failures)
    require(audit_contract.get("token_omitted") is True, f"{label} audit token omission missing: {audit_contract}", failures)
    bounded_runner = audit_contract.get("bounded_runner") or {}
    require(bounded_runner.get("policy_id") == "advance_loop_local_bounded_v1", f"{label} bounded policy missing: {bounded_runner}", failures)
    require(bounded_runner.get("server_executes_shell") is False, f"{label} server shell boundary missing: {bounded_runner}", failures)
    require("--confirm-live" in (bounded_runner.get("denied_flags") or []), f"{label} live confirm denied flag missing: {bounded_runner}", failures)
    retrieve_phase = next((item for item in payload.get("launch_sequence") or [] if item.get("phase") == "RETRIEVE"), {})
    verify_phase = next((item for item in payload.get("launch_sequence") or [] if item.get("phase") == "VERIFY"), {})
    record_phase = next((item for item in payload.get("launch_sequence") or [] if item.get("phase") == "RECORD"), {})
    repo_map = retrieve_phase.get("repo_map") or {}
    require(repo_map.get("operation") == "repo_map", f"{label} retrieve phase lacks repo-map: {retrieve_phase}", failures)
    require(repo_map.get("status") in {"ready", "empty"}, f"{label} repo-map status invalid: {repo_map}", failures)
    require(repo_map.get("command") and "agentops commander repo-map" in repo_map.get("command"), f"{label} repo-map command missing: {repo_map}", failures)
    require((repo_map.get("safety") or {}).get("read_only") is True, f"{label} repo-map read-only proof missing: {repo_map}", failures)
    require(repo_map.get("snippets_omitted") is True and repo_map.get("raw_content_omitted") is True, f"{label} repo-map should omit raw content: {repo_map}", failures)
    for item in repo_map.get("files") or []:
        require(item.get("path") and item.get("content_hash"), f"{label} repo-map file missing path/hash: {item}", failures)
        require((item.get("source_provenance") or {}).get("raw_content_returned") is False, f"{label} repo-map provenance leaked raw body: {item}", failures)
        require(item.get("snippets_omitted") is True and item.get("raw_content_omitted") is True, f"{label} repo-map file should omit snippets/raw body: {item}", failures)
    require((verify_phase.get("evaluation_contract") or {}).get("operation") == "loop_evaluation_contract", f"{label} verify phase lacks evaluation contract: {verify_phase}", failures)
    require((record_phase.get("audit_contract") or {}).get("operation") == "loop_audit_contract", f"{label} record phase lacks audit contract: {record_phase}", failures)
    execution_chain = payload.get("execution_chain") or []
    require(len(execution_chain) >= 7, f"{label} execution chain too short: {execution_chain}", failures)
    chain_ids = [item.get("step_id") for item in execution_chain]
    for step_id in [
        "pre_advance_self_check",
        "bounded_advance_preview",
        "bounded_advance_confirm",
        "verify_loop_evidence",
        "record_plan_evidence",
        "record_review_queue",
        "loop_audit_final",
    ]:
        require(step_id in chain_ids, f"{label} execution chain missing {step_id}: {chain_ids}", failures)
    chain_joined = "\n".join(str(item.get("command") or "") for item in execution_chain)
    require("agentops operator advance-loop" in chain_joined, f"{label} execution chain missing advance-loop: {execution_chain}", failures)
    require("--confirm-advance" in chain_joined, f"{label} execution chain missing confirm advance: {execution_chain}", failures)
    require("agentops plan-evidence create" in chain_joined, f"{label} execution chain missing plan evidence: {execution_chain}", failures)
    confirm_step = next((item for item in execution_chain if item.get("step_id") == "bounded_advance_confirm"), {})
    require(confirm_step.get("mutating") is True, f"{label} confirm step should be mutating: {confirm_step}", failures)
    require(confirm_step.get("confirm_required") is True, f"{label} confirm step should require confirmation: {confirm_step}", failures)
    require(confirm_step.get("receipt_required") is True, f"{label} confirm step should require receipt: {confirm_step}", failures)
    require(confirm_step.get("policy_id") == "advance_loop_local_bounded_v1", f"{label} confirm step policy missing: {confirm_step}", failures)
    require("--confirm-live" in (confirm_step.get("denied_flags") or []), f"{label} confirm step denied flags missing: {confirm_step}", failures)
    require(all(item.get("token_omitted") is True for item in execution_chain), f"{label} execution chain token omission missing: {execution_chain}", failures)
    require(all(item.get("step_status") in {"ready", "attention", "blocked", "verified"} for item in execution_chain), f"{label} execution chain missing live step status: {execution_chain}", failures)
    require(all((item.get("receipt_state") or {}).get("token_omitted") is True for item in execution_chain), f"{label} execution chain receipt state token omission missing: {execution_chain}", failures)
    require(all(item.get("blocked_reason") or item.get("ready_reason") for item in execution_chain), f"{label} execution chain missing readiness reasons: {execution_chain}", failures)
    require((confirm_step.get("receipt_state") or {}).get("required") is True, f"{label} confirm step receipt state missing: {confirm_step}", failures)
    require(confirm_step.get("blocked_reason") or (confirm_step.get("receipt_state") or {}).get("verified") is True, f"{label} confirm step should explain confirm/receipt gate: {confirm_step}", failures)
    record_step = next((item for item in execution_chain if item.get("step_id") == "record_plan_evidence"), {})
    require(record_step.get("step_status") in {"blocked", "verified"}, f"{label} plan evidence step should be id-gated or verified: {record_step}", failures)
    control_summary = payload.get("control_summary") or {}
    recommended_step = control_summary.get("recommended_step") or {}
    require(control_summary.get("operation") == "loop_launch_control_summary", f"{label} control summary missing: {control_summary}", failures)
    require(control_summary.get("status") in {"ready", "attention", "blocked"}, f"{label} control status invalid: {control_summary}", failures)
    require(control_summary.get("copy_only") is True, f"{label} control summary must be copy-only: {control_summary}", failures)
    require(control_summary.get("server_executes_shell") is False, f"{label} control summary server shell boundary missing: {control_summary}", failures)
    require(recommended_step.get("step_id") in chain_ids, f"{label} recommended step not in chain: {recommended_step}", failures)
    require(control_summary.get("next_command") == recommended_step.get("command"), f"{label} control next command mismatch: {control_summary}", failures)
    require((recommended_step.get("control_mode") or control_summary.get("mode")) in {"read_only_copy", "receipt_required", "human_confirm_required", "blocked_waiting_input"}, f"{label} control mode invalid: {control_summary}", failures)
    require(control_summary.get("token_omitted") is True and recommended_step.get("token_omitted") is True, f"{label} control token omission missing: {control_summary}", failures)
    sources = payload.get("sources") or {}
    require((sources.get("intake") or {}).get("operation") == "task_intake_checklist", f"{label} missing intake source: {sources}", failures)
    require((sources.get("knowledge_search") or {}).get("operation") == "knowledge_search", f"{label} missing knowledge source: {sources}", failures)
    require((sources.get("repo_map") or {}).get("operation") == "repo_map", f"{label} missing repo-map source: {sources}", failures)
    operator_control = sources.get("operator_control") or {}
    handoff_source = sources.get("handoff") or {}
    require(operator_control.get("operation") == expected_control_operation, f"{label} missing operator control source: {sources}", failures)
    require(operator_control.get("mode") == expected_handoff_mode, f"{label} operator control mode mismatch: {operator_control}", failures)
    require(handoff_source.get("operation") == expected_control_operation, f"{label} handoff compatibility source mismatch: {sources}", failures)
    require(handoff_source.get("mode") == expected_handoff_mode, f"{label} handoff mode mismatch: {handoff_source}", failures)
    require(operator_control.get("token_omitted") is True and handoff_source.get("token_omitted") is True, f"{label} control source token omission missing: {sources}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    agent_id = f"agt_loop_launch_{stamp}"
    task_id = f"tsk_loop_launch_{stamp}"
    with tempfile.TemporaryDirectory(prefix="agentops-loop-launch-packet-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            for args in [
                ["knowledge", "index", "--rebuild"],
                ["agent", "register", "--id", agent_id, "--name", f"Loop Launch {stamp}", "--role", "Builder", "--runtime", "codex"],
                [
                    "task",
                    "create",
                    "--task-id",
                    task_id,
                    "--title",
                    "Loop launch packet smoke task",
                    "--description",
                    "Verify a read-only packet can guide the next agent loop.",
                    "--owner-agent-id",
                    agent_id,
                    "--requester-id",
                    "usr_founder",
                    "--acceptance",
                    "Launch packet must include method phases, plan draft, retrieval, compare, verify and record commands.",
                    "--risk",
                    "medium",
                ],
            ]:
                proc_cli = run_cli(base_url, args, env)
                outputs.extend([proc_cli.stdout, proc_cli.stderr])
                require(proc_cli.returncode == 0, f"CLI setup failed for {args}: {proc_cli.stderr or proc_cli.stdout}", failures)
            before = db_fingerprint(db_path)
            status, api_payload = http_json(
                base_url,
                "/api/operator/loop-launch-packet",
                {"task_id": task_id, "agent_id": agent_id, "limit": 8, "q": "Agent Work Method Block"},
            )
            outputs.append(json.dumps(api_payload, ensure_ascii=False))
            require(status == 200, f"API status mismatch: {status} {api_payload}", failures)
            validate_packet(api_payload, "api", task_id, agent_id, failures)
            cli_proc = run_cli(
                base_url,
                ["operator", "loop-launch-packet", "--task-id", task_id, "--agent-id", agent_id, "--limit", "8", "--query", "Agent Work Method Block"],
                env,
            )
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            cli_payload = load_json(cli_proc.stdout)
            require(cli_proc.returncode == 0, f"CLI launch packet failed: {cli_proc.stderr or cli_proc.stdout}", failures)
            validate_packet(cli_payload, "cli", task_id, agent_id, failures)
            full_status, full_payload = http_json(
                base_url,
                "/api/operator/loop-launch-packet",
                {"task_id": task_id, "agent_id": agent_id, "limit": 8, "q": "Agent Work Method Block", "full_handoff": "true"},
            )
            outputs.append(json.dumps(full_payload, ensure_ascii=False))
            require(full_status == 200, f"Full handoff API status mismatch: {full_status} {full_payload}", failures)
            validate_packet(full_payload, "api_full_handoff", task_id, agent_id, failures, expected_control_operation="operator_handoff", expected_handoff_mode="full")
            full_cli = run_cli(
                base_url,
                ["operator", "loop-launch-packet", "--task-id", task_id, "--agent-id", agent_id, "--limit", "8", "--query", "Agent Work Method Block", "--full-handoff"],
                env,
            )
            outputs.extend([full_cli.stdout, full_cli.stderr])
            full_cli_payload = load_json(full_cli.stdout)
            require(full_cli.returncode == 0, f"Full handoff CLI launch packet failed: {full_cli.stderr or full_cli.stdout}", failures)
            validate_packet(full_cli_payload, "cli_full_handoff", task_id, agent_id, failures, expected_control_operation="operator_handoff", expected_handoff_mode="full")
            after = db_fingerprint(db_path)
            require(before == after, f"launch packet changed database fingerprint: {before} -> {after}", failures)
            require(not leaked("\n".join(outputs)), "loop launch packet leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    result = {
        "ok": not failures,
        "operation": "operator_loop_launch_packet_smoke",
        "failures": failures,
        "secret_leaked": leaked("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
