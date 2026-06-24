"""In-process read-model cache helpers.

This P1-05 boundary keeps short-TTL aggregate read caching outside the local
HTTP server module. It is intentionally memory-only and dependency-light: no
SQLite, no HTTP server, no provider calls, and no token persistence.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any


IGNORED_QUERY_KEYS = {"_", "bypass_cache", "refresh_cache"}


def stable_hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def jsonable_clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def normalize_workspace_id(value: Any) -> str:
    workspace_id = str(value or "local-demo").strip()
    return workspace_id or "local-demo"


def qs_bool(qs: dict | None, name: str, default: bool = False) -> bool:
    value = ((qs or {}).get(name) or [str(default).lower()])[0]
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def auth_is_bound(auth_ctx: dict | None) -> bool:
    return bool(auth_ctx and auth_ctx.get("mode") in {"agent_token", "agent_session"})


class ReadModelCache:
    def __init__(self, *, ttl_sec: float, max_items: int) -> None:
        self.ttl_sec = float(ttl_sec)
        self.max_items = max(1, int(max_items))
        self._cache: dict[str, dict] = {}
        self._lock = threading.Lock()

    def cache_key(self, name: str, qs: dict | None, headers, auth_ctx: dict | None = None) -> str:
        cache_qs = {
            str(key): [str(item) for item in values]
            for key, values in sorted((qs or {}).items())
            if str(key) not in IGNORED_QUERY_KEYS
        }
        header_workspace = normalize_workspace_id(headers.get("X-AgentOps-Workspace-Id") or "local-demo")
        auth_profile = {
            "mode": (auth_ctx or {}).get("mode") or "local_dev_no_token",
            "workspace_id": normalize_workspace_id((auth_ctx or {}).get("workspace_id") or header_workspace),
            "agent_id": str((auth_ctx or {}).get("agent_id") or headers.get("X-AgentOps-Agent-Id") or ""),
            "scopes": sorted(str(scope) for scope in ((auth_ctx or {}).get("scopes") or [])),
            "bound": auth_is_bound(auth_ctx),
        }
        token_ref = (auth_ctx or {}).get("session_id") or (auth_ctx or {}).get("token_id")
        if token_ref:
            auth_profile["credential_ref_hash"] = stable_hash(str(token_ref))[:16]
        return stable_hash({"name": name, "qs": cache_qs, "auth": auth_profile})

    def prune(self, now: float) -> None:
        expired = [key for key, entry in self._cache.items() if float(entry.get("expires_at") or 0) <= now]
        for key in expired:
            self._cache.pop(key, None)
        while len(self._cache) > self.max_items:
            oldest = min(self._cache.items(), key=lambda item: float(item[1].get("created_at") or 0))[0]
            self._cache.pop(oldest, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def cached(self, name: str, qs: dict | None, headers, producer: Callable[[], Any], auth_ctx: dict | None = None) -> dict:
        ttl = max(0.0, self.ttl_sec)
        bypass = ttl <= 0 or qs_bool(qs, "bypass_cache", False) or qs_bool(qs, "refresh_cache", False)
        key = self.cache_key(name, qs, headers, auth_ctx)
        now = time.time()
        if not bypass:
            with self._lock:
                entry = self._cache.get(key)
                if entry and float(entry.get("expires_at") or 0) > now:
                    payload = jsonable_clone(entry["payload"])
                    age_ms = int((now - float(entry.get("created_at") or now)) * 1000)
                    payload["read_model_cache"] = {
                        "name": name,
                        "status": "hit",
                        "ttl_ms": int(ttl * 1000),
                        "age_ms": max(0, age_ms),
                        "expires_in_ms": max(0, int((float(entry["expires_at"]) - now) * 1000)),
                        "key_hash": key[:16],
                        "token_omitted": True,
                    }
                    return payload

        payload = jsonable_clone(producer())
        status = "bypass" if bypass else "miss"
        if not bypass:
            with self._lock:
                self.prune(now)
                self._cache[key] = {
                    "payload": jsonable_clone(payload),
                    "created_at": now,
                    "expires_at": now + ttl,
                    "name": name,
                }
        payload["read_model_cache"] = {
            "name": name,
            "status": status,
            "ttl_ms": int(ttl * 1000),
            "age_ms": 0,
            "expires_in_ms": 0 if bypass else int(ttl * 1000),
            "key_hash": key[:16],
            "token_omitted": True,
        }
        return payload
