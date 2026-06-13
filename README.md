# AgentOps MIS / AI Workforce MIS MVP

这是一个面向“一人公司 / 小团队”的 **AgentOps MIS（AI 数字员工管理信息系统）** 本地原型包。它不是 LLM runtime、不是 agent builder，也不会调用真实外部 API。它实现的是管理控制面：

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

## 强本地 MVP 集成

页面 `/integrations` 已经支持三个本地优先能力：

- OpenClaw status/import/probe：读取 `~/.openclaw/openclaw.json`、cron jobs、cron run JSONL 和 subagent run index。
- Hermes status/probe：检查本机 Hermes gateway 与 `127.0.0.1:8642`，不可用时记录 health failure，不让 MIS 崩溃。
- Notion export：默认 dry-run，真实导出必须显式 `dry_run:false` + `confirm_export:true`。

OpenClaw 导入使用确定性 ID，重复导入不会重复造 agents/tasks/runs/evaluations/tool_calls。cron run summary 不存原文，只存脱敏前 200 字和 hash/source metadata。

常用 API：

```bash
curl -fsS http://127.0.0.1:8787/api/integrations/openclaw/status | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/openclaw/import -d '{}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/hermes/probe -d '{}' | jq .
curl -fsS http://127.0.0.1:8787/api/dashboard/metrics | jq .
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

打开 `/integrations` 可以查看 OpenClaw/Hermes/Notion 状态、汇报预览，并执行 dry-run 或实际导出。

## 文件结构

```text
agentops-mis-mvp/
├── server.py                         # 零依赖本地服务 + SQLite API + mock/OpenClaw/Hermes adapters
├── scripts/
│   └── openclaw_v1_experiment.py      # OpenClaw v1 safe metadata + live probe experiment
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
- 不调用外部 API。
- 高风险工具调用默认进入审批。
- 所有关键写操作写入 audit log。
- 预留 `tamper_chain_hash` 字段。
- 禁止隐藏 telemetry；如果未来接入第三方观测系统，必须显式记录并可关闭。

## 下一步

本地 Codex 应把这个参考实现迁移成 Next.js + TypeScript + Tailwind + SQLite + Prisma/Drizzle：保留数据库模型、API 语义和 mock runtime 行为，再逐步接入 Claude Code / Codex / OpenHands / CrewAI / LangGraph adapter。
