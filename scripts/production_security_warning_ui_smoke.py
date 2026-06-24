#!/usr/bin/env python3
"""Verify production-security warnings are prominent in the AI Employees UI."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_(API|ADMIN)_KEY=", re.IGNORECASE),
]


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
    live_api = LIVE_API.read_text(encoding="utf-8")
    warning_strip = extract_block(ai, 'data-testid="production-security-warning-strip"', 'data-testid="commander-work-package-planner"')
    gateway_card = extract_block(ai, "{copy.productionSecurity}</div>", "{copy.recentEvents}")
    readiness_type = extract_block(live_api, "export interface SecurityProductionReadinessPayload", "export interface DemoReadinessShot")
    readiness_loader = extract_block(live_api, "export async function loadSecurityProductionReadiness", "export async function loadDemoReadiness")

    expected_markers = {
        "strip_test_id": 'data-testid="production-security-warning-strip"',
        "strip_before_commander": 'data-testid="production-security-warning-strip"',
        "warning_attention_state": "productionSecurityNeedsAttention",
        "warning_status": "productionSecurityStatus",
        "warning_next_action": "productionSecurityNextAction",
        "warning_label_en": 'productionSecurityWarning: "Production security boundary"',
        "warning_label_zh": 'productionSecurityWarning: "生产安全边界"',
        "warning_summary_en": "Shared/production use must pass admin write guard",
        "warning_summary_zh": "共享/生产使用前，Admin 写保护",
        "warning_icon_alert": "AlertTriangle",
        "warning_icon_pass": "ShieldCheck",
        "warning_status_badge": "StatusBadge status={productionSecurityStatus}",
        "local_write_guard_badge": 'label={copy.localWriteGuard}',
        "deployment_mode_copy_en": 'deploymentMode: "Deployment mode"',
        "deployment_mode_copy_zh": 'deploymentMode: "部署模式"',
        "startup_security_copy_en": 'startupSecurity: "Startup security"',
        "startup_security_copy_zh": 'startupSecurity: "启动安全"',
        "deployment_mode_value": "securityReadiness?.deployment_mode",
        "startup_security_value": "securityReadiness?.startup_security?.status",
        "warning_next_action_copy": "copyIntakeCommand(productionSecurityNextAction)",
    }
    for label, marker in expected_markers.items():
        if marker not in ai:
            failures.append(f"missing {label}: {marker}")

    require(bool(warning_strip), "production security warning strip block missing", failures)
    require("commander-work-package-planner" in ai and ai.find('data-testid="production-security-warning-strip"') < ai.find('data-testid="commander-work-package-planner"'), "warning strip should appear before operator work queues", failures)
    require("localWriteGuardGate?.detail" in warning_strip, "warning strip should render local write guard detail", failures)
    require("securityReadiness?.contract" in warning_strip, "warning strip should fall back to security contract", failures)
    require("productionSecurityNextAction" in warning_strip, "warning strip should render next action", failures)
    require("localWriteGuardGate?.detail" in gateway_card, "detailed gateway card should still include local write guard detail", failures)
    require("deployment_mode: string;" in readiness_type, "readiness type should include deployment_mode", failures)
    require("startup_security?: StartupSecurityAssessment;" in readiness_type, "readiness type should include startup_security", failures)
    require("export interface StartupSecurityAssessment" in live_api, "startup security type should be explicit", failures)
    require("deployment_mode: String(raw.deployment_mode" in readiness_loader, "readiness loader should normalize deployment_mode", failures)
    require("startup_security:" in readiness_loader, "readiness loader should normalize startup_security", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(f"{ai}\n{live_api}")]
    require(not secret_hits, f"secret-like marker found in UI/API source: {secret_hits}", failures)

    output = {
        "ok": not failures,
        "operation": "production_security_warning_ui_smoke",
        "files": [str(AI_EMPLOYEES.relative_to(ROOT)), str(LIVE_API.relative_to(ROOT))],
        "contract": "AI Employees shows a top-of-page production-security warning before operator queues and backs it with normalized readiness evidence.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
