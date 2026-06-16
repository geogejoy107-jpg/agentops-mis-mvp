# AI Knowledge Base / Q&A Bot Customer Demo

This is a safe local customer-task demo for the AgentOps MIS v1.4 Agent Gateway slice.

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

## Safety Boundaries

- No raw customer documents are uploaded.
- No credentials are stored.
- No full private chats or transcripts are written to MIS.
- External Dify/OpenAI File Search/AnythingLLM ingestion stays pending until a human approval exists.
