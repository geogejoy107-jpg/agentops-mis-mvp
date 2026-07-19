#!/usr/bin/env python3
"""Prove the default Worker cadence cannot create a periodic Fleet stale window."""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


AGENT_ID = "agt_worker_heartbeat_cadence_fixture"
WORKSPACE_ID = "local-demo"
BASE_TIME = dt.datetime(2035, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc)
HISTORICAL_HEARTBEAT_TIME = BASE_TIME - dt.timedelta(minutes=30)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class FixedClock:
    def __init__(self) -> None:
        self.offset_sec = 0.0

    def monotonic(self) -> float:
        return self.offset_sec

    def utc_at(self, offset_sec: float | None = None) -> dt.datetime:
        offset = self.offset_sec if offset_sec is None else offset_sec
        return BASE_TIME + dt.timedelta(seconds=offset)


class RecordingClient:
    workspace_id = WORKSPACE_ID
    agent_id = AGENT_ID

    def __init__(self, clock: FixedClock) -> None:
        self.clock = clock
        self.posts: list[dict[str, object]] = []
        self.scoped_observations: dict[tuple[str, str], dict[str, str]] = {}

    def post(self, path: str, payload: dict, timeout: int = 20) -> dict:
        require(path == "/api/agent-gateway/heartbeat", f"unexpected heartbeat path: {path}")
        require(timeout == 20, f"unexpected heartbeat timeout: {timeout}")
        require(payload.get("workspace_id") == WORKSPACE_ID, f"unexpected heartbeat workspace: {payload}")
        require(payload.get("agent_id") == AGENT_ID, f"unexpected heartbeat agent: {payload}")
        timestamp = self.clock.utc_at().isoformat()
        observation = {"last_heartbeat_at": timestamp, "updated_at": timestamp}
        self.scoped_observations[(WORKSPACE_ID, AGENT_ID)] = observation
        self.posts.append({
            "offset_sec": self.clock.offset_sec,
            "timestamp": timestamp,
            "status": payload.get("status"),
            "scoped_observation": dict(observation),
        })
        return {"ledger_recorded": True}


def default_worker_args(worker):
    sentinel = object()
    previous = os.environ.pop("AGENTOPS_WORKER_HEARTBEAT_INTERVAL_SEC", sentinel)
    try:
        return worker.build_parser().parse_args([])
    finally:
        if previous is not sentinel:
            os.environ["AGENTOPS_WORKER_HEARTBEAT_INTERVAL_SEC"] = str(previous)


def fleet_at(
    worker_fleet,
    *,
    now_at: dt.datetime,
    scoped_heartbeat_at: dt.datetime | None,
    historical_heartbeat_at: dt.datetime = HISTORICAL_HEARTBEAT_TIME,
) -> dict:
    heartbeats_by_worker = {}
    if scoped_heartbeat_at is not None:
        scoped_timestamp = scoped_heartbeat_at.isoformat()
        heartbeats_by_worker[(WORKSPACE_ID, AGENT_ID)] = {
            "last_heartbeat_at": scoped_timestamp,
            "updated_at": scoped_timestamp,
        }
    summary = worker_fleet.build_worker_remote_fleet_summary(
        enrollments=[],
        sessions=[{
            "agent_id": AGENT_ID,
            "workspace_id": WORKSPACE_ID,
            "session_state": "active",
            "scopes": sorted(worker_fleet.SERVICE_WORKER_EXECUTION_SCOPES),
            "created_at": BASE_TIME.isoformat(),
            "last_used_at": BASE_TIME.isoformat(),
        }],
        agents_by_id={
            AGENT_ID: {
                "agent_id": AGENT_ID,
                "name": "Heartbeat Cadence Fixture",
                "runtime_type": "openclaw",
                "status": "running",
            },
        },
        heartbeats_by_agent={
            AGENT_ID: {"last_heartbeat_at": historical_heartbeat_at.isoformat()},
        },
        heartbeats_by_worker=heartbeats_by_worker,
        now_dt=now_at,
    )
    service_workers = summary.get("service_workers") or []
    require(len(service_workers) == 1, f"expected one service Worker: {summary}")
    return {"summary": summary, "worker": service_workers[0]}


def main() -> int:
    try:
        from agentops_mis_cli import worker
        from agentops_mis_core import worker_fleet

        args = default_worker_args(worker)
        heartbeat_interval_sec = float(args.heartbeat_interval_sec)
        require(heartbeat_interval_sec > 0, "default heartbeat interval must be positive")

        clock = FixedClock()
        client = RecordingClient(clock)
        poll_offsets: list[float] = []
        heartbeat_results: list[dict] = []
        next_poll_offset = 0.0

        with mock.patch.object(worker.time, "monotonic", clock.monotonic):
            for idle_streak in range(1, 13):
                clock.offset_sec = next_poll_offset
                poll_offsets.append(clock.offset_sec)
                heartbeat_results.append(
                    worker.worker_heartbeat(
                        client,
                        args,
                        "idle",
                        "Fixed heartbeat cadence smoke.",
                    )
                )
                next_poll_offset += worker.backoff_sleep(
                    args.poll_interval,
                    args.idle_backoff_max,
                    idle_streak,
                    args.backoff_factor,
                )

        sent_offsets = [float(post["offset_sec"]) for post in client.posts]
        require(len(sent_offsets) >= 4, f"insufficient heartbeat cycles simulated: {sent_offsets}")
        require(sent_offsets[0] == 0.0, f"first heartbeat was not immediate: {sent_offsets}")
        require(
            sum(bool(result.get("sent")) for result in heartbeat_results) == len(sent_offsets),
            "worker_heartbeat results disagreed with recorded requests",
        )

        historical_only = fleet_at(
            worker_fleet,
            now_at=BASE_TIME,
            scoped_heartbeat_at=None,
        )
        require(historical_only["worker"].get("heartbeat_state") == "stale",
                f"expired unscoped historical heartbeat was not stale: {historical_only}")

        initial_fleet = fleet_at(
            worker_fleet,
            now_at=BASE_TIME,
            scoped_heartbeat_at=BASE_TIME,
        )
        freshness_timeout_sec = float(initial_fleet["worker"].get("heartbeat_timeout_sec") or 0)
        require(freshness_timeout_sec > 0, "Fleet service heartbeat timeout must be positive")
        require(
            freshness_timeout_sec > heartbeat_interval_sec,
            "Fleet freshness timeout must be strictly greater than the default heartbeat request interval",
        )
        require(initial_fleet["worker"].get("heartbeat_state") == "fresh",
                f"fresh scoped observation did not override expired history: {initial_fleet}")
        require(initial_fleet["worker"].get("last_heartbeat_at") == BASE_TIME.isoformat(),
                f"Fleet did not select the scoped observation: {initial_fleet['worker']}")
        require(
            client.scoped_observations.get((WORKSPACE_ID, AGENT_ID), {}).get("last_heartbeat_at")
            == client.posts[-1]["timestamp"],
            "each heartbeat request did not update the scoped Worker observation",
        )
        require(
            len([post for post in client.posts if post.get("scoped_observation")]) == len(sent_offsets),
            "scoped observation update count did not match heartbeat request count",
        )

        request_gaps = [later - earlier for earlier, later in zip(sent_offsets, sent_offsets[1:])]
        max_request_gap_sec = max(request_gaps)
        require(
            max_request_gap_sec <= freshness_timeout_sec,
            f"default polling/backoff produced a heartbeat gap beyond Fleet freshness: {request_gaps}",
        )

        sample_offsets: set[float] = set()
        for earlier, later in zip(sent_offsets, sent_offsets[1:]):
            sample_offsets.update(float(second) for second in range(int(earlier), int(later) + 1))
            sample_offsets.add(max(earlier, later - 0.001))

        stale_samples: list[dict[str, object]] = []
        for sample_offset in sorted(sample_offsets):
            heartbeat_offset = max(offset for offset in sent_offsets if offset <= sample_offset)
            fleet = fleet_at(
                worker_fleet,
                now_at=clock.utc_at(sample_offset),
                scoped_heartbeat_at=clock.utc_at(heartbeat_offset),
            )
            service_worker = fleet["worker"]
            if service_worker.get("heartbeat_state") != "fresh":
                stale_samples.append({
                    "sample_offset_sec": sample_offset,
                    "heartbeat_offset_sec": heartbeat_offset,
                    "state": service_worker.get("heartbeat_state"),
                })
            require(fleet["summary"].get("fresh_service_workers") == 1,
                    f"fresh service Worker count dropped at t={sample_offset}: {fleet['summary']}")
            require(fleet["summary"].get("stale_service_workers") == 0,
                    f"stale service Worker appeared at t={sample_offset}: {fleet['summary']}")

        require(not stale_samples, f"periodic stale window detected: {stale_samples}")

        last_heartbeat_offset = sent_offsets[-1]
        at_timeout = fleet_at(
            worker_fleet,
            now_at=clock.utc_at(last_heartbeat_offset + freshness_timeout_sec),
            scoped_heartbeat_at=clock.utc_at(last_heartbeat_offset),
        )
        after_timeout = fleet_at(
            worker_fleet,
            now_at=clock.utc_at(last_heartbeat_offset + freshness_timeout_sec + 0.001),
            scoped_heartbeat_at=clock.utc_at(last_heartbeat_offset),
        )
        require(at_timeout["worker"].get("heartbeat_state") == "fresh",
                "Fleet freshness boundary changed from inclusive to exclusive")
        require(after_timeout["worker"].get("heartbeat_state") == "stale",
                "Fleet did not mark an actually expired service heartbeat stale")

        print(json.dumps({
            "ok": True,
            "default_heartbeat_interval_sec": heartbeat_interval_sec,
            "default_idle_backoff_max_sec": float(args.idle_backoff_max),
            "fleet_service_freshness_timeout_sec": freshness_timeout_sec,
            "poll_offsets_sec": poll_offsets,
            "heartbeat_request_offsets_sec": sent_offsets,
            "max_heartbeat_request_gap_sec": max_request_gap_sec,
            "fleet_samples_checked": len(sample_offsets),
            "periodic_stale_windows": len(stale_samples),
            "expired_historical_heartbeat_age_sec": (
                BASE_TIME - HISTORICAL_HEARTBEAT_TIME
            ).total_seconds(),
            "historical_only_state": historical_only["worker"].get("heartbeat_state"),
            "fresh_scoped_over_historical_state": initial_fleet["worker"].get("heartbeat_state"),
            "scoped_observation_updates": len(client.posts),
            "boundary_state_at_timeout": at_timeout["worker"].get("heartbeat_state"),
            "boundary_state_after_timeout": after_timeout["worker"].get("heartbeat_state"),
            "service_started": False,
            "database_read": False,
            "credentials_read": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
