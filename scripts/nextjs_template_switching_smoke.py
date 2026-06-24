#!/usr/bin/env python3
"""Verify Next.js template/base switching parity."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_template_switching_parity_v1"

sys.path.insert(0, str(SCRIPTS))

from nextjs_playwright_snapshot_smoke import (  # noqa: E402
    free_port,
    leaked_secret,
    restore_next_env,
    run,
    start_process,
    wait_http,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def http_json_status(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def http_text_status(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            return int(response.status), response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read().decode("utf-8", errors="replace")


def post_form_no_redirect(url: str, payload: dict[str, str]) -> tuple[int, str]:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
            return None

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=90) as response:
            return int(response.status), response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        if exc.code in {302, 303, 307, 308}:
            return int(exc.code), exc.headers.get("Location", "")
        raise


def query(location: str) -> dict[str, list[str]]:
    return urllib.parse.parse_qs(urllib.parse.urlparse(location).query)


def stop_processes(processes: list[subprocess.Popen[str]]) -> list[str]:
    logs: list[str] = []
    for proc in reversed(processes):
        if proc.poll() is None:
            proc.terminate()
        try:
            output, _ = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            output, _ = proc.communicate(timeout=5)
        if output:
            logs.append(output[-2000:])
    return logs


def assert_no_secret(label: str, payload: Any) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True)
    require("session_token" not in text, f"{label} leaked session_token")
    require("token_hash" not in text and "session_hash" not in text, f"{label} leaked token/session hash")
    require(not leaked_secret(text), f"{label} leaked token-like material")


def main() -> int:
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": "npx is required"}, indent=2), file=sys.stderr)
        return 1

    processes: list[subprocess.Popen[str]] = []
    api_port = free_port()
    next_port = free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    transcripts: list[Any] = []

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-template-switching-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            reset_env = os.environ.copy()
            reset_env.pop("AGENTOPS_API_KEY", None)
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env.pop("AGENTOPS_API_KEY", None)
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_API_KEY", None)
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/templates")

            page_status, page_html = http_text_status(f"{next_base}/workspace/templates")
            require(page_status == 200, f"templates page failed: {page_status}")
            for text in [
                "Template Switching",
                "template-switching-live-read-model",
                "template-base-switching-plan",
                "Core ledger protection",
                "/template-packages",
                "/bases",
                "/migration/preview",
            ]:
                require(text in page_html, f"templates page missing {text!r}")
            transcripts.append(page_html)

            packages_status, packages = http_json_status("GET", f"{next_base}/api/mis/template-packages")
            require(packages_status == 200 and isinstance(packages, list) and packages, f"template packages proxy failed: {packages_status} {packages}")
            require(any(item.get("template_id") == "tpl_ai_software_team" for item in packages if isinstance(item, dict)), f"seed template package missing: {packages}")
            transcripts.append(packages)

            bases_status, bases = http_json_status("GET", f"{next_base}/api/mis/bases")
            require(bases_status == 200 and bases.get("bases") and bases.get("capabilities"), f"bases proxy failed: {bases_status} {bases}")
            require(any(item.get("base_id") == "base_notion_tasks" for item in bases.get("bases", [])), f"notion task base missing: {bases}")
            transcripts.append(bases)

            bindings_status, bindings = http_json_status("GET", f"{next_base}/api/mis/template-bindings")
            require(bindings_status == 200 and isinstance(bindings, list), f"template bindings proxy failed: {bindings_status} {bindings}")
            transcripts.append(bindings)

            preview_status, preview = http_json_status("POST", f"{next_base}/api/mis/migration/preview", {
                "template_id": "tpl_ai_software_team",
                "from_base_id": "base_local_tasks",
                "to_base_id": "base_notion_tasks",
            })
            require(preview_status == 201, f"migration preview proxy failed: {preview_status} {preview}")
            require(preview.get("template_id") == "tpl_ai_software_team", f"migration preview template mismatch: {preview}")
            require(len(preview.get("migratable_objects") or []) >= 3, f"migration preview missing migratable objects: {preview}")
            require(len(preview.get("non_migratable_objects") or []) >= 3, f"migration preview missing protected objects: {preview}")
            transcripts.append(preview)

            form_status, location = post_form_no_redirect(f"{next_base}/workspace/templates/migration-preview", {
                "template_id": "tpl_ai_software_team",
                "from_base_id": "base_local_tasks",
                "to_base_id": "base_notion_tasks",
            })
            require(form_status == 303, f"migration preview form did not redirect: {form_status} {location}")
            form_query = query(location)
            require(form_query.get("preview_status") == ["created"], f"migration preview form missing success query: {location}")
            require(form_query.get("preview_template_id") == ["tpl_ai_software_team"], f"migration preview form wrong template: {location}")
            transcripts.append(location)

            preview_page_status, preview_page = http_text_status(f"{next_base}{urllib.parse.urlparse(location).path}?{urllib.parse.urlparse(location).query}")
            require(preview_page_status == 200, f"preview feedback page failed: {preview_page_status}")
            require("Migration preview recorded" in preview_page, "preview feedback banner missing")
            transcripts.append(preview_page)

            transcript = json.dumps(transcripts, ensure_ascii=False, sort_keys=True)
            assert_no_secret("template switching transcript", transcript)

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "route": "/workspace/templates",
                "template_packages": len(packages),
                "bases": len(bases.get("bases") or []),
                "bindings": len(bindings),
                "preview_status": preview_status,
                "form_status": form_status,
                "secret_leaked": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    finally:
        logs = stop_processes(processes)
        restore_next_env()
        if any(proc.returncode not in (0, None, -15) for proc in processes):
            print(json.dumps({"process_logs": logs[-2:]}, ensure_ascii=False, indent=2), file=sys.stderr)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        raise
