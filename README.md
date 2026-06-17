# AgentOps MIS / AI Workforce MIS MVP

这是一个面向“一人公司 / 小团队”的 **AgentOps MIS（AI 数字员工管理信息系统）** 本地原型包。它不是 LLM runtime、不是 agent builder；它是运行在 agent runtime 之上的管理控制面。默认本地优先、外部写入关闭，只有显式确认后才会尝试 Notion 导出或固定安全 runtime probe。

- Agent Registry
- Task Management
- Run Ledger
- Tool Call Ledger
- Approval Workflow
- Organizational Memory
- Evaluation / Quality Gate
- Dashboard
- Audit Log
- OpenClaw local import / probe
- Hermes local health probe
- Agnesfallback dry-run / fixed probe adapter
- Notion External Base dry-run connector
- Template + Base switching preview

## 为什么不是 Next.js 版？

用户指定 Next.js + TypeScript + Tailwind 为优先技术栈。本沙盒环境无法稳定安装 npm 依赖，因此这个包提供一个 **零依赖 Python + SQLite + HTML/JS/CSS 的可运行参考实现**，用于验证 MIS 数据模型、流程和页面信息架构。`docs/CODEX_NEXTJS_HANDOFF_PROMPT.md` 是给本地 Codex/Pro 的 Next.js 版本实现提示词。

## 快速运行

```bash
cd agentops-mis-mvp
python3 server.py --reset
python3 server.py
```

打开：

```text
http://127.0.0.1:8787/dashboard
```

## Figma UI Preview

下载的 Figma/Vite UI 已保存在 `ui/start-building-app/`，用于演示更完整的 AgentOps MIS 产品界面。它是独立前端预览，不替代当前 Python/SQLite demo API。

一条命令启动本地后端和 beta UI：

```bash
python3 scripts/run_local_stack.py --install-ui
```

依赖已经装过时可省略 `--install-ui`：

```bash
python3 scripts/run_local_stack.py
```

也可以手动启动 UI：

```bash
cd ui/start-building-app
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173/
```

构建检查：

```bash
npm run build
```

## 关键验收路径

1. 打开 `/dashboard` 看总览。
2. 去 `/agents` 创建 Agent。
3. 去 `/tasks` 创建任务并分派 Agent。
4. 进入任务详情点击 `Start mock run`。
5. 查看 `/runs` 和 `/tool-calls`。
6. 如果生成高风险 tool call，进入 `/approvals` 批准或拒绝。
7. Run 完成后查看 `/evaluations`。
8. 查看 `/memory` 中的候选组织记忆，并批准/拒绝。
9. 查看 `/audit` 的审计记录。
10. 打开 `/integrations`，运行 OpenClaw 本地导入、OpenClaw 手动 probe、Hermes 手动 probe，并查看 Notion dry-run/export。

## v1.2.1 可录屏复现路径

生成红acted、大规模、可复现 demo 数据：

```bash
python3 scripts/demo_seed_openclaw_redacted.py --reset
```

一键验收本地 API：

```bash
python3 scripts/demo_acceptance.py --start-server
```

验收覆盖：

- Dashboard runtime health 和 Agent performance summary。
- OpenClaw status。
- Hermes/Agnesfallback status、models、dry-run CLI probe。
- Notion status、preview、dry-run export。
- Bases、connectors、template packages、migration preview。
- SQLite 中 audit/runtime/template/bases 基础数据存在。

除 Dify / Notion 之外的本地 runtime live 验收：

```bash
HERMES_ALLOW_REAL_RUN=true \
HERMES_REQUIRE_CONFIRM_RUN=true \
AGNESFALLBACK_GATEWAY_URL=http://127.0.0.1:8642 \
python3 server.py

python3 scripts/local_runtime_acceptance.py \
  --live-openclaw \
  --live-hermes \
  --live-agnesfallback \
  --live-agnesfallback-api \
  --require-hermes-api \
  --require-agnesfallback-api
```

这条验收会跑 Agent Gateway CLI smoke、OpenClaw import/probe、Hermes default gateway fixed run-task、Agnesfallback CLI fixed probe 和 Agnesfallback OpenAI-compatible fixed probe。它不会调用 Dify 或 Notion 写入路径。

## Local live recording mode

默认可复现 demo 仍然是 dry-run，这是 GitHub clone 后最安全的行为。录制本机视频时，如果要展示一次真实 Agnesfallback fixed probe，可以按 `docs/LIVE_DEMO_RUNBOOK.md` 显式开启 live mode：

- 不要把 `HERMES_ALLOW_REAL_RUN=true` 写入 `.env.example`。
- 启动 server 前只在当前 shell 中 `export HERMES_ALLOW_REAL_RUN=true`。
- 调用 probe 时必须传 `{"confirm_run": true}`。
- 录完 `unset HERMES_ALLOW_REAL_RUN`，停止临时 gateway，并确认 `agentops_mis.db` 没有被提交。

## Pixel Office Demo Mode

v1.3 当前默认使用原创 React/CSS Pixel Operating Map，不复制 Star-Office-UI 资产。它把 AgentOps MIS 的 agents / tasks / runs / approvals / memory / audit 状态映射到一个可点击运营大厅。

当前本地 demo 主入口：

- `http://127.0.0.1:19001/workspace/pixel-office`：原生 Pixel Office 前台。顾客可以提交任务、选择 AI 员工，并跳转到正式 MIS 页面。
- `http://127.0.0.1:19001/admin`：MIS 后台管理端。查看控制塔、Run Ledger、Tool Calls、Evaluations、Connectors、External Bases 和 Audit。
- `http://127.0.0.1:19000/workspace`：可选 legacy Star-Office visualizer，仅当你单独启动 Star-Office-UI 时使用。

重要边界：

- Star-Office-UI 只作为课程 demo / 本地录屏视觉层。
- 它不替代 AgentOps MIS Core，MIS 的 SQLite/API 仍是权威账本。
- 本仓库不提交 Star-Office-UI 美术资产。
- Star-Office-UI 资产仅限非商业学习、演示、交流用途；正式发布、商业化、官网宣传、对外产品版本必须换成原创 AgentOps MIS Pixel Office assets。

文档：

- `docs/STAR_OFFICE_UI_DEMO_INTEGRATION.md`
- `docs/PIXEL_OFFICE_ASSET_REPLACEMENT_PLAN.md`

## Agent Gateway Customer Task Demo

v1.4 增加了最小 Agent Gateway/API slice，用于让本机或远程 AI 员工通过 CLI/API/MCP 写入 MIS，而不是让 agent 操作浏览器 UI。

本地 CLI wrapper：

```bash
./scripts/agentops --help
./scripts/agentops login --base-url http://127.0.0.1:8787 --workspace-id local-demo --agent-id agt_local_worker
./scripts/agentops agent register --id agt_local_worker --name "Local Worker" --role "AI Digital Employee"
./scripts/agentops task pull --agent-id agt_local_worker
```

已支持：

```text
agentops login
agentops agent register
agentops agent heartbeat
agentops task pull
agentops task claim
agentops run start
agentops run heartbeat
agentops toolcall record
agentops approval request
agentops memory propose
agentops eval submit
agentops audit emit
```

知识库机器人客户任务演示：

```bash
python3 scripts/run_kb_bot_demo.py
```

它会模拟 AI 团队完成“正式 AI 知识库 / 问答机器人”项目：

- 注册 Project Planner、Document Cleaner、Knowledge Base Builder、Q&A Evaluator、Customer Report Writer。
- 创建并认领任务。
- 写入 Run Ledger、Tool Calls、Runtime Events、Evaluations、Memories 和 Audit。
- 对 Dify / OpenAI File Search / AnythingLLM 外部上传创建 pending approval，不上传原始资料、不保存凭证。

## v1.5 Local Agent Worker Loop

`scripts/agent_worker.py` 是 repo-local worker daemon v0.1。它通过 Agent Gateway API 拉取普通 MIS 任务，认领后调用 adapter，并把 run/tool/eval/audit 写回 MIS。

单轮 mock：

```bash
python3 scripts/agent_worker.py --once --adapter mock --agent-id agt_worker_local
```

单轮 Hermes live adapter：

```bash
python3 scripts/agent_worker.py \
  --once \
  --adapter hermes \
  --confirm-run \
  --agent-id agt_worker_local \
  --hermes-gateway-url http://127.0.0.1:8642
```

单轮 OpenClaw live adapter：

```bash
python3 scripts/agent_worker.py \
  --once \
  --adapter openclaw \
  --confirm-run \
  --agent-id agt_worker_local
```

循环模式：

```bash
python3 scripts/agent_worker.py --adapter mock --poll-interval 5 --max-tasks 10
```

浏览器派发：

- `/workspace/agents` 现在有 “本地 Worker 循环 / Local Worker Loop” 面板。
- 它可以从页面触发一次 `mock`、`Hermes` 或 `OpenClaw` worker run。
- 它也可以启动/停止本地 mock / Hermes / OpenClaw daemon，让 worker 持续拉取普通 MIS 任务。
- 后端会先创建普通 MIS 任务，再调用 `scripts/agent_worker.py --once`，结果写入 Run Ledger、Tool Calls、Evaluations 和 Audit。
- Hermes/OpenClaw 页面派发仍会带显式确认，不改变默认安全策略。

Worker API：

```bash
curl -fsS http://127.0.0.1:8787/api/workers/status | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/workers/local/dispatch-once \
  -H "Content-Type: application/json" \
  -d '{"adapter":"mock"}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/workers/local/start \
  -H "Content-Type: application/json" \
  -d '{"adapter":"mock","poll_interval":2,"max_tasks":0}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/workers/local/stop \
  -H "Content-Type: application/json" \
  -d '{"adapter":"all"}' | jq .
```

边界：

- 不调用 Dify / Notion。
- 不保存完整 prompt、raw response、credentials、transcripts。
- Hermes/OpenClaw 真实执行必须显式传 `--confirm-run`。
- 页面 daemon 控制是本地录屏/自用 supervisor，不是 launchd/systemd 或远程 fleet manager。
- 当前仍是 repo-local worker，不是全局安装包或远程 enrollment 产品。

Dify 可以作为本地或客户服务器上的 agent 工具层，而不是 MIS 的替代品。MIS 负责记录任务、运行、工具、审批、评估和审计；Dify 负责知识库/工作流/问答应用。查看 Dify 当前信任域和配置：

```bash
curl -fsS http://127.0.0.1:8787/api/integrations/dify/status | jq .
```

本地 agent 触发一次安全 dry-run：

```bash
python3 scripts/dify_local_agent_demo.py
```

本地/私有 Dify 真正上传需要显式环境变量和确认：

```bash
export DIFY_API_BASE_URL="http://127.0.0.1:8088/v1"
export DIFY_KB_API_KEY="..."
export DIFY_DATASET_ID="..."
export DIFY_ALLOW_REAL_UPLOAD=true
python3 scripts/dify_local_agent_demo.py --confirm-upload
```

云端或跨信任域 Dify 默认还需要传入已批准的 `approval_id`。不管 dry-run 还是真实上传，MIS 都不会保存 API key 或完整文档正文。

录屏可看：

- `/workspace/pixel-office`
- `/workspace/tasks`
- `/admin/runs`
- `/admin/toolcalls`
- `/workspace/approvals`
- `/admin/evaluations`
- `/admin/audit`

详情见 `docs/AI_KNOWLEDGE_BASE_BOT_DEMO.md`。

Dry-run 预览 payload：

```bash
python3 scripts/push_star_office_state.py
```

本地 Star-Office-UI 跑在 `127.0.0.1:19000` 后，显式发送：

```bash
python3 scripts/push_star_office_state.py --send
```

自定义 endpoint：

```bash
python3 scripts/push_star_office_state.py --base-url http://127.0.0.1:19000 --endpoint set_state --send
```

## 强本地 MVP 集成

页面 `/integrations` 已经支持三个本地优先能力：

- OpenClaw status/import/probe：读取 `~/.openclaw/openclaw.json`、cron jobs、cron run JSONL 和 subagent run index。
- Hermes status/probe：检查本机 Hermes gateway 与 `127.0.0.1:8642`，不可用时记录 health failure，不让 MIS 崩溃。
- Notion export：默认 dry-run，真实导出必须显式 `dry_run:false` + `confirm_export:true`。
- 产品化 Notion 路径：除 parent/database 导出外，也支持 `NOTION_WORKSPACE_PRIVATE_EXPORT=true` 尝试 workspace-level private page；该模式取决于 token 类型，internal integration 通常仍需要指定 parent。
- Agnesfallback：默认只返回 dry-run 计划；真实固定 probe 必须同时设置 `HERMES_ALLOW_REAL_RUN=true` 并在请求体里传 `confirm_run:true`。默认不会加 `--yolo`。
- Base/template switching：提供 Notion、W&B、Plane、Docmost、Mattermost 等外部 base 的能力矩阵和迁移 preview；Agent-MIS local base 仍是权威账本。
- Local AI Workflows：`/workflows` 里提供一个真实本地 AI brief 工作流。它读取 MIS 的结构化安全指标，调用本机 Agnesfallback 生成中文项目/运营简报，并写入 Run Ledger、Runtime Events、Evaluation、Audit 和 Artifact。默认仍是 dry-run；真实运行必须启动 server 前显式设置 `HERMES_ALLOW_REAL_RUN=true`，再用页面确认按钮或 API 传 `confirm_run:true`。

OpenClaw 导入使用确定性 ID，重复导入不会重复造 agents/tasks/runs/evaluations/tool_calls。cron run summary 不存原文，只存脱敏前 200 字和 hash/source metadata。

常用 API：

```bash
curl -fsS http://127.0.0.1:8787/api/integrations/openclaw/status | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/openclaw/import -d '{}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/hermes/probe -d '{}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/hermes/cli-probe -d '{}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/workflows/local-brief -d '{}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/notion/dry-run-export -d '{}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/migration/preview -d '{}' | jq .
curl -fsS http://127.0.0.1:8787/api/dashboard/metrics | jq .
```

本机录屏或自用时执行一次真实 brief：

```bash
export HERMES_ALLOW_REAL_RUN=true
export HERMES_REQUIRE_CONFIRM_RUN=true
python3 server.py
curl -fsS -X POST http://127.0.0.1:8787/api/workflows/local-brief \
  -H "Content-Type: application/json" \
  -d '{"confirm_run":true}' | jq .
```

录完或用完关闭 live mode：

```bash
unset HERMES_ALLOW_REAL_RUN
```

## V1 OpenClaw 实验脚本

本地 v1 目标已经加入一个可重复运行的 OpenClaw 观测实验：

```bash
python3 scripts/openclaw_v1_experiment.py
```

它会读取安全元数据，跑一次 OpenClaw main agent live probe，并把结果写入 MIS 数据库：

- `agt_openclaw_main`
- `agt_openclaw_subagents`
- `tsk_v1_openclaw_observability`
- `run_v1_openclaw_probe_*`

实验报告会写到：

```text
outputs/V1_OPENCLAW_EXPERIMENT.md
```

隐私边界：脚本只记录模型、耗时、token usage、cron/job 计数、subagent run 计数和本机路径引用；不读取 credentials、消息正文或 session transcript 全文。

## 今日交付与汇报材料

- 多线程/分支协作规则：`docs/OPERATING_RULES.md`
- 10 分钟课堂汇报骨架：`docs/PRESENTATION_BRIEF.md`
- 10 分钟中文口播脚本：`docs/CHINESE_PRESENTATION_SCRIPT.md`
- 前后台 demo checklist：`docs/DEMO_CHECKLIST.md`
- 系统规划、分析与设计：`docs/SYSTEM_PLANNING_ANALYSIS_DESIGN.md`
- 能力路线与 Pro 模型分工：`outputs/CAPABILITY_ROADMAP.md`

Notion 连接已预留：

```bash
export NOTION_TOKEN="..."
export NOTION_PARENT_PAGE_ID="..."
python3 server.py
```

如果使用 Notion public integration / OAuth / personal access token，并希望模拟 GPT-style “直接创建到 workspace private area”，可以尝试：

```bash
export NOTION_TOKEN="..."
export NOTION_WORKSPACE_PRIVATE_EXPORT=true
python3 server.py
```

打开 `/integrations` 可以查看 OpenClaw/Hermes/Notion 状态、汇报预览，并执行 dry-run 或实际导出。

## 文件结构

```text
agentops-mis-mvp/
├── server.py                         # 零依赖本地服务 + SQLite API + mock/OpenClaw/Hermes adapters
├── scripts/
│   ├── openclaw_v1_experiment.py      # OpenClaw v1 safe metadata + live probe experiment
│   ├── demo_seed_openclaw_redacted.py  # Synthetic redacted scale data for video demos
│   └── demo_acceptance.py              # Local API acceptance checks
├── static/
│   ├── index.html                     # 单页 UI
│   ├── styles.css
│   └── app.js
├── docs/
│   ├── PRODUCT_UNDERSTANDING.md
│   ├── TECHNICAL_SOLUTION.md
│   ├── COMPETITOR_MATRIX.md
│   ├── ARCHITECTURE.md
│   ├── DATABASE_SCHEMA.md
│   ├── API_SPEC.md
│   ├── PAGE_INFORMATION_ARCHITECTURE.md
│   ├── IMPLEMENTATION_PLAN.md
│   ├── TEST_PLAN.md
│   ├── RISK_REGISTER.md
│   ├── SANDBOX_VS_CODEX.md
│   └── CODEX_NEXTJS_HANDOFF_PROMPT.md
├── sql/
│   └── schema.sql
├── inputs/
│   └── USER_SPEC_PROMPT.md
├── outputs/
│   └── OUTPUT_SUMMARY.md
└── artifacts/
    ├── sample_export_runs.json
    └── sample_export_memories.json
```

## 默认安全策略

- 不含真实 API key。
- 默认不调用外部 API；Notion export 和 Agnesfallback fixed probe 需要显式确认。
- 高风险工具调用默认进入审批。
- 所有关键写操作写入 audit log。
- 预留 `tamper_chain_hash` 字段。
- 禁止隐藏 telemetry；如果未来接入第三方观测系统，必须显式记录并可关闭。
- 不提交 `agentops_mis.db`、credentials、真实 prompts、私聊正文或完整 transcripts。

## 下一步

本地 Codex 应把这个参考实现迁移成 Next.js + TypeScript + Tailwind + SQLite + Prisma/Drizzle：保留数据库模型、API 语义和 mock runtime 行为，再逐步接入 Claude Code / Codex / OpenHands / CrewAI / LangGraph adapter。
