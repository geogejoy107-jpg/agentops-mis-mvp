"""Bounded Codex CLI execution for the AgentOps worker adapter."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from .redaction import redact_text


DEFAULT_CODEX_APP_BIN = "/Applications/ChatGPT.app/Contents/Resources/codex"
PROHIBITED_ITEM_TYPES = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "web_search",
    "browser_action",
    "computer_use",
}
ALLOWED_EVENT_TYPES = {
    "thread.started",
    "turn.started",
    "item.started",
    "item.updated",
    "item.completed",
    "turn.completed",
    "error",
}
ALLOWED_ITEM_TYPES = {"agent_message", "reasoning"}
MAX_JSONL_BYTES = 2_000_000
MAX_JSONL_EVENTS = 2_000
DISABLED_FEATURES = (
    "apps",
    "browser_use",
    "computer_use",
    "goals",
    "hooks",
    "image_generation",
    "multi_agent",
    "plugins",
    "shell_tool",
    "unified_exec",
)


@dataclass
class CodexRuntimeResult:
    ok: bool
    output_summary: str
    raw_payload_hash: str
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: int = 0
    output_tokens: int = 0
    target_resource: str = "local://codex/read-only"
    retryable: bool = False
    observation: dict | None = None


def resolve_codex_binary(configured: str = "") -> Path:
    candidates = [
        configured.strip(),
        os.environ.get("CODEX_BIN", "").strip(),
        DEFAULT_CODEX_APP_BIN,
        shutil.which("codex") or "",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return path
    return Path(candidates[0] or "codex").expanduser()


def _safe_proxy_value(value: str) -> str | None:
    parsed = urlsplit(value)
    if parsed.username or parsed.password:
        return None
    return value


def codex_subprocess_env() -> dict[str, str]:
    allowed = {
        "HOME",
        "PATH",
        "TMPDIR",
        "LANG",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "NO_COLOR",
        "CODEX_HOME",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed and value}
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "all_proxy", "no_proxy"):
        value = os.environ.get(key)
        if not value:
            continue
        safe_value = _safe_proxy_value(value) if key.lower() != "no_proxy" else value
        if safe_value:
            env[key] = safe_value
    env["NO_COLOR"] = "1"
    return env


def codex_command(binary: Path, cwd: Path) -> list[str]:
    command = [
        str(binary),
        "exec",
        "--json",
        "--ephemeral",
        "--ignore-user-config",
        "--strict-config",
        "--config",
        'web_search="disabled"',
        "--sandbox",
        "read-only",
        "--color",
        "never",
        "-C",
        str(cwd),
        "-",
    ]
    for feature in DISABLED_FEATURES:
        command[2:2] = ["--disable", feature]
    return command


def _parse_jsonl(stdout: str) -> tuple[str, int, dict, list[str], list[str]]:
    final_message = ""
    output_tokens = 0
    event_counts: dict[str, int] = {}
    item_counts: dict[str, int] = {}
    parse_errors = 0
    prohibited: list[str] = []
    protocol_errors: list[str] = []
    lines = stdout.splitlines()
    if len(stdout.encode("utf-8")) > MAX_JSONL_BYTES:
        protocol_errors.append("jsonl_size_limit_exceeded")
    if len(lines) > MAX_JSONL_EVENTS:
        protocol_errors.append("jsonl_event_limit_exceeded")
    for line in lines[:MAX_JSONL_EVENTS]:
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            parse_errors += 1
            continue
        event_type = str(event.get("type") or "unknown")
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type not in ALLOWED_EVENT_TYPES:
            protocol_errors.append(f"unknown_event_type:{event_type}")
        item = event.get("item") if isinstance(event.get("item"), dict) else {}
        item_type = str(item.get("type") or "")
        if item_type:
            item_counts[item_type] = item_counts.get(item_type, 0) + 1
        if item_type in PROHIBITED_ITEM_TYPES:
            prohibited.append(item_type)
        elif item_type and item_type not in ALLOWED_ITEM_TYPES:
            protocol_errors.append(f"unknown_item_type:{item_type}")
        if event_type == "item.completed" and item_type == "agent_message":
            final_message = str(item.get("text") or "").strip()
        if event_type == "turn.completed":
            usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
            output_tokens = int(usage.get("output_tokens") or 0)
    if parse_errors:
        protocol_errors.append("jsonl_parse_error")
    for required_type in ("thread.started", "turn.started", "turn.completed"):
        if event_counts.get(required_type) != 1:
            protocol_errors.append(f"invalid_{required_type}_count")
    if item_counts.get("agent_message") != 1:
        protocol_errors.append("invalid_agent_message_count")
    observation = {
        "protocol": "codex_exec_jsonl_v1",
        "sandbox": "read-only",
        "ephemeral": True,
        "ignore_user_config": True,
        "strict_config": True,
        "web_search": "disabled",
        "disabled_features": list(DISABLED_FEATURES),
        "prompt_transport": "stdin",
        "event_counts": event_counts,
        "item_type_counts": item_counts,
        "parse_errors": parse_errors,
        "prohibited_item_types": sorted(set(prohibited)),
        "prohibited_event_count": len(prohibited),
        "protocol_errors": sorted(set(protocol_errors)),
        "protocol_valid": not protocol_errors,
        "raw_events_omitted": True,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "token_omitted": True,
    }
    return final_message, output_tokens, observation, prohibited, protocol_errors


def execute_codex_read_only(*, binary_path: str, prompt: str, cwd: Path, timeout: int) -> CodexRuntimeResult:
    binary = resolve_codex_binary(binary_path)
    started = time.time()
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return CodexRuntimeResult(
            ok=False,
            output_summary="Codex CLI is not available.",
            raw_payload_hash=hashlib.sha256(b"codex-binary-unavailable").hexdigest(),
            error_type="CodexBinaryUnavailable",
            error_message="Install Codex CLI or set CODEX_BIN to an executable path.",
            target_resource="local://codex/unavailable",
            retryable=False,
        )
    try:
        proc = subprocess.run(
            codex_command(binary, cwd),
            cwd=cwd,
            env=codex_subprocess_env(),
            input=prompt,
            capture_output=True,
            text=True,
            timeout=max(int(timeout or 300), 1),
            check=False,
        )
        final_message, output_tokens, observation, prohibited, protocol_errors = _parse_jsonl(proc.stdout or "")
        raw_hash = hashlib.sha256((proc.stdout or "").encode("utf-8")).hexdigest()
        duration_ms = int((time.time() - started) * 1000)
        if prohibited:
            return CodexRuntimeResult(
                ok=False,
                output_summary="Codex read-only adapter blocked a run that emitted prohibited tool events.",
                raw_payload_hash=raw_hash,
                error_type="CodexProhibitedToolEvent",
                error_message=f"Prohibited Codex event types: {', '.join(sorted(set(prohibited)))}.",
                duration_ms=duration_ms,
                output_tokens=output_tokens,
                retryable=False,
                observation=observation,
            )
        if protocol_errors:
            return CodexRuntimeResult(
                ok=False,
                output_summary="Codex read-only adapter rejected an invalid runtime event stream.",
                raw_payload_hash=raw_hash,
                error_type="CodexProtocolViolation",
                error_message=f"Codex JSONL protocol errors: {', '.join(sorted(set(protocol_errors)))}.",
                duration_ms=duration_ms,
                output_tokens=output_tokens,
                retryable=False,
                observation=observation,
            )
        ok = proc.returncode == 0 and bool(final_message)
        return CodexRuntimeResult(
            ok=ok,
            output_summary=redact_text(final_message, 200) if ok else "Codex read-only adapter execution failed.",
            raw_payload_hash=raw_hash,
            error_type=None if ok else "CodexExecutionFailed",
            error_message=None if ok else redact_text(proc.stderr or f"exit={proc.returncode}", 200),
            duration_ms=duration_ms,
            output_tokens=output_tokens,
            retryable=proc.returncode != 0,
            observation=observation,
        )
    except subprocess.TimeoutExpired:
        return CodexRuntimeResult(
            ok=False,
            output_summary="Codex read-only adapter timed out.",
            raw_payload_hash=hashlib.sha256(b"codex-timeout").hexdigest(),
            error_type="CodexTimeout",
            error_message=f"Codex execution exceeded {max(int(timeout or 300), 1)} seconds.",
            duration_ms=int((time.time() - started) * 1000),
            retryable=True,
        )
    except Exception as exc:
        return CodexRuntimeResult(
            ok=False,
            output_summary="Codex read-only adapter execution failed.",
            raw_payload_hash=hashlib.sha256(type(exc).__name__.encode("utf-8")).hexdigest(),
            error_type="CodexExecutionFailed",
            error_message=redact_text(str(exc), 200),
            duration_ms=int((time.time() - started) * 1000),
            retryable=True,
        )


def codex_preflight(*, binary_path: str, cwd: Path, timeout: int) -> dict:
    binary = resolve_codex_binary(binary_path)
    exists = binary.is_file()
    executable = exists and os.access(binary, os.X_OK)
    version_ok = False
    version_summary = ""
    if executable:
        try:
            proc = subprocess.run(
                [str(binary), "--version"],
                cwd=cwd,
                env=codex_subprocess_env(),
                capture_output=True,
                text=True,
                timeout=min(max(int(timeout or 5), 1), 20),
                check=False,
            )
            version_ok = proc.returncode == 0
            version_summary = redact_text(proc.stdout or proc.stderr or f"exit={proc.returncode}", 200)
        except Exception as exc:
            version_summary = redact_text(str(exc), 200)
    return {
        "ok": bool(executable and version_ok),
        "adapter": "codex",
        "target_resource": "local://codex/read-only",
        "binary_path": str(binary),
        "binary_exists": exists,
        "binary_executable": executable,
        "version_ok": version_ok,
        "version_summary": version_summary,
        "execution_contract": {
            "sandbox": "read-only",
            "ephemeral": True,
            "ignore_user_config": True,
            "strict_config": True,
            "web_search": "disabled",
            "disabled_features": list(DISABLED_FEATURES),
            "prompt_transport": "stdin",
            "prohibited_tool_events_fail_run": True,
            "agentops_token_inherited": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
        "live_execution_performed": False,
        "token_omitted": True,
    }
