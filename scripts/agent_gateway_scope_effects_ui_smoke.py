#!/usr/bin/env python3
"""Verify the Agent Gateway enrollment UI explains selected scope effects."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"
SCOPE_MATRIX_SMOKE = ROOT / "scripts" / "agent_gateway_scope_matrix_smoke.py"
SERVER = ROOT / "server.py"


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def extract_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    if end < 0:
        return text[start:]
    return text[start:end]


def main() -> int:
    failures: list[str] = []
    ai = AI_EMPLOYEES.read_text(encoding="utf-8")
    matrix = SCOPE_MATRIX_SMOKE.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")

    scope_logic = extract_block(ai, "const scopeEffectRows = [", "useEffect(() =>")
    scope_panel = extract_block(ai, 'data-testid="agent-gateway-scope-effects"', "enrollmentPolicy.invalid_scopes")
    auth_context = extract_block(server, "def agent_gateway_auth_context", "def agent_gateway_auth_error")

    require("agent-gateway-scope-effects" in ai, "AI Employees page missing selected scope effects panel", failures)
    require("scopeEffectRows" in ai, "AI Employees page missing scope effect row model", failures)
    require("agents:heartbeat" in scope_logic and ".endsWith(\":read\")" in scope_logic, "read/heartbeat scope classification missing", failures)
    require("tasks:claim" in scope_logic and "runs:write" in scope_logic, "execution scope classification missing", failures)
    require("toolcalls:write" in scope_logic and "runtime_events:write" in scope_logic and "evaluations:submit" in scope_logic, "evidence-write scope classification missing", failures)
    require("agent_plans:" in scope_logic and "plan_evidence:" in scope_logic, "governance scope classification missing", failures)
    require("scopeEffectsSummary" in scope_panel and "scopeRbacProof" in scope_panel, "scope effects panel missing 403 proof copy", failures)
    require("HTTP 403" in ai and "服务端执行这些 endpoint scope" in ai, "English/Chinese scope enforcement copy missing", failures)
    require("Agent Gateway scoped-token RBAC returns 403" in matrix, "scope matrix smoke does not document 403 RBAC contract", failures)
    require("require(status == 403" in matrix, "scope matrix smoke does not assert missing-scope 403", failures)
    require("missing required scope" in auth_context and "forbidden" in auth_context, "Agent Gateway auth context does not return forbidden for missing scopes", failures)

    print(json.dumps({
        "operation": "agent_gateway_scope_effects_ui_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "files": [
            str(AI_EMPLOYEES.relative_to(ROOT)),
            str(SCOPE_MATRIX_SMOKE.relative_to(ROOT)),
            str(SERVER.relative_to(ROOT)),
        ],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
