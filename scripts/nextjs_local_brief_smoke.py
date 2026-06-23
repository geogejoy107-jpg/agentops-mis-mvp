#!/usr/bin/env python3
"""Verify Next.js exposes local brief dry-run controls while blocking live run."""
from __future__ import annotations

import json
import os
import shutil
import stat
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
CONTRACT_ID = "nextjs_local_brief_v1"

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


def write_fake_cli(path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env python3
import os
import sys
from pathlib import Path
log_path = Path(os.environ["AGNESFALLBACK_FAKE_LOG"])
prompt = sys.argv[sys.argv.index("-z") + 1] if "-z" in sys.argv else ""
with log_path.open("a", encoding="utf-8") as handle:
    handle.write(f"called prompt_chars={len(prompt)}\\n")
print("本地简报已生成：NEXT_LOCAL_BRIEF_OK")
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def cli_call_count(log_path: Path) -> int:
    if not log_path.exists():
        return 0
    return len([line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()])


def http_json_status(method: str, url: str, payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    headers = {"Content-Type": "application/json"} if payload is not None else {}
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
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
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=120) as response:
            return int(response.status), response.headers.get("Location", "")
    except urllib.error.HTTPError as exc:
        if exc.code in {302, 303, 307, 308}:
            return int(exc.code), exc.headers.get("Location", "")
        raise


def absolute_location(base_url: str, location: str) -> str:
    parsed = urllib.parse.urlparse(location)
    if parsed.path.startswith("/workspace/"):
        return urllib.parse.urljoin(base_url.rstrip("/") + "/", parsed.path.lstrip("/") + (f"?{parsed.query}" if parsed.query else ""))
    if parsed.scheme and parsed.netloc:
        return location
    return urllib.parse.urljoin(base_url.rstrip("/") + "/", location)


def audit_count(api_base: str) -> int:
    status, payload = http_json_status("GET", f"{api_base}/api/audit?limit=200")
    require(status == 200 and isinstance(payload, list), f"audit list failed: {status} {payload}")
    return len(payload)


def assert_dry_run_result(label: str, payload: Any) -> tuple[str, str]:
    require(isinstance(payload, dict), f"{label} payload is not object: {payload}")
    require(payload.get("provider") == "agnesfallback", f"{label} wrong provider: {payload}")
    require(payload.get("workflow") == "local_ai_brief", f"{label} wrong workflow: {payload}")
    require(payload.get("dry_run") is True, f"{label} was not dry-run: {payload}")
    require(payload.get("would_run") and "[SAFE_STRUCTURED_MIS_BRIEF_PROMPT]" in str(payload.get("would_run")), f"{label} missing safe prompt placeholder: {payload}")
    require(payload.get("prompt_hash") and payload.get("state_hash"), f"{label} missing hashes: {payload}")
    require("state_preview" in payload, f"{label} missing state preview: {payload}")
    require("prompt" not in payload and "JSON 状态" not in json.dumps(payload, ensure_ascii=False), f"{label} leaked prompt body: {payload}")
    return str(payload["prompt_hash"]), str(payload["state_hash"])


def assert_prepared_result(label: str, payload: Any) -> tuple[str, str, str, str]:
    require(isinstance(payload, dict), f"{label} payload is not object: {payload}")
    require(payload.get("provider") == "agnesfallback", f"{label} wrong provider: {payload}")
    require(payload.get("workflow") == "local_ai_brief", f"{label} wrong workflow: {payload}")
    require(payload.get("dry_run") is False, f"{label} should be a prepared live action: {payload}")
    require(payload.get("requires_approval") is True, f"{label} missing approval requirement: {payload}")
    require(payload.get("provider_call_performed") is False, f"{label} called provider before approval: {payload}")
    require(payload.get("prepared_action_id") and payload.get("approval_id"), f"{label} missing approval ids: {payload}")
    require(payload.get("prompt_hash") and payload.get("state_hash"), f"{label} missing hashes: {payload}")
    require(payload.get("raw_prompt_omitted") is True, f"{label} did not omit raw prompt: {payload}")
    require("prompt" not in payload and "JSON 状态" not in json.dumps(payload, ensure_ascii=False), f"{label} leaked prompt body: {payload}")
    return str(payload["prepared_action_id"]), str(payload["approval_id"]), str(payload["prompt_hash"]), str(payload["state_hash"])


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
        with tempfile.TemporaryDirectory(prefix="agentops-next-local-brief-") as tmp:
            tmp_path = Path(tmp)
            db_path = str(tmp_path / "agentops.db")
            runtime_dir = tmp_path / "runtime"
            fake_cli = tmp_path / "agnesfallback"
            fake_cli_log = tmp_path / "agnesfallback-cli.log"
            runtime_dir.mkdir(parents=True, exist_ok=True)
            write_fake_cli(fake_cli)
            reset_env = os.environ.copy()
            reset_env.pop("AGENTOPS_API_KEY", None)
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_RUNTIME_DIR"] = str(runtime_dir)
            reset_env["HERMES_ALLOW_REAL_RUN"] = "true"
            reset_env["AGNESFALLBACK_BIN"] = str(fake_cli)
            reset_env["AGNESFALLBACK_FAKE_LOG"] = str(fake_cli_log)
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")

            api_env = os.environ.copy()
            api_env.pop("AGENTOPS_API_KEY", None)
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_RUNTIME_DIR"] = str(runtime_dir)
            api_env["HERMES_ALLOW_REAL_RUN"] = "true"
            api_env["AGNESFALLBACK_BIN"] = str(fake_cli)
            api_env["AGNESFALLBACK_FAKE_LOG"] = str(fake_cli_log)
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env.pop("AGENTOPS_API_KEY", None)
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace/pixel-office")

            prepare_status, prepare_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/local-brief",
                {"confirm_run": True},
            )
            transcripts.append(prepare_payload)
            require(prepare_status == 202, f"live local brief proxy should prepare approval action: {prepare_status} {prepare_payload}")
            prepared_action_id, approval_id, prepared_prompt_hash, prepared_state_hash = assert_prepared_result("proxy prepare", prepare_payload)
            require(cli_call_count(fake_cli_log) == 0, "fake CLI called during Next proxy prepare")

            premature_status, premature_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/local-brief",
                {"confirm_run": True, "prepared_action_id": prepared_action_id, "prompt_hash": prepared_prompt_hash, "state_hash": prepared_state_hash},
            )
            transcripts.append(premature_payload)
            require(premature_status == 428 and premature_payload.get("error") == "approval_required", f"premature proxy resume should require approval: {premature_status} {premature_payload}")
            require(cli_call_count(fake_cli_log) == 0, "fake CLI called during premature proxy resume")

            approved_status, approved_payload = http_json_status("POST", f"{api_base}/api/approvals/{approval_id}/approve", {})
            transcripts.append(approved_payload)
            require(approved_status == 200 and approved_payload.get("decision") == "approved", f"approval failed: {approved_status} {approved_payload}")
            require(cli_call_count(fake_cli_log) == 0, "fake CLI called during local brief approval")

            mismatch_status, mismatch_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/local-brief",
                {"confirm_run": True, "prepared_action_id": prepared_action_id, "prompt_hash": "bad-prompt-hash", "state_hash": prepared_state_hash},
            )
            transcripts.append(mismatch_payload)
            require(mismatch_status == 409 and mismatch_payload.get("error") == "prepared_action_prompt_hash_mismatch", f"hash mismatch should be blocked: {mismatch_status} {mismatch_payload}")
            require(cli_call_count(fake_cli_log) == 0, "fake CLI called during proxy hash mismatch")

            resumed_status, resumed_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/local-brief",
                {"confirm_run": True, "prepared_action_id": prepared_action_id, "prompt_hash": prepared_prompt_hash, "state_hash": prepared_state_hash},
            )
            transcripts.append(resumed_payload)
            require(resumed_status == 201 and resumed_payload.get("ok") is True, f"proxy resume should run once: {resumed_status} {resumed_payload}")
            require(resumed_payload.get("prepared_action_status") == "consumed", f"proxy resume did not consume action: {resumed_payload}")
            require(cli_call_count(fake_cli_log) == 1, "fake CLI should be called exactly once after proxy resume")

            replay_status, replay_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/local-brief",
                {"confirm_run": True, "prepared_action_id": prepared_action_id, "prompt_hash": prepared_prompt_hash, "state_hash": prepared_state_hash},
            )
            transcripts.append(replay_payload)
            require(replay_status == 409 and replay_payload.get("error") == "prepared_action_already_consumed", f"proxy replay should be blocked: {replay_status} {replay_payload}")
            require(cli_call_count(fake_cli_log) == 1, "fake CLI called during proxy replay")

            dry_status, dry_payload = http_json_status(
                "POST",
                f"{next_base}/api/mis/workflows/local-brief",
                {"confirm_run": False},
            )
            transcripts.append(dry_payload)
            require(dry_status == 201, f"dry-run local brief proxy returned {dry_status}: {dry_payload}")
            proxy_prompt_hash, proxy_state_hash = assert_dry_run_result("proxy dry-run", dry_payload)

            form_prepare_status, form_prepare_location = post_form_no_redirect(
                f"{next_base}/workspace/pixel-office/local-brief",
                {"confirm_run": "true"},
            )
            transcripts.append(form_prepare_location)
            require(form_prepare_status == 303, f"live local brief form did not redirect after prepare: {form_prepare_status} {form_prepare_location}")
            form_prepare_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_prepare_location).query)
            require(form_prepare_query.get("local_brief_status") == ["waiting_approval"], f"live local brief form did not report waiting approval: {form_prepare_location}")
            form_prepared_action_id = (form_prepare_query.get("local_brief_prepared_action_id") or [""])[0]
            form_approval_id = (form_prepare_query.get("local_brief_approval_id") or [""])[0]
            form_prompt_hash = (form_prepare_query.get("local_brief_prompt_hash") or [""])[0]
            form_state_hash = (form_prepare_query.get("local_brief_state_hash") or [""])[0]
            require(form_prepared_action_id and form_approval_id and form_prompt_hash and form_state_hash, f"form prepare missing ids/hashes: {form_prepare_location}")
            require(cli_call_count(fake_cli_log) == 1, "fake CLI called during form prepare")

            prepared_page_status, prepared_page_html = http_text_status(absolute_location(next_base, form_prepare_location))
            require(prepared_page_status == 200, f"prepared feedback page failed: {prepared_page_status}")
            require("Local brief prepared action waiting approval" in prepared_page_html and "Resume approved brief" in prepared_page_html, "prepared feedback page missing approval/resume controls")

            form_approved_status, form_approved_payload = http_json_status("POST", f"{api_base}/api/approvals/{form_approval_id}/approve", {})
            transcripts.append(form_approved_payload)
            require(form_approved_status == 200 and form_approved_payload.get("decision") == "approved", f"form approval failed: {form_approved_status} {form_approved_payload}")

            form_resume_status, form_resume_location = post_form_no_redirect(
                f"{next_base}/workspace/pixel-office/local-brief",
                {
                    "confirm_run": "true",
                    "prepared_action_id": form_prepared_action_id,
                    "prompt_hash": form_prompt_hash,
                    "state_hash": form_state_hash,
                },
            )
            transcripts.append(form_resume_location)
            require(form_resume_status == 303, f"form resume did not redirect: {form_resume_status} {form_resume_location}")
            form_resume_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_resume_location).query)
            require(form_resume_query.get("local_brief_status") == ["live_run"], f"form resume did not report live run: {form_resume_location}")
            require((form_resume_query.get("local_brief_prepared_status") or [""])[0] == "consumed", f"form resume did not consume prepared action: {form_resume_location}")
            require(cli_call_count(fake_cli_log) == 2, "fake CLI should be called once for proxy resume and once for form resume")

            form_status, form_location = post_form_no_redirect(
                f"{next_base}/workspace/pixel-office/local-brief",
                {},
            )
            transcripts.append(form_location)
            require(form_status == 303, f"dry-run local brief form did not redirect: {form_status} {form_location}")
            form_query = urllib.parse.parse_qs(urllib.parse.urlparse(form_location).query)
            require(form_query.get("local_brief_status") == ["dry_run"], f"dry-run local brief form wrong status: {form_location}")
            form_prompt_hash = (form_query.get("local_brief_prompt_hash") or [""])[0]
            form_state_hash = (form_query.get("local_brief_state_hash") or [""])[0]
            require(form_prompt_hash and form_state_hash, f"dry-run local brief form missing hashes: {form_location}")

            feedback_url = absolute_location(next_base, form_location)
            page_status, page_html = http_text_status(feedback_url)
            require(page_status == 200, f"Pixel Office feedback page failed: {page_status} url={feedback_url} body={page_html[:500]}")
            expected = [
                "Local brief controls",
                "Local brief dry-run recorded",
                form_prompt_hash[:16],
                form_state_hash[:16],
                "live brief approval-gated",
            ]
            missing = [item for item in expected if item not in page_html]
            require(not missing, f"Pixel Office local brief page missed {missing}")
            transcripts.append({"page_status": page_status, "page_contains_hash": form_prompt_hash[:16] in page_html})

            transcript_text = json.dumps(transcripts, ensure_ascii=False, sort_keys=True)
            require(not leaked_secret(transcript_text), "Next local brief smoke leaked token-like material")

            print(json.dumps({
                "ok": True,
                "contract": CONTRACT_ID,
                "api_base": api_base,
                "next_base": next_base,
                "proxy_route": "/api/mis/workflows/local-brief",
                "form_route": "/workspace/pixel-office/local-brief",
                "approval_gate": "prepared_action_exact_resume",
                "proxy_prompt_hash": proxy_prompt_hash,
                "proxy_state_hash": proxy_state_hash,
                "prepared_action_id": prepared_action_id,
                "approval_id": approval_id,
                "form_prepared_action_id": form_prepared_action_id,
                "form_prompt_hash": form_prompt_hash,
                "form_state_hash": form_state_hash,
                "live_execution_performed": True,
                "provider_call_count": cli_call_count(fake_cli_log),
                "secret_leaked": False,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
