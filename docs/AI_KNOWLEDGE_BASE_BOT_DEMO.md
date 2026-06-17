# AI Knowledge Base / Q&A Bot Customer Demo

This is a safe local customer-task demo for the AgentOps MIS v1.5 Agent Gateway slice.

## What It Shows

A customer asks for:

```text
Raw materials
  -> clean Markdown / PDF / DOCX
  -> Dify / OpenAI File Search / AnythingLLM
  -> chunks + embeddings + vector store
  -> AI Q&A / workflow / agent
```

AgentOps MIS turns that request into managed AI-team work:

- AI digital employees register through Agent Gateway.
- Tasks are created and claimed.
- Runs are started and completed.
- Tool calls are recorded.
- External knowledge-base upload is represented as a high-risk approval request.
- Evaluation and memory candidates are written.
- Audit and runtime events prove the work happened.
- A customer-facing delivery artifact is recorded through Agent Gateway, without storing raw documents or credentials.

Dify can run locally or on a customer server. In that model, Dify is the agent's knowledge/workflow tool, while AgentOps MIS remains the control plane and ledger. MIS records only task state, summaries, hashes, connector ids, approval decisions, document ids, evaluations and audit events.

## Run

Start the backend and UI first:

```bash
python3 server.py
cd ui/start-building-app
npm run dev -- --host 127.0.0.1 --port 19001
```

Then run:

```bash
python3 scripts/run_kb_bot_demo.py
```

Acceptance smoke:

```bash
python3 scripts/kb_bot_demo_smoke.py
```

The smoke runs the same customer scenario and checks that `tasks`, `runs`, `tool_calls`, `approvals`, `evaluations`, `memories`, `runtime_events`, `audit_logs`, and `artifacts` all increase.

If `AGENTOPS_API_KEY` is set on the server, pass the same local key:

```bash
AGENTOPS_API_KEY="$AGENTOPS_API_KEY" python3 scripts/run_kb_bot_demo.py
```

## Recording Pages

- `/workspace/pixel-office`: customer dispatch entry and pixel operating map.
- `/workspace/tasks`: created knowledge-base tasks.
- `/admin/runs`: run ledger.
- `/admin/toolcalls`: tool calls and external upload plan.
- `/workspace/approvals`: pending approval for Dify/OpenAI/AnythingLLM upload.
- `/admin/evaluations`: quality gate evidence.
- `/admin/audit`: tamper-chain audit records.
- Task or run detail: customer delivery artifact summary.

## Safety Boundaries

- No raw customer documents are uploaded.
- No credentials are stored.
- Artifact records store title, summary, URI/hash metadata only; they do not store the full customer source corpus.
- No full private chats or transcripts are written to MIS.
- Local/private Dify may run with explicit `DIFY_ALLOW_REAL_UPLOAD=true` plus `confirm_upload`; cloud or cross-domain ingestion stays pending until a human approval exists.

## Optional Local Dify Agent Demo

Check local Dify connector status:

```bash
curl -fsS http://127.0.0.1:8787/api/integrations/dify/status | jq .
```

Dry-run a local agent upload:

```bash
python3 scripts/dify_local_agent_demo.py
```

Live local/private upload:

```bash
export DIFY_API_BASE_URL="http://127.0.0.1:8088/v1"
export DIFY_KB_API_KEY="..."
export DIFY_DATASET_ID="..."
export DIFY_ALLOW_REAL_UPLOAD=true
python3 scripts/dify_local_agent_demo.py --confirm-upload
```

For `cloud_dify` or cross-trust-domain Dify, pass an approved approval id:

```bash
python3 scripts/dify_local_agent_demo.py --confirm-upload --approval-id ap_...
```
