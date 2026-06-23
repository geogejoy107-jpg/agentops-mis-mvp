#!/usr/bin/env python3
"""Create and verify a signed, redacted local audit export."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import hmac
import json
import os
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
DEFAULT_EXPORT_DIR = ROOT / ".agentops_runtime" / "audit_exports"
DEFAULT_KEY_ENV = "AGENTOPS_AUDIT_EXPORT_KEY"
SAFE_ROW_FIELDS = (
    "audit_id",
    "actor_type",
    "actor_id",
    "action",
    "entity_type",
    "entity_id",
    "before_hash",
    "after_hash",
    "metadata_hash",
    "tamper_chain_hash",
    "created_at",
)


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def canonical_json(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def stable_hash(value) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def signing_key(env_name: str) -> tuple[str | None, dict]:
    raw = os.environ.get(env_name)
    if not raw:
        return None, {
            "ok": False,
            "error": "signing_key_required",
            "message": f"Set {env_name} to create or verify a signed audit export.",
            "key_omitted": True,
        }
    return raw, {}


def sign_manifest(manifest: dict, key: str) -> str:
    unsigned = {key_: value for key_, value in manifest.items() if key_ != "signature"}
    return hmac.new(key.encode("utf-8"), canonical_json(unsigned), hashlib.sha256).hexdigest()


def connect_readonly(path: Path) -> sqlite3.Connection:
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def audit_rows(conn: sqlite3.Connection, limit: int) -> list[dict]:
    existing = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }
    if "audit_logs" not in existing:
        return []
    rows = conn.execute(
        """
        SELECT audit_id, actor_type, actor_id, action, entity_type, entity_id,
               before_hash, after_hash, metadata_json, tamper_chain_hash, created_at
        FROM audit_logs
        ORDER BY created_at ASC, audit_id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    safe_rows: list[dict] = []
    for row in rows:
        raw_metadata = row["metadata_json"] or "{}"
        safe_rows.append({
            "audit_id": row["audit_id"],
            "actor_type": row["actor_type"],
            "actor_id": row["actor_id"],
            "action": row["action"],
            "entity_type": row["entity_type"],
            "entity_id": row["entity_id"],
            "before_hash": row["before_hash"],
            "after_hash": row["after_hash"],
            "metadata_hash": sha256_text(raw_metadata),
            "tamper_chain_hash": row["tamper_chain_hash"],
            "created_at": row["created_at"],
        })
    return safe_rows


def build_manifest(export_path: Path, source_db: Path, rows: list[dict], started_at: str) -> dict:
    row_hash = stable_hash(rows)
    chain_head = rows[-1].get("tamper_chain_hash") if rows else None
    return {
        "provider": "agentops-signed-audit-export",
        "operation": "signed_audit_export",
        "contract_id": "signed_audit_export_v1",
        "export_id": export_path.stem,
        "created_at": started_at,
        "source_db_label": source_db.name,
        "export_file": export_path.name,
        "row_count": len(rows),
        "rows_sha256": row_hash,
        "audit_chain_head": chain_head,
        "signature_alg": "hmac-sha256",
        "signed_fields": [
            "contract_id",
            "created_at",
            "export_id",
            "row_count",
            "rows_sha256",
            "audit_chain_head",
        ],
        "safety": {
            "raw_metadata_omitted": True,
            "raw_prompts_omitted": True,
            "raw_responses_omitted": True,
            "tokens_omitted": True,
            "signing_key_omitted": True,
        },
    }


def create_export(args: argparse.Namespace) -> tuple[dict, int]:
    key, missing = signing_key(args.signing_key_env)
    if not key:
        return missing, 2
    source = Path(args.db_path or DEFAULT_DB).expanduser().resolve()
    if not source.exists():
        return {"ok": False, "error": "source_db_not_found", "source_db_label": source.name}, 1
    export_dir = Path(args.export_dir or DEFAULT_EXPORT_DIR).expanduser().resolve()
    export_dir.mkdir(parents=True, exist_ok=True)
    started_at = now_stamp()
    export_path = Path(args.output).expanduser().resolve() if args.output else export_dir / f"agentops-audit-{started_at}.signed.json"
    with connect_readonly(source) as conn:
        rows = audit_rows(conn, max(1, int(args.limit)))
    manifest = build_manifest(export_path, source, rows, started_at)
    manifest["signature"] = sign_manifest(manifest, key)
    export_payload = {
        "manifest": manifest,
        "rows": rows,
    }
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(json.dumps(export_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "ok": True,
        "export_path": str(export_path),
        "manifest": manifest,
        "rows_printed": False,
        "token_omitted": True,
        "signing_key_omitted": True,
    }, 0


def validate_export_payload(payload: dict, key: str) -> tuple[list[str], dict]:
    failures: list[str] = []
    manifest = payload.get("manifest") if isinstance(payload.get("manifest"), dict) else {}
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    if manifest.get("contract_id") != "signed_audit_export_v1":
        failures.append("contract_id_mismatch")
    for index, row in enumerate(rows):
        keys = set(row.keys())
        if keys != set(SAFE_ROW_FIELDS):
            failures.append(f"unsafe_row_fields:{index}")
        if "metadata_json" in row:
            failures.append(f"raw_metadata_present:{index}")
    actual_rows_hash = stable_hash(rows)
    if manifest.get("rows_sha256") != actual_rows_hash:
        failures.append("rows_sha256_mismatch")
    if manifest.get("row_count") != len(rows):
        failures.append("row_count_mismatch")
    expected_signature = sign_manifest(manifest, key)
    if not hmac.compare_digest(str(manifest.get("signature") or ""), expected_signature):
        failures.append("signature_mismatch")
    if (manifest.get("safety") or {}).get("tokens_omitted") is not True:
        failures.append("token_omission_missing")
    if (manifest.get("safety") or {}).get("raw_metadata_omitted") is not True:
        failures.append("raw_metadata_omission_missing")
    return failures, manifest


def verify_export(args: argparse.Namespace) -> tuple[dict, int]:
    key, missing = signing_key(args.signing_key_env)
    if not key:
        return missing, 2
    export_path = Path(args.export).expanduser().resolve()
    if not export_path.exists():
        return {"ok": False, "error": "export_not_found", "export_path": str(export_path)}, 1
    try:
        payload = json.loads(export_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "error": "export_unreadable", "detail": str(exc)}, 1
    failures, manifest = validate_export_payload(payload, key)
    return {
        "ok": not failures,
        "export_path": str(export_path),
        "contract_id": manifest.get("contract_id"),
        "row_count": manifest.get("row_count"),
        "rows_sha256": manifest.get("rows_sha256"),
        "audit_chain_head": manifest.get("audit_chain_head"),
        "signature_alg": manifest.get("signature_alg"),
        "failures": failures,
        "rows_printed": False,
        "token_omitted": True,
        "signing_key_omitted": True,
    }, 0 if not failures else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AgentOps MIS signed audit export utility.")
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="Write a signed, redacted audit export file.")
    export.add_argument("--db-path", default=str(DEFAULT_DB))
    export.add_argument("--export-dir", default=str(DEFAULT_EXPORT_DIR))
    export.add_argument("--output", default="")
    export.add_argument("--limit", type=int, default=500)
    export.add_argument("--signing-key-env", default=DEFAULT_KEY_ENV)
    export.set_defaults(func=create_export)

    verify = sub.add_parser("verify", help="Verify a signed audit export without printing rows.")
    verify.add_argument("--export", required=True)
    verify.add_argument("--signing-key-env", default=DEFAULT_KEY_ENV)
    verify.set_defaults(func=verify_export)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload, status = args.func(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
