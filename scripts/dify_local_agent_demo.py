#!/usr/bin/env python3
"""
Small local-agent demo for the Dify connector.

Default mode is a dry-run. Live upload requires:
- DIFY_API_BASE_URL, DIFY_KB_API_KEY, DIFY_DATASET_ID
- DIFY_ALLOW_REAL_UPLOAD=true
- --confirm-upload

For live upload, the server first returns a prepared_action_id. Approve the
linked approval, then repeat the request with --prepared-action-id.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def post_json(base_url: str, path: str, payload: dict):
    req = Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=30) as res:
            return json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach AgentOps MIS at {base_url}: {exc.reason}") from exc


def get_json(base_url: str, path: str):
    try:
        with urlopen(base_url.rstrip("/") + path, timeout=10) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        raise RuntimeError(f"{path} failed: {exc}") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a safe local Dify upload demo through AgentOps MIS.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--document-name", default="AgentOps MIS local Dify smoke document")
    parser.add_argument("--text", default="AgentOps MIS local Dify smoke: this text is intentionally small and non-sensitive.")
    parser.add_argument("--dataset-id", default=os.environ.get("DIFY_DATASET_ID", ""))
    parser.add_argument("--approval-id", default="")
    parser.add_argument("--prepared-action-id", default="")
    parser.add_argument("--confirm-upload", action="store_true")
    args = parser.parse_args()

    status = get_json(args.base_url, "/api/integrations/dify/status")
    result = post_json(args.base_url, "/api/integrations/dify/upload-text", {
        "agent_id": "agt_gw_kb_builder",
        "document_name": args.document_name,
        "text": args.text,
        "dataset_id": args.dataset_id or None,
        "approval_id": args.approval_id or None,
        "prepared_action_id": args.prepared_action_id or None,
        "confirm_upload": args.confirm_upload,
    })
    print(json.dumps({
        "dify_status": status,
        "upload_result": result,
        "safety": {
            "script_stores_api_key": False,
            "mis_stores_full_text": False,
            "live_upload_requires_confirm": True,
            "live_upload_requires_prepared_action": True,
        },
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
