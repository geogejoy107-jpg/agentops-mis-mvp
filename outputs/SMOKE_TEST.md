# Smoke Test

Executed in sandbox:

```bash
cd /mnt/data/agentops-mis-package/agentops-mis-mvp
python3 server.py --reset
python3 server.py --host 127.0.0.1 --port 8799
curl http://127.0.0.1:8799/api/agents
```

Result:

- Database reset and seeded successfully.
- Counts after seed:
  - agents: 5
  - tasks: 10
  - runs: 30
  - tool_calls: 40
  - approvals: 8
  - memories: 10
  - evaluations: 12
  - audit_logs: 57
- `/api/agents` returned HTTP 200 with JSON payload.

Note:

- The sandbox test used port 8799 to avoid port conflicts.
- Default README uses port 8787.
