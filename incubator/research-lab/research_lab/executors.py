from __future__ import annotations

import asyncio
import os
import signal
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    command: Sequence[str]
    cwd: Path
    env: Mapping[str, str]
    stdout_path: Path
    stderr_path: Path
    timeout_seconds: float


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: str
    exit_code: int | None
    error_summary: str | None
    pid: int | None
    metadata: dict[str, Any] = field(default_factory=dict)
    remote_job_ref: str | None = None


class LocalExecutor:
    name = "local"

    async def run(self, request: ExecutionRequest, *, on_started: Callable[[int], None] | None = None) -> ExecutionResult:
        process: asyncio.subprocess.Process | None = None
        try:
            request.stdout_path.parent.mkdir(parents=True, exist_ok=True)
            request.stderr_path.parent.mkdir(parents=True, exist_ok=True)
            with request.stdout_path.open("wb") as stdout_file, request.stderr_path.open("wb") as stderr_file:
                process = await asyncio.create_subprocess_exec(
                    *request.command,
                    cwd=str(request.cwd),
                    env=dict(request.env),
                    stdout=stdout_file,
                    stderr=stderr_file,
                    start_new_session=(os.name != "nt"),
                )
                if on_started is not None and process.pid is not None:
                    on_started(int(process.pid))
                try:
                    exit_code = await asyncio.wait_for(process.wait(), timeout=request.timeout_seconds)
                except TimeoutError:
                    await self._terminate(process)
                    return ExecutionResult("timed_out", process.returncode, f"timeout after {request.timeout_seconds:g} seconds", process.pid)
                if exit_code == 0:
                    return ExecutionResult("completed", 0, None, process.pid)
                return ExecutionResult("failed", exit_code, f"process exited with code {exit_code}", process.pid)
        except FileNotFoundError as exc:
            return ExecutionResult("failed", None, f"command not found: {exc.filename}", process.pid if process else None)
        except OSError as exc:
            return ExecutionResult("failed", None, f"process start failed: {exc}", process.pid if process else None)

    @staticmethod
    async def _terminate(process: asyncio.subprocess.Process) -> None:
        if process.returncode is not None:
            return
        if os.name != "nt" and process.pid:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        else:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            if os.name != "nt" and process.pid:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    return
            else:
                process.kill()
            await process.wait()
