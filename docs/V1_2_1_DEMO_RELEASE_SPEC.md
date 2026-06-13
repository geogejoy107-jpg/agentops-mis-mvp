下面这一版就是**完整目标 + 产品/技术 spec + 可以直接贴给 Codex 跑一晚的提示词**。
定位是：**先做 v1.2.1 可录视频、可复现、能体现研究来源的版本；UI 后面再优化。**

你现在项目已经不是单纯 mock。README 里已经明确写了它是 AgentOps MIS / AI Workforce MIS 本地原型，不是 runtime / agent builder，而是管理控制面，包含 Agent Registry、Task、Run Ledger、Tool Call Ledger、Approval、Memory、Evaluation、Dashboard、Audit Log、OpenClaw import/probe 和 Hermes health probe。 `/integrations` 现在也已经有 OpenClaw、Hermes、Notion 三条线，OpenClaw 读取本地配置/cron/subagent 数据，Hermes 不可用时记录 health failure，Notion 默认 dry-run 且真实导出需要确认。 但文档还落后，比如系统规划文档还把 Hermes probe、OpenClaw cron/subagent import 写成未完成。 Roadmap 也还把 OpenClaw import 当成下一步。 另外你刚刚 push 的 commit `43cd077` 已经把 Notion workspace-private export 模式加进去了，`.env.example` 里出现了 `NOTION_WORKSPACE_PRIVATE_EXPORT=false`，并说明该模式取决于 token 类型，internal integration 通常仍需要 parent。

---

# 一、v1.2.1 总目标

```text
版本名：v1.2.1-demo-release

核心目标：
把当前“能跑的本地 demo”收口成一个有研究支撑、有真实 runtime 连接雏形、有 Notion 外部底座、有模板/底座切换雏形、有 GitHub 复现路径、能直接录 demo 视频的版本。

一句话定位：
AgentOps MIS 不是另一个 agent builder，也不是替代 OpenClaw / Hermes / W&B / Notion / Plane / Docmost 的工具。它是 AI 数字员工与多 Agent 工作流的管理信息系统，通过统一对象模型、Run Ledger、Tool Call Ledger、Approval、Memory、Evaluation、Audit 和 Connector Layer，把不同 runtime、API、开源底座纳入一个可治理、可审计、可切换的 control plane。
```

---

# 二、本轮必须完成的东西

## 1. 文档与现实同步

必须更新：

```text
README.md
docs/SYSTEM_PLANNING_ANALYSIS_DESIGN.md
outputs/CAPABILITY_ROADMAP.md
docs/PRESENTATION_BRIEF.md
docs/DEMO_CHECKLIST.md
docs/API_SPEC.md
```

要修正为：

```text
OpenClaw local import：已完成
OpenClaw cron tasks import：已完成
OpenClaw cron/subagent run metadata import：已完成
OpenClaw manual probe：已完成
Hermes default gateway health probe：已完成，但当前 8642 unavailable 是可记录的 runtime health failure
Agnesfallback CLI/API：用户已手动验证可真实运行，v1.2.1 要产品化为 profile-aware runtime connector
Notion：支持 dry-run、parent/database export、workspace-private export mode
GitHub：不提交本地 SQLite 大数据库；需要 mock seed / local OpenClaw import / redacted demo seed 三条复现路径
```

---

## 2. Hermes / Agnesfallback 从 health probe 升级为 Runtime Connector

当前问题不是 Agnesfallback 不能用，而是：

```text
MIS 当前只检查 default Hermes 127.0.0.1:8642
default LaunchAgent 没开 API_SERVER_ENABLED / API_SERVER_PORT
agnesfallback profile 实际可通过 CLI 和临时 OpenAI-compatible gateway 跑
MIS 还没把 agnesfallback 做成 profile-aware runtime connector
```

v1.2.1 要新增：

```text
Hermes default health probe
Agnesfallback CLI probe
Agnesfallback OpenAI-compatible API probe
Runtime connector 状态记录
真实调用必须显式 confirm
成功/失败都写 run/evaluation/audit
```

---

## 3. Notion 作为 External Base，而不是单纯导出

Notion 这轮要表达成：

```text
Notion as Memory Base
Notion as Task Base
Notion as Template Base
```

Notion 可以替代：

```text
轻量任务库
轻量知识库
模板展示库
部分人工审核前台
组织记忆操作层
```

不能替代：

```text
Run Ledger
Tool Call Ledger
Approval Authority
Audit Authority
Agent IAM
Cost / Quality Authority
Base Switching Authority
```

Notion export 支持三种模式：

```text
page_parent：NOTION_TOKEN + NOTION_PARENT_PAGE_ID
database_parent：NOTION_TOKEN + NOTION_DATABASE_ID
workspace_private：NOTION_TOKEN + NOTION_WORKSPACE_PRIVATE_EXPORT=true
```

---

## 4. Template + Base Switching v0.1

要新增 4 个模板：

```text
AI Software Team Template
AI Experiment Evaluation Template
Content Studio Template
One-Person Company Ops Template
```

每个模板都要有：

```text
默认底座
可替换底座
Agent roles
Task schema
Memory schema
Quality gates
Approval policy
Audit requirements
Recommended runtime
Recommended observability base
```

核心思想：

```text
同一个模板可以跑在我们的本地/改良底座上，也可以切到 Notion / W&B / Plane / Docmost / Mattermost 等外部底座。
但审批、审计、Run Ledger、Tool Call Ledger 永远留在 Agent-MIS Core。
```

---

## 5. GitHub 可复现

必须新增：

```text
scripts/demo_seed_openclaw_redacted.py
scripts/demo_acceptance.py 或 scripts/demo_acceptance.sh
docs/REPRODUCIBLE_DEMO.md
```

复现路径三条：

```text
A. mock seed demo
B. local OpenClaw import demo
C. redacted OpenClaw-scale demo seed
```

脱敏 seed 至少生成：

```text
10 agents
50 tasks
500 runs
800 tool_calls
200 memory_candidates
2000 audit_logs
```

不能包含：

```text
真实路径
真实 prompt
真实 session transcript
credentials
本机用户名
真实 OpenClaw 消息正文
```

---

## 6. Demo 视频脚本

新增：

```text
docs/DEMO_VIDEO_SCRIPT.md
docs/DEMO_CHECKLIST_V1_2.md
```

视频路线：

```text
1. 问题定义：市场不缺 agent builder，缺 cross-runtime / cross-base control plane
2. Dashboard：展示 agents/tasks/runs/audit/runtime health
3. Integrations：OpenClaw ready，Hermes default unavailable 被记录，Agnesfallback 可真实连接，Notion dry-run/workspace export
4. Agents：OpenClaw / Hermes / Agnesfallback agent performance
5. Runs：OpenClaw cron/manual probe run，parent/delegation/child graph
6. Evaluations：quality gates
7. Memory：failure/risk/decision/SOP candidates
8. Audit：所有关键事件可追踪
9. Notion：Notion 是外部底座，不是核心账本
10. Roadmap：Template + Base Switching，W&B/Plane/Docmost，Local Connector，Self-host
```

---

# 三、建议新增/修改文件清单

## 新增文档

```text
docs/RUNTIME_CONNECTOR_SPEC.md
docs/HERMES_AGNESFALLBACK_CONNECTOR_SPEC.md
docs/TEMPLATE_BASE_SWITCHING_SPEC.md
docs/RESEARCH_TO_PRODUCT_TRACEABILITY.md
docs/PRICING_AND_ENTITLEMENT_DRAFT.md
docs/DEMO_VIDEO_SCRIPT.md
docs/DEMO_CHECKLIST_V1_2.md
docs/REPRODUCIBLE_DEMO.md
```

## 新增脚本

```text
scripts/demo_seed_openclaw_redacted.py
scripts/demo_acceptance.py
```

## 可能修改代码

```text
server.py
sql/schema.sql
static/app.js
static/index.html
static/styles.css
.env.example
README.md
docs/API_SPEC.md
docs/SYSTEM_PLANNING_ANALYSIS_DESIGN.md
outputs/CAPABILITY_ROADMAP.md
docs/PRESENTATION_BRIEF.md
docs/DEMO_CHECKLIST.md
```

---

# 四、数据模型 Spec

## 新增 Runtime Connector 表

```sql
CREATE TABLE IF NOT EXISTS runtime_connectors (
    runtime_connector_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    connector_type TEXT NOT NULL,
    profile_name TEXT,
    base_url TEXT,
    binary_path TEXT,
    status TEXT NOT NULL,
    allow_real_run INTEGER NOT NULL DEFAULT 0,
    require_confirm_run INTEGER NOT NULL DEFAULT 1,
    last_health_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

## 新增 Runtime Events 表

```sql
CREATE TABLE IF NOT EXISTS runtime_events (
    runtime_event_id TEXT PRIMARY KEY,
    runtime_connector_id TEXT,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    run_id TEXT,
    task_id TEXT,
    agent_id TEXT,
    model_name TEXT,
    latency_ms INTEGER,
    prompt_hash TEXT,
    input_summary TEXT,
    output_summary TEXT,
    error_message TEXT,
    raw_payload_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(runtime_connector_id) REFERENCES runtime_connectors(runtime_connector_id),
    FOREIGN KEY(run_id) REFERENCES runs(run_id),
    FOREIGN KEY(task_id) REFERENCES tasks(task_id),
    FOREIGN KEY(agent_id) REFERENCES agents(agent_id)
);
```

如果 Codex 觉得为了兼容当前 demo 更稳，也可以先用 `tool_calls + audit_logs` 表达 runtime event，但必须在 `docs/RUNTIME_CONNECTOR_SPEC.md` 里写清楚 v1.2.1 暂时映射和 v2 迁移方案。

---

## 新增 Base / Connector / Switching 表

```sql
CREATE TABLE IF NOT EXISTS bases (
    base_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    category TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS base_capabilities (
    capability_id TEXT PRIMARY KEY,
    base_id TEXT NOT NULL,
    supports_tasks INTEGER DEFAULT 0,
    supports_comments INTEGER DEFAULT 0,
    supports_artifacts INTEGER DEFAULT 0,
    supports_metrics INTEGER DEFAULT 0,
    supports_webhooks INTEGER DEFAULT 0,
    supports_oauth INTEGER DEFAULT 0,
    supports_writeback INTEGER DEFAULT 0,
    supports_permissions INTEGER DEFAULT 0,
    supports_audit_export INTEGER DEFAULT 0,
    supports_realtime_sync INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS connectors (
    connector_id TEXT PRIMARY KEY,
    base_id TEXT,
    provider TEXT NOT NULL,
    auth_type TEXT NOT NULL,
    status TEXT NOT NULL,
    last_checked_at TEXT,
    last_error TEXT,
    dry_run_default INTEGER NOT NULL DEFAULT 1,
    writeback_allowed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS connector_scopes (
    scope_id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL,
    scope_name TEXT NOT NULL,
    granted INTEGER NOT NULL DEFAULT 0,
    required_for TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(connector_id) REFERENCES connectors(connector_id)
);

CREATE TABLE IF NOT EXISTS external_object_links (
    link_id TEXT PRIMARY KEY,
    internal_object_type TEXT NOT NULL,
    internal_object_id TEXT NOT NULL,
    external_provider TEXT NOT NULL,
    external_object_type TEXT NOT NULL,
    external_object_id TEXT,
    external_url TEXT,
    sync_direction TEXT NOT NULL,
    sync_status TEXT NOT NULL,
    last_synced_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    sync_job_id TEXT PRIMARY KEY,
    connector_id TEXT NOT NULL,
    job_type TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(connector_id) REFERENCES connectors(connector_id)
);

CREATE TABLE IF NOT EXISTS sync_events (
    sync_event_id TEXT PRIMARY KEY,
    connector_id TEXT,
    direction TEXT NOT NULL,
    object_type TEXT NOT NULL,
    internal_object_id TEXT,
    external_object_id TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    payload_hash TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(connector_id) REFERENCES connectors(connector_id)
);

CREATE TABLE IF NOT EXISTS field_mappings (
    field_mapping_id TEXT PRIMARY KEY,
    base_id TEXT NOT NULL,
    internal_object_type TEXT NOT NULL,
    internal_field TEXT NOT NULL,
    external_field TEXT NOT NULL,
    transform_rule TEXT,
    required INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS template_packages (
    template_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    scenario TEXT NOT NULL,
    description TEXT,
    default_bases_json TEXT NOT NULL DEFAULT '{}',
    swappable_bases_json TEXT NOT NULL DEFAULT '{}',
    agent_roles_json TEXT NOT NULL DEFAULT '[]',
    task_schema_json TEXT NOT NULL DEFAULT '{}',
    memory_schema_json TEXT NOT NULL DEFAULT '{}',
    quality_gates_json TEXT NOT NULL DEFAULT '{}',
    approval_policy_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS template_bindings (
    binding_id TEXT PRIMARY KEY,
    template_id TEXT NOT NULL,
    base_id TEXT NOT NULL,
    workspace_id TEXT,
    status TEXT NOT NULL,
    mapping_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    FOREIGN KEY(template_id) REFERENCES template_packages(template_id),
    FOREIGN KEY(base_id) REFERENCES bases(base_id)
);

CREATE TABLE IF NOT EXISTS migration_runs (
    migration_run_id TEXT PRIMARY KEY,
    template_id TEXT,
    from_base_id TEXT,
    to_base_id TEXT,
    status TEXT NOT NULL,
    preview_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT,
    FOREIGN KEY(template_id) REFERENCES template_packages(template_id),
    FOREIGN KEY(from_base_id) REFERENCES bases(base_id),
    FOREIGN KEY(to_base_id) REFERENCES bases(base_id)
);
```

---

# 五、API Spec

## Runtime / Hermes / Agnesfallback

```text
GET  /api/integrations/hermes/status
GET  /api/integrations/hermes/models
POST /api/integrations/hermes/probe
POST /api/integrations/hermes/cli-probe
POST /api/integrations/hermes/chat-completion-probe
POST /api/integrations/hermes/run-task
GET  /api/runtime-connectors
GET  /api/runtime-events
```

行为：

```text
/status:
返回 default Hermes 与 agnesfallback 配置状态，包括 profile、gateway_url、mode、api_server_listening、real_run_enabled、requires_confirm_run、last_error。

/models:
调用 OpenAI-compatible /v1/models。失败返回 unavailable，不崩溃。

/probe:
保留 health probe。

/cli-probe:
默认返回 dry-run plan。
只有 HERMES_ALLOW_REAL_RUN=true 且 confirm_run=true 才调用 AGNESFALLBACK_BIN。
固定安全 prompt：请只回复 AGNESFALLBACK_OK，不要解释。

/chat-completion-probe:
默认返回 dry-run plan。
只有 HERMES_ALLOW_REAL_RUN=true 且 confirm_run=true 才调用 AGNESFALLBACK_GATEWAY_URL /v1/chat/completions。
固定安全 prompt：请只回复 HERMES_AGNES_API_OK，不要解释。

/run-task:
MVP 只允许低风险任务或 confirm_run=true 的任务。
必须写 runs / runtime_events / evaluations / audit_logs。
```

---

## Notion External Base

```text
GET  /api/integrations/notion/status
POST /api/integrations/notion/preview
POST /api/integrations/notion/dry-run-export
POST /api/integrations/notion/export-confirmed
POST /api/integrations/notion/import-preview
POST /api/integrations/notion/sync-memory-candidates
POST /api/integrations/notion/sync-tasks
```

行为：

```text
/status:
返回 has_token、parent_page_id、database_id、workspace_private_export、export_mode、dry_run_default、writeback_allowed、last_sync、last_error。

/preview:
返回将导出的 report、tasks、memory candidates，不写外部系统。

/dry-run-export:
只写 sync_event/audit_log，不创建 external_object_link。

/export-confirmed:
只有 confirm_export=true 且配置 token + target 或 workspace_private_export=true 才尝试真实导出。
Notion 403/400 要记录 sync_event/audit_log，不崩溃。

/sync-memory-candidates:
将 memory candidates 映射为 Notion page payload preview。
dry-run 下只写 sync_event/audit_log。

/sync-tasks:
将 Agent-MIS tasks 映射为 Notion database row payload preview。
dry-run 下只写 sync_event/audit_log。
```

---

## Base / Template / Switching

```text
GET /api/bases
GET /api/connectors
GET /api/external-links
GET /api/sync-events
GET /api/template-packages
GET /api/template-bindings
POST /api/migration/preview
```

`/api/migration/preview` 不要真的迁移，只返回：

```text
可迁移对象
不可迁移对象
字段降级
权限变化
需要人工确认的字段
回滚建议
```

---

# 六、完整 Codex 提示词

下面这一整段可以直接贴给 Codex。

```text
你是 geogejoy107-jpg/agentops-mis-mvp 仓库的资深产品工程师、后端工程师、技术写作者。请在当前 Python/SQLite/HTML 本地原型基础上完成 v1.2.1-demo-release。不要迁移 Next.js，不要重写 UI，不要上传本地 SQLite 数据库，不要提交任何真实 token / API key / credentials，不要把真实 OpenClaw prompt、session transcript、个人路径、用户名写入仓库。

当前项目定位：
AgentOps MIS / AI Workforce MIS 是面向 AI 数字员工与多 Agent 工作流的管理信息系统。它不是 LLM runtime，不是 agent builder，也不替代 OpenClaw / Hermes / W&B / Notion / Plane / Docmost。它是 vendor-neutral control plane，用统一对象模型管理 Agent、Task、Run、ToolCall、Approval、Memory、Evaluation、Audit，并通过 adapters/connectors 接入不同 runtime、API、开源底座和外部工具。

当前已知项目状态：
1. 本地 demo 已经能跑。
2. OpenClaw 本地导入已经完成，用户本地约有 6010+ OpenClaw runs、34 cron tasks。
3. OpenClaw manual probe 已成功。
4. Hermes default health probe 已做，当前 127.0.0.1:8642 unavailable 不代表系统失败，而是 runtime health failure 被记录。
5. 用户已经手动验证 agnesfallback CLI 可以实际运行：
   ~/.local/bin/agnesfallback -z '请只回复 AGNESFALLBACK_OK，不要解释。' --yolo
   返回 AGNESFALLBACK_OK。
6. 用户已经手动验证 agnesfallback 临时 API gateway 可运行在 127.0.0.1:8643，/health OK，/v1/models 返回 agnesfallback，/v1/chat/completions 可返回 HERMES_AGNES_API_OK。
7. 当前 MIS 还没有 profile-aware Hermes/Agnesfallback runtime connector，只是 health probe。
8. Notion connector 已经支持 dry-run / preview / confirmed export，并在 commit 43cd077 加入 NOTION_WORKSPACE_PRIVATE_EXPORT=true 模式。
9. GitHub 私有仓库不包含本地 agentops_mis.db，这是安全正确的。
10. UI 后面再优化，本轮主要做架构、API、seed、文档、demo 脚本、可复现。

本轮目标：
完成 v1.2.1-demo-release，包括：
A. 文档与现实同步
B. Hermes/Agnesfallback Runtime Connector v1
C. Notion External Base v1
D. Template + Base Switching v0.1
E. Redacted OpenClaw-scale demo seed
F. Demo video script
G. Research-to-product traceability
H. Pricing/entitlement draft
I. Reproducible GitHub demo instructions

严禁事项：
1. 不要迁移 Next.js。
2. 不要重做 UI。
3. 不要把 agentops_mis.db 加入 git。
4. 不要提交真实 token、API key、secret、个人路径、真实 session transcript。
5. 不要默认真实调用 Hermes/Agnesfallback。
6. 不要默认自动启动 gateway。
7. 不要默认使用 --yolo。
8. 不要强制真实写 Notion。
9. 不要 fork 外部开源项目。
10. 不要做完整 billing 系统。

========================
任务 A：文档同步
========================

更新：
- README.md
- docs/API_SPEC.md
- docs/SYSTEM_PLANNING_ANALYSIS_DESIGN.md
- outputs/CAPABILITY_ROADMAP.md
- docs/PRESENTATION_BRIEF.md
- docs/DEMO_CHECKLIST.md

要求：
1. 把 OpenClaw local import、cron tasks import、cron/subagent run metadata import、manual probe 改为已完成。
2. 把 Hermes default gateway probe 改为已完成 health check；当前 unavailable 是可记录 runtime health failure，不是系统失败。
3. 写清楚 Agnesfallback CLI/API 已由用户手动验证可运行，v1.2.1 目标是产品化 profile-aware runtime connector。
4. 写清楚 Notion 支持三种 export mode：
   - page_parent：NOTION_TOKEN + NOTION_PARENT_PAGE_ID
   - database_parent：NOTION_TOKEN + NOTION_DATABASE_ID
   - workspace_private：NOTION_TOKEN + NOTION_WORKSPACE_PRIVATE_EXPORT=true
5. 说明 workspace_private 更像 GPT-style workspace private page 创建，但取决于 token 类型；internal integration 通常仍需要 parent/database。
6. 说明 GitHub clone 后默认不会看到本地 6000+ OpenClaw runs，因为数据库被安全排除。
7. 补充三种复现路径：
   - mock seed demo
   - local OpenClaw import demo
   - redacted OpenClaw-scale demo seed
8. 添加安全提示：任何在聊天、日志、截图或 commit 中暴露过的 Notion token / API key / gateway credential 都必须 rotate。

========================
任务 B：Hermes / Agnesfallback Runtime Connector v1
========================

新增配置到 .env.example、README、API docs：

HERMES_GATEWAY_URL=http://127.0.0.1:8642
HERMES_PROFILE=default
HERMES_RUNTIME_MODE=health_only
HERMES_ALLOW_REAL_RUN=false
HERMES_REQUIRE_CONFIRM_RUN=true

AGNESFALLBACK_BIN=~/.local/bin/agnesfallback
AGNESFALLBACK_GATEWAY_URL=http://127.0.0.1:8643
AGNESFALLBACK_PROFILE=agnesfallback

配置含义：
- health_only：只做 health/model probe。
- cli_probe：允许通过 CLI 发送固定测试任务。
- openai_compatible：允许通过 /v1/chat/completions 发送固定测试任务。
- 真实运行必须 HERMES_ALLOW_REAL_RUN=true 且请求体 confirm_run=true。
- 默认绝不自动运行 --yolo。
- --yolo 只能作为用户本地可信 demo 的手动示例，不要作为默认代码路径。

新增或补全 API：
- GET  /api/integrations/hermes/status
- GET  /api/integrations/hermes/models
- POST /api/integrations/hermes/probe
- POST /api/integrations/hermes/cli-probe
- POST /api/integrations/hermes/chat-completion-probe
- POST /api/integrations/hermes/run-task
- GET  /api/runtime-connectors
- GET  /api/runtime-events

行为要求：
1. /status 返回 profile、gateway_url、mode、health、api_server_listening、real_run_enabled、requires_confirm_run、last_error。
2. /models 调用 OpenAI-compatible /v1/models；失败时返回 unavailable，不崩溃。
3. /probe 保留 Hermes default gateway health probe。
4. /cli-probe 默认只返回 dry-run plan；只有 HERMES_ALLOW_REAL_RUN=true 且 confirm_run=true 才调用 AGNESFALLBACK_BIN。
5. /cli-probe 固定 prompt 为：请只回复 AGNESFALLBACK_OK，不要解释。
6. /chat-completion-probe 默认只返回 dry-run plan；只有 HERMES_ALLOW_REAL_RUN=true 且 confirm_run=true 才调用 AGNESFALLBACK_GATEWAY_URL /v1/chat/completions。
7. /chat-completion-probe 固定 prompt 为：请只回复 HERMES_AGNES_API_OK，不要解释。
8. /run-task MVP 只允许低风险任务或 confirm_run=true 的任务。
9. 成功和失败都必须写 audit_logs。
10. 真实运行成功时，必须写 runs、runtime_events 或 tool_calls、evaluations、audit_logs。
11. 不保存完整 prompt、完整 response raw body、credentials、token；只保存 prompt_hash、summary、status、duration、model、error_tail。

新增 schema：
runtime_connectors:
- runtime_connector_id
- provider
- connector_type
- profile_name
- base_url
- binary_path
- status
- allow_real_run
- require_confirm_run
- last_health_at
- last_error
- created_at
- updated_at

runtime_events:
- runtime_event_id
- runtime_connector_id
- event_type
- status
- run_id
- task_id
- agent_id
- model_name
- latency_ms
- prompt_hash
- input_summary
- output_summary
- error_message
- raw_payload_hash
- created_at

如果为了兼容当前 demo 不想新增 runtime_events，也可以先把 runtime event 映射到 tool_calls + audit_logs，但必须在 docs/RUNTIME_CONNECTOR_SPEC.md 说明当前映射和 v2 迁移计划。

新增文档：
- docs/RUNTIME_CONNECTOR_SPEC.md
- docs/HERMES_AGNESFALLBACK_CONNECTOR_SPEC.md

文档必须解释：
1. Health probe 与 real runtime run 的区别。
2. default Hermes gateway unavailable 不等于 Hermes/Agnesfallback 不能用。
3. agnesfallback 可以作为 CLI runtime，也可以作为 OpenAI-compatible API runtime。
4. 同一套 OpenAI-compatible adapter 未来可以接 OpenAI、local proxy、vLLM、Ollama-compatible、Agnesfallback gateway。
5. 所有真实调用必须进入 Agent-MIS Run Ledger / Evaluation / Audit，而不是只返回前端。

========================
任务 C：Notion External Base v1
========================

当前 Notion 不能只是 report export，要作为第一种 External Base。

新增或补全 schema：
- bases
- base_capabilities
- connectors
- connector_scopes
- external_object_links
- sync_jobs
- sync_events
- field_mappings
- template_packages
- template_bindings
- migration_runs

要求：
1. 保持向后兼容，不破坏 agents/tasks/runs/tool_calls/approvals/memories/evaluations/audit_logs。
2. server.py 初始化时如果表不存在就创建。
3. seed 至少创建：
   - Agent-MIS Local Task Base
   - Agent-MIS Local Memory Base
   - Agent-MIS Local Template Base
   - Notion External Memory Base
   - Notion External Task Base
   - Notion External Template Base
4. Notion connector 默认 dry_run=true，writeback_allowed=false。
5. Notion 操作必须写 sync_events 和 audit_logs。
6. 不要真实调用 Notion，除非显式配置 token 且请求带 confirm_export=true。
7. 增加 external_object_links，用于把 internal memory/task/template 关联到 notion page/database/data_source。

补全 API：
- GET  /api/integrations/notion/status
- POST /api/integrations/notion/preview
- POST /api/integrations/notion/dry-run-export
- POST /api/integrations/notion/export-confirmed
- POST /api/integrations/notion/import-preview
- POST /api/integrations/notion/sync-memory-candidates
- POST /api/integrations/notion/sync-tasks
- GET  /api/bases
- GET  /api/connectors
- GET  /api/external-links
- GET  /api/sync-events

行为：
1. status 返回 env 配置、export_mode、dry_run 状态、writeback_allowed、last_sync、last_error。
2. preview 返回将被导出的任务、memory candidates、report sections，不写外部系统。
3. dry-run-export 只创建 sync_event/audit_log，不创建 external_object_link。
4. export-confirmed 只有 confirm_export=true 且配置 token + target 或 workspace_private_export=true 时才尝试真实导出。
5. 如果 Notion 返回 403/400，要记录 sync_event/audit_log，不崩溃。
6. sync-memory-candidates 将 approved/candidate memories 映射为 Notion page payload preview，并创建 sync_event。
7. sync-tasks 将 tasks 映射为 Notion database row payload preview，并创建 sync_event。
8. import-preview 不写数据库，只返回字段映射建议。

========================
任务 D：Template + Base Switching v0.1
========================

seed 4 个 template_packages：
1. AI Software Team Template
2. AI Experiment Evaluation Template
3. Content Studio Template
4. One-Person Company Ops Template

每个 template_package 包含：
- scenario
- default_bases_json
- swappable_bases_json
- agent_roles_json
- task_schema_json
- memory_schema_json
- quality_gates_json
- approval_policy_json

必须体现：
1. 同一个模板可以绑定 Agent-MIS Local Base，也可以绑定 Notion/W&B/Plane/Docmost/Mattermost 等 External Base。
2. Agent-MIS Core 永远保留 approval/audit/tool_call/run ledger。
3. 外部底座只承担 task/memory/template/observability 的一部分能力。
4. 切换底座不是无损魔法，要通过 capability detection、field_mapping、migration_preview、sync_events 和 audit_logs 记录。
5. 不可迁移字段必须给出降级策略。

新增 API：
- GET /api/template-packages
- GET /api/template-bindings
- POST /api/migration/preview

新增文档：
- docs/TEMPLATE_BASE_SWITCHING_SPEC.md

文档必须写清楚：
- Managed Base vs External Base
- Canonical Object Model
- Base Adapter interface
- external_object_links
- migration preview
- rollback policy
- 不可迁移字段和降级策略
- 为什么审批/审计/Run Ledger 必须留在 Agent-MIS Core

========================
任务 E：Redacted OpenClaw-scale demo seed
========================

新增：
- scripts/demo_seed_openclaw_redacted.py
- scripts/demo_acceptance.py

demo_seed_openclaw_redacted.py 要生成脱敏规模感数据：
- 至少 10 agents
- 至少 50 tasks
- 至少 500 runs
- 至少 800 tool_calls
- 至少 200 memory_candidates
- 至少 2000 audit_logs

隐私要求：
- 不含真实路径
- 不含真实 prompt
- 不含真实 session transcript
- 不含 credentials
- 不含本机用户名
- 使用 deterministic fake IDs
- 可重复运行，不重复制造无穷重复数据，或有 --reset 参数

demo_acceptance.py 要检查：
- server can start 或 API reachable
- /api/dashboard/metrics works
- runs count > 0
- /api/integrations/openclaw/status works
- /api/integrations/hermes/status works
- /api/integrations/notion/status works
- /api/bases works
- /api/connectors works
- /api/integrations/notion/preview works
- audit_logs count > 0

========================
任务 F：Demo 视频材料
========================

新增：
- docs/DEMO_VIDEO_SCRIPT.md
- docs/DEMO_CHECKLIST_V1_2.md
- docs/REPRODUCIBLE_DEMO.md

DEMO_VIDEO_SCRIPT.md 写 6 分钟中文脚本，路线：
1. Problem: 市场不缺 agent builder，缺跨 runtime / 跨底座 control plane。
2. Dashboard: agents/tasks/runs/audit/runtime health。
3. Integrations:
   - OpenClaw ready/imported/manual probe succeeded
   - Hermes default 8642 unavailable 被记录
   - Agnesfallback CLI/API 已手动验证，v1.2.1 提供 profile-aware connector
   - Notion dry-run、parent/database export、workspace-private export mode
4. Agents: OpenClaw/Hermes/Agnesfallback agent performance。
5. Runs: parent/delegation/child graph + tool calls。
6. Evaluations: quality gates。
7. Memory: failure/risk/decision/SOP candidates。
8. Audit: traceability。
9. Notion: Notion as external memory/task/template base, not core ledger。
10. Roadmap: Template + Base Switching, W&B/Plane/Docmost, Local Connector, Self-host。

视频话术必须包含：
“这里不是说 Hermes 做不到，而是当前 default gateway 没开 API server。我们已经验证 Agnesfallback profile 可以通过 CLI 和 OpenAI-compatible gateway 实际返回结果。v1.2.1 把它从 health probe 升级为 runtime connector，所有真实调用都会进入 run ledger、evaluation 和 audit。”

========================
任务 G：Research-to-product traceability
========================

新增：
- docs/RESEARCH_TO_PRODUCT_TRACEABILITY.md

至少包含以下映射：
1. 市场不缺 agent builder，缺 cross-runtime control plane
→ README / Presentation / Architecture / Connector Layer

2. Observability 不只 prompt/token/cost，需要 delegated-execution ledger
→ runs / tool_calls / approvals / audit_logs / runtime_events

3. Agent IAM：高风险动作必须决策和执行分离
→ approval workflow / risk_level / fail closed / confirm_run / confirm_export

4. 组织记忆不是聊天历史，而是 facts/decisions/commitments/evidence
→ memories scope/type/source/confidence/TTL/review_status

5. HITL 不应处处审批，而是按风险分层
→ high-risk tool calls approval; low-risk auto complete

6. 模板与底座可替换是商业化方向
→ bases / connectors / template_packages / external_object_links / migration preview

7. Notion 是外部底座，不是核心账本
→ Notion Base / sync_events / external_object_links / core ledger remains local

8. Hermes/Agnesfallback 不是 dry-run，产品需要真实 runtime connector
→ runtime_connectors / cli-probe / chat-completion-probe / run ledger

========================
任务 H：Pricing and entitlement draft
========================

新增：
- docs/PRICING_AND_ENTITLEMENT_DRAFT.md

写清楚：
- Free: 内置底座 + mock/local demo
- Pro: OpenClaw/Hermes/Agnesfallback/Notion connector
- Team: 外部 task/memory/workflow bases
- Business: W&B/Langfuse/Helicone/SSO/audit retention
- Enterprise: self-host/BYOC/custom adapter/private connector

定义 entitlement 字段：
- allowed_bases
- allowed_connectors
- max_agents
- max_runs
- max_tool_calls
- audit_retention_days
- memory_storage_limit
- external_sync_frequency
- custom_adapter_allowed
- self_host_allowed
- allow_real_runtime_connectors
- allow_workspace_private_notion_export

========================
最终验收
========================

代码验收：
1. python3 server.py --reset 可以跑。
2. /dashboard 可打开。
3. /api/dashboard/metrics 可返回。
4. /api/integrations/openclaw/status 可返回。
5. /api/integrations/hermes/status 可返回 default + agnesfallback 配置信息。
6. /api/integrations/hermes/cli-probe 未 confirm 时只返回 dry-run plan。
7. /api/integrations/hermes/chat-completion-probe 未 confirm 时只返回 dry-run plan。
8. HERMES_ALLOW_REAL_RUN=true 且 confirm_run=true 时，可以执行固定安全 probe；成功或失败都写 audit。
9. /api/integrations/notion/status 返回 export_mode。
10. /api/bases 返回 local + notion bases。
11. /api/connectors 返回 notion connector 和 runtime connectors。
12. /api/template-packages 返回 4 个模板。
13. /api/migration/preview 返回迁移预览，不真正迁移。
14. scripts/demo_seed_openclaw_redacted.py 可生成规模感数据。
15. scripts/demo_acceptance.py 可通过。

文档验收：
1. README 不再说 Notion 真实写入只能 parent/database。
2. README 说明 workspace_private export 的限制。
3. SYSTEM_PLANNING_ANALYSIS_DESIGN 不再把已完成能力写成未完成。
4. CAPABILITY_ROADMAP 不再把 OpenClaw import 当下一步。
5. DEMO_VIDEO_SCRIPT 可直接照着录。
6. REPRODUCIBLE_DEMO 说明三种复现路径。
7. RESEARCH_TO_PRODUCT_TRACEABILITY 体现来源调研如何落到产品。
8. RUNTIME_CONNECTOR_SPEC 解释 Hermes/Agnesfallback 真实连接。
9. HERMES_AGNESFALLBACK_CONNECTOR_SPEC 解释 default unavailable 与 agnesfallback 可用的区别。
10. 安全提示写明泄露过的 token 必须 rotate。

最后输出：
1. 修改文件列表
2. 新增文件列表
3. 数据库变更说明
4. API 变更说明
5. 本地运行命令
6. Demo 录屏路径
7. 未完成事项
8. 风险和回滚建议
```

---

# 七、明天验收顺序

不要先看页面。先按这个顺序验收：

```text
1. python3 server.py --reset
2. python3 scripts/demo_seed_openclaw_redacted.py
3. python3 server.py
4. curl /api/dashboard/metrics
5. curl /api/integrations/hermes/status
6. curl /api/integrations/hermes/cli-probe，不 confirm，确认是 dry-run
7. curl /api/integrations/notion/status，看 export_mode
8. curl /api/bases
9. curl /api/template-packages
10. curl /api/migration/preview
11. python3 scripts/demo_acceptance.py
12. 打开 docs/DEMO_VIDEO_SCRIPT.md，看能不能直接录
```

---

# 八、最终交付标准

这轮跑完后，项目应该达到：

```text
功能完整度：从 85% → 90%
视频准备：从 70% → 90%
课程汇报完整度：从 75% → 88%
GitHub 可复现：从 50% → 80%
研究落实度：从 50% → 80%
产品叙事统一度：从 60% → 90%
```

这个版本仍然不是最终商业产品，但已经能讲清楚：

```text
为什么它是 MIS
为什么不是 agent builder
为什么 OpenClaw/Hermes/Agnesfallback 是 runtime
为什么 Notion 是外部底座
为什么 W&B/Plane/Docmost 后续也能接
为什么 Run Ledger / Approval / Audit / Memory 是核心护城河
为什么模板 + 可替换底座是商业化方向
```
