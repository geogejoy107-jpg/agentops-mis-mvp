# AgentOps MIS P0 开源调研与落地交付方案

> 调研日期：2026-06-21  
> 目标仓库：`geogejoy107-jpg/agentops-mis-mvp`  
> 交付分支：`research/p0-open-source-plan`  
> 适用范围：P0-1 Agent Method Block、P0-2 Shared Knowledge Index、P0-3 Real Local Runtime、P0-4 Approval Wall、P0-5 Local Coding Project Template

## 0. 执行摘要

本轮结论不是“再选一个大框架替换现有 MIS”，而是选择成熟项目中最强、最可移植的部分，嵌入 AgentOps MIS 的控制面：

| P0 | 推荐直接采用/兼容 | 推荐借鉴 | P0 暂不采用 |
|---|---|---|---|
| Agent Method Block | GitHub Spec Kit 的 spec/plan/tasks 流程；`AGENTS.md`；Agent Skills `SKILL.md` | Devin Knowledge 的触发式知识、Swarm Skills 的角色/边界描述 | 把整套多 Agent 框架作为主控制面 |
| Shared Knowledge Index | Markdown + 当前 SQLite memories + SQLite FTS5 | Aider Repo Map；Anthropic Contextual Retrieval | 一开始就上独立向量数据库或知识图谱集群 |
| Real Local Runtime | MIS 自有持久化状态机；MCP Python SDK v1；后台 worker；SSE | LangGraph checkpoint/interrupt；A2A Task/Artifact 状态语义；ACP 编码代理接口 | 用 MCP 代替任务调度器；把 LangGraph 变成权威账本 |
| Approval Wall | sandbox + policy + prepared action + action hash + checkpoint resume | Codex 双层安全模型；LangGraph interrupt；OPA/Cedar 的策略分离思想 | “审批通过即把 run 标记 completed” |
| Local Coding Template | Agentless 的定位→修复→验证；Git worktree；独立 verifier | SWE-agent ACI；MetaGPT SOP；Swarm Skills | 默认启动无边界的大型 swarm |

**推荐总体架构：**

```text
Codex / Hermes / OpenClaw / future agents
                 │
                 │ MCP resources + guarded tools
                 ▼
┌──────────────────────────────────────────────────────────┐
│ AgentOps MIS Control Plane（唯一权威状态）               │
│                                                          │
│ Method/Spec Service   Knowledge Service   Policy Service │
│       │                    │                   │          │
│       └────────────── Run Orchestrator ───────┘          │
│                          │                               │
│              run_steps / checkpoints / events            │
│                          │                               │
│              Runtime Adapter Interface                    │
│          Hermes / OpenClaw / Codex / future A2A           │
│                                                          │
│ Task → Plan → Run → Tool → Approval → Artifact            │
│              → Evaluation → Memory → Audit                │
└──────────────────────────────────────────────────────────┘
```

这条路线保留长期目标：科研公司模板、一人公司模板、GPU/实验管理、JiuwenSwarm 类集群、Agent Marketplace、API 计费和企业治理；P0 是这些能力的共同底座，不是对远期设想的删减。

---

## 1. 当前仓库审计

### 1.1 已经值得保留的资产

当前项目并非纯空壳，已经具备：

- Agent、Task、Run、ToolCall、Approval、Memory、Evaluation、Artifact、Audit 等一等对象；
- `runtime_connectors` / `runtime_events`；
- OpenClaw 本地数据导入和探针；
- Hermes/Agnesfallback 健康检查、CLI 固定探针和 OpenAI-compatible 固定探针；
- `HERMES_ALLOW_REAL_RUN` + `confirm_run` 的安全开关；
- 本地 AI brief 的真实调用、Artifact、Evaluation、Audit 闭环；
- `bases`、`base_capabilities`、`template_packages`、`template_bindings` 等未来底座/模板抽象；
- Memory candidate/review/TTL/access tags；
- append-style audit chain hash；
- 默认 dry-run、默认无外部写入的安全边界。

这些应作为迁移约束，不能在重构中被丢弃。

### 1.2 当前阻碍“真正可用”的关键缺口

1. `hermes_run_task()` 明确禁止任意真实任务，只允许固定探针。
2. 审批通过后，`decide_approval()` 直接调用 `complete_run()`，并没有恢复被暂停的真实步骤。
3. `start_mock_run()` 随机生成工具调用，不能证明任务执行能力。
4. `server.py` 是单文件同步实现，长耗时 subprocess/HTTP 调用会占用请求线程。
5. SQLite 连接只启用 foreign keys，尚未设置 WAL、`busy_timeout`、短事务策略。
6. 没有 Agent Plan、run steps、checkpoint、prepared action，因此无法安全暂停/续跑。
7. Memory 有治理字段，但没有执行前检索和 provenance 注入。
8. 没有 `AGENTS.md`、repo skills、feature specs，Codex 很容易忽略既有底座和设计约束。
9. 测试以手工/mock 为主，缺少真实本地运行、审批续跑、知识检索和回归基线。

### 1.3 本轮原则

- **不先重写整个技术栈。** 先在当前 Python/SQLite 原型中跑通真实闭环，再迁移 Next.js/FastAPI/Postgres。
- **MIS 是 source of truth。** LangGraph、MCP、A2A、OpenClaw、Hermes 都是适配层或协议层。
- **先测量再优化。** 所有“更快”必须有 cold start、API p95、检索 p95、first-event latency 和任务完成率基线。
- **优先移植接口和方法，不盲目复制代码。** 复制任何第三方代码前必须记录许可证、版本、来源、修改内容和 SBOM。

---

## 2. P0-1：Agent Method Block

### 2.1 调研结论

#### GitHub Spec Kit

Spec Kit 将开发流程拆为 constitution → specify → plan → tasks → implement，并支持 extensions、presets 和 role-oriented bundles。它适合解决“Agent 不先理解需求、直接写代码”的问题。

采用方式：**移植其工件结构和阶段门，不把 Specify CLI 变成生产运行依赖。** 开发者可选使用 CLI 初始化，但 MIS 必须能自己保存和验证 spec/plan/tasks。

#### AGENTS.md

Codex 会在工作前读取 `AGENTS.md`，并从仓库根目录向当前目录逐层合并，越近的规则优先。它非常适合承载短、稳定、必须每次加载的仓库规则。

采用方式：仓库根目录新增简短 `AGENTS.md`，复杂规则放入 skills/references；必要时在 `runtime/`、`knowledge/` 等目录增加局部 `AGENTS.md`。

#### Agent Skills

Agent Skills 使用包含 `SKILL.md` 的目录，可附带 scripts/references/assets，并通过 progressive disclosure 减少每次注入的上下文。Codex 原生扫描 `.agents/skills`。

采用方式：建立可移植的 MIS skills，而不是把所有说明塞进一个超长 prompt。

#### Devin Knowledge（商业化参照）

Devin 的知识条目使用 trigger description 决定何时召回，并支持文件夹、组织范围、企业范围和仓库绑定。值得借鉴的不是其闭源实现，而是：**每条知识必须有触发条件、范围、开关和更新治理。**

### 2.2 AgentOps MIS 设计

新增目录：

```text
AGENTS.md
.specify/
specs/
  <feature-id>/
    spec.md
    plan.md
    tasks.md
    acceptance.md
.agents/skills/
  inspect-existing-bases/
    SKILL.md
    references/
  implement-mis-feature/
    SKILL.md
    scripts/
  verify-mis-change/
    SKILL.md
  propose-shared-memory/
    SKILL.md
knowledge/
  bases/
  shared/
  runbooks/
```

新增表：

```sql
CREATE TABLE agent_plans (
  agent_plan_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  spec_refs_json TEXT NOT NULL DEFAULT '[]',
  memory_refs_json TEXT NOT NULL DEFAULT '[]',
  base_refs_json TEXT NOT NULL DEFAULT '[]',
  proposed_files_json TEXT NOT NULL DEFAULT '[]',
  execution_steps_json TEXT NOT NULL DEFAULT '[]',
  verification_plan_json TEXT NOT NULL DEFAULT '[]',
  rollback_plan_json TEXT NOT NULL DEFAULT '[]',
  risk_level TEXT NOT NULL,
  approval_required INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  plan_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  approved_at TEXT
);
```

新增 API：

```text
GET  /api/project-context
POST /api/agent-plans
GET  /api/agent-plans/:id
POST /api/agent-plans/:id/validate
POST /api/agent-plans/:id/approve
```

执行门：

```text
没有 acceptance criteria       → 不允许开始真实 run
没有 agent_plan                → 不允许开始真实 run
没有至少一个 spec reference    → 不允许开始真实 run
高风险计划未审批               → waiting_approval
计划 hash 与执行输入不一致      → 计划失效，重新生成
```

### 2.3 P0 验收

- Codex 从仓库根目录启动时能列出已加载的 `AGENTS.md` 和 repo skills；
- 任意真实任务必须产生可审计 `agent_plan`；
- plan 明确列出参考过的 spec、memory、base 和拟修改文件；
- 单个 `SKILL.md` 保持短小，详细资料按需读取；
- instructions 只负责指导，关键约束由 API/state machine/policy 真正执行；
- 对同一任务重复提交相同 plan，使用 plan hash 实现幂等。

### 2.4 不做什么

- 不把所有需求放入一个巨型 system prompt；
- 不认为写了 `AGENTS.md` 就等于完成治理；
- 不在 P0 自动“自我进化”生产 skills，先使用人工 review 的 candidate 流程。

---

## 3. P0-2：Shared Knowledge Index

### 3.1 方案比较

| 方案 | 优点 | 问题 | P0 决定 |
|---|---|---|---|
| 全量上下文 | 简单、零检索误差 | 项目增大后慢、贵、容易污染 | 小任务可作为 fallback |
| SQLite FTS5 | 本地、快、成熟、无独立服务，支持 rank/BM25/snippet/prefix/NEAR | 纯语义能力有限；中文需注意 tokenizer | **P0 主方案** |
| Embeddings + vector | 语义召回好 | 模型/索引依赖、更新和权限更复杂 | P1 作为 hybrid recall |
| Graph memory | 关系和时间推理强 | 工程复杂、延迟和治理成本高 | 研究团队/组织记忆成熟后再上 |
| 远程 RAG SaaS | 快速搭建 | 数据外发、供应商锁定、离线不可用 | P0 不采用 |

Anthropic 的 Contextual Retrieval 说明 BM25 与 embedding 互补，hybrid + reranking 在其测试中能显著降低检索失败；但 reranking 也引入额外延迟和成本。因此 P0 先建立可测量的 lexical baseline，再加可选 hybrid，而不是反过来。

### 3.2 推荐实现

#### 3.2.1 双源数据

```text
文件源：docs/、specs/、knowledge/、AGENTS.md、SKILL.md
账本源：approved memories、artifacts、evaluations、selected run summaries
```

所有检索结果都必须保留：

```text
source_type
source_path / entity_id
content_hash
scope
access_tags
created_at / updated_at
line range 或 chunk range
```

#### 3.2.2 SQLite FTS5

新增普通表保存权威文档元数据，FTS 表只做索引：

```sql
CREATE TABLE knowledge_documents (
  document_id TEXT PRIMARY KEY,
  source_type TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  title TEXT NOT NULL,
  scope TEXT NOT NULL,
  access_tags TEXT NOT NULL DEFAULT '[]',
  content_hash TEXT NOT NULL,
  mtime_ns INTEGER,
  status TEXT NOT NULL,
  indexed_at TEXT NOT NULL
);

CREATE TABLE knowledge_chunks (
  chunk_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  heading_path TEXT,
  content TEXT NOT NULL,
  context_prefix TEXT,
  token_estimate INTEGER,
  content_hash TEXT NOT NULL
);

CREATE VIRTUAL TABLE knowledge_fts USING fts5(
  chunk_id UNINDEXED,
  title,
  heading_path,
  context_prefix,
  content,
  tokenize='trigram'
);
```

说明：P0 使用 trigram 以支持中英文混合、文件路径和标识符的子串匹配；如测试发现英文 BM25 质量受影响，可再增加一个 `unicode61` FTS 表并做 rank fusion。

#### 3.2.3 Aider-style Repo Map

借鉴 Aider Repo Map：不是把整个仓库塞入上下文，而是生成 token-budgeted 的高价值符号地图。

P0 版本：

- Python：优先使用标准库 `ast` 提取类、函数、调用和 import；
- JS/TS：先使用稳定的轻量 parser/regex fallback，后续评估 tree-sitter；
- Git diff 中涉及的文件、被引用最多的符号、与任务关键词匹配的文件优先；
- repo map 按 `repo_head + file hashes + budget` 缓存；
- Agent Plan 必须记录使用过的 repo map 版本。

#### 3.2.4 增量索引

```text
扫描 path → 比较 mtime/hash → 只重切变化文件 → 单事务 upsert → 更新 FTS
```

不能在每次查询时全仓库重扫。

### 3.3 API 与 MCP 资源

```text
POST /api/knowledge/reindex
GET  /api/knowledge/search?q=&scope=&project_id=&limit=
GET  /api/knowledge/documents/:id
GET  /api/knowledge/repo-map?task_id=&budget=
POST /api/knowledge/candidates
```

MCP resources：

```text
mis://project/{project_id}/spec
mis://project/{project_id}/repo-map
mis://task/{task_id}/context
mis://knowledge/search?q=...
mis://memory/{memory_id}
```

MCP tools 只暴露受控写入：

```text
mis_create_agent_plan
mis_propose_memory
mis_report_artifact
mis_request_approval
```

### 3.4 P0 验收

- 10,000 chunks 本地查询 p95 目标 `<100ms`，以实际机器 baseline 为准；
- 文件未变化时重建索引不重复切块；
- 搜索结果返回来源、scope、hash、snippet；
- 未批准 memory 默认不能进入普通 Agent 的权威知识结果；
- access tag 不匹配时不返回内容；
- 检索日志写 audit，但不写入原始密钥或敏感正文；
- 至少建立 30 个真实 MIS 问题的 retrieval test set，记录 Recall@5 / MRR；
- Embedding 只有在 lexical baseline 达不到目标后才进入 P1。

---

## 4. P0-3：Real Local Runtime

### 4.1 协议和框架定位

#### MCP

MCP 适合统一“资源、工具、prompts”的访问，使 Codex、Hermes 和未来 Agent 用同一接口读取 MIS 上下文、申请动作、汇报 Artifact。它不是完整的任务队列和 durable workflow engine。

截至 2026-06-21，官方 Python SDK 的稳定线仍为 v1.x，v2 为 alpha；官方建议依赖方在 v2 稳定前加 `<2` 上限。因此 P0 若引入 SDK，应固定：

```text
mcp>=1.27,<2
```

#### LangGraph

值得借鉴：checkpoint、thread/run identity、interrupt/resume、故障恢复和持久化状态。P0 不要求把全部运行改写为 LangGraph；可以先在 MIS 内实现小型 durable state machine，未来把 LangGraph 作为 adapter。

#### A2A

A2A 适合未来多个独立 Agent 服务之间的发现、Task/Artifact 交换、流式更新和 input-required/auth-required 状态。P0 本地 Hermes/OpenClaw 适配器不必先承担 A2A 复杂度，但状态命名应与其兼容。

#### ACP

ACP 适合 IDE/编辑器与 coding agent 的本地通信。它可作为后续 Codex/其他编码 Agent connector，不应承担 MIS 项目、审批和记忆账本。

### 4.2 推荐状态机

```text
queued
  → preparing_context
  → planned
  → running
  → waiting_approval
  → resuming
  → verifying
  → completed

失败支线：failed / blocked / canceled / timed_out
交互支线：input_required / auth_required
```

新增表：

```sql
CREATE TABLE run_steps (
  run_step_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  step_type TEXT NOT NULL,
  status TEXT NOT NULL,
  input_json TEXT NOT NULL DEFAULT '{}',
  output_json TEXT NOT NULL DEFAULT '{}',
  idempotency_key TEXT NOT NULL,
  started_at TEXT,
  ended_at TEXT,
  error_type TEXT,
  error_message TEXT
);

CREATE TABLE run_checkpoints (
  checkpoint_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  run_step_id TEXT,
  state_json TEXT NOT NULL,
  state_hash TEXT NOT NULL,
  reason TEXT NOT NULL,
  resume_token_hash TEXT,
  created_at TEXT NOT NULL,
  consumed_at TEXT
);
```

### 4.3 Runtime Adapter Contract

```python
class RuntimeAdapter(Protocol):
    def probe(self) -> RuntimeHealth: ...
    def prepare(self, task, context, plan) -> PreparedRun: ...
    def start(self, prepared_run) -> RuntimeHandle: ...
    def stream(self, handle) -> Iterable[RuntimeEvent]: ...
    def cancel(self, handle) -> None: ...
    def resume(self, checkpoint, decision) -> RuntimeHandle: ...
    def collect_artifacts(self, handle) -> list[Artifact]: ...
```

首批适配顺序：

1. `Agnesfallback/HermesAdapter`：在现有 fixed probe 基础上放开受控 arbitrary task；
2. `OpenClawAdapter`：先 read/status/import，再做受控启动；
3. `CodexAdapter`：以 worktree、结构化输出、测试结果和 diff 为核心；
4. LangGraph/CrewAI/JiuwenSwarm：作为 workflow/swarm adapter，而不是核心依赖。

### 4.4 后台执行与响应速度

当前 HTTP 请求内直接 `subprocess.run(timeout=180)` 不适合实际任务。P0 改成：

```text
HTTP POST /runs → 快速写 queued run → enqueue → 立即返回 run_id
worker          → prepare/start/stream/checkpoint
SSE endpoint    → 持续推送 runtime_events
```

P0 可以先用本地进程内可靠队列 + 数据库 claim；但队列权威状态必须在 SQLite，不能只存在内存。进程重启后 worker 能重新 claim `queued/resuming` run。

数据库连接建议：

```sql
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;
```

同时要求短事务、每个 worker 独立连接、写入后快速 commit。

### 4.5 P0 API

```text
POST /api/runs
GET  /api/runs/:id
GET  /api/runs/:id/events
POST /api/runs/:id/cancel
POST /api/runs/:id/input
POST /api/runtime-connectors/:id/probe
POST /api/runtime-connectors/:id/run
GET  /api/runtime-connectors/:id/capabilities
```

原有 `/api/integrations/hermes/run-task` 可以保留为兼容入口，但内部必须转入统一 orchestrator。

### 4.6 P0 验收

- `POST /api/runs` 不等待模型完成即可返回；
- 接受任务后首个 SSE event 目标 `<500ms`；
- 进程重启后 queued/waiting/resuming 状态不丢；
- runtime 超时、退出码、stderr、模型错误分类写入 ledger；
- 不保存完整敏感 prompt/response，只保存 hash、受控摘要和显式 Artifact；
- 真实运行必须生成 plan、run_steps、runtime_events、evaluation、audit；
- 10 个真实本地任务中，基础设施生命周期成功率至少 80%，且零未授权副作用。

---

## 5. P0-4：Approval Wall

### 5.1 当前实现必须修复的问题

现在审批通过会直接将对应工具调用标记 completed 并完成 run。这只能用于 mock，不能用于真实运行。真实系统必须：

```text
prepare action → pause/checkpoint → human decision → resume exact action → execute → verify
```

而不是：

```text
human approve → mark completed
```

### 5.2 最佳实践组合

- 借鉴 Codex：**sandbox 决定技术上能做什么，approval policy 决定何时必须停下来询问。** 两者不能互相替代；
- 借鉴 LangGraph interrupt：暂停状态要持久化，恢复时使用同一 run/thread identity；副作用必须放在 interrupt 之后或保证幂等；
- 借鉴 OPA/Cedar：策略决策与业务执行分离，输入是结构化 principal/action/resource/context；
- MCP tool metadata 只能作为信号，不能作为最终授权依据；服务端仍要独立评估。

### 5.3 Prepared Action

新增表：

```sql
CREATE TABLE prepared_actions (
  prepared_action_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  run_step_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  normalized_args_json TEXT NOT NULL,
  target_resource TEXT,
  risk_level TEXT NOT NULL,
  policy_result_json TEXT NOT NULL,
  action_hash TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  status TEXT NOT NULL,
  expires_at TEXT,
  created_at TEXT NOT NULL,
  executed_at TEXT
);
```

`action_hash` 必须覆盖：

```text
tool_name + normalized_args + target_resource + run_id + step_id + nonce/version
```

审批记录绑定 `prepared_action_id` 和 `action_hash`：

- 参数、目标或版本发生任何变化，原审批立即失效；
- 审批为一次性并带过期时间；
- 批准只会 enqueue/resume 对应 step；
- 拒绝会 block/cancel 对应 step；
- 恢复时再次检查 hash、权限、secret scope 和 policy；
- policy/parser/validator 超时或异常一律 fail closed。

### 5.4 P0 Policy Format

P0 不必立刻部署独立 OPA 服务，可先用版本化 JSON/YAML policy，并保持未来可映射到 OPA/Cedar：

```yaml
version: 1
rules:
  - id: github-push-main
    match:
      tool: github.push
      resource: refs/heads/main
    effect: require_approval
    sandbox: worktree-only
    max_uses: 1

  - id: secret-read
    match:
      tool: secret.resolve
    effect: require_scoped_grant
    never_return_plaintext_to_model: true
```

建议决策：

```text
allow
require_approval
require_auth
require_input
deny
```

### 5.5 Secret 处理

知识库中只保存 `secret_ref` 元数据：env name、用途、允许 Agent、允许 tool、是否需要审批。真实值保存在环境变量、系统 keychain 或后续 vault 中。

Agent 不应获得广域 token；最佳方式是由受控 tool 在服务端使用 secret，并仅返回最小结果。

### 5.6 P0 验收

- 批准后确实执行并恢复对应 step，而不是改状态；
- 修改 action args 后旧批准不能复用；
- 重复点击批准不会重复产生副作用；
- 过期、拒绝、已消费审批无法再次使用；
- destructive/network/secret/write-outside-worktree 默认需要审批或禁止；
- 任何 secret 不出现在 DB、日志、SSE、Artifact、prompt summary；
- 全流程 audit 可还原：谁、何时、批准了哪个 hash、最终执行结果是什么。

---

## 6. P0-5：Local Coding Project Template

### 6.1 调研结论

#### Agentless

其核心流程 localization → repair → patch validation 简单、可解释、成本可控。对当前 P0 很适合，说明不必为了“显得高级”默认启动复杂多代理。

#### SWE-agent

它强调 Agent-Computer Interface：给 Agent 好用、受限、结构化的仓库导航、编辑和测试工具，会直接影响效果。对 MIS 而言，价值在于设计 coding tools，而不是只换模型。

#### MetaGPT

其关键思想是把人类 SOP 编码进角色协作流程，并验证中间产物，减少级联错误。适合未来模板化团队，但 P0 要限制角色数量和执行边界。

#### Git worktree

每个 run 使用独立 worktree，可隔离并行修改、测试和回滚，不污染 main working tree。

#### Swarm Skills / JiuwenSwarm

Swarm Skills 把 roles、workflows、execution bounds 和演化元数据做成可移植资产。它非常符合未来 Agent 公司模板和 Marketplace，但 P0 应先定义兼容字段，不默认开启“自我演化”和无边界 swarm。

### 6.2 默认流程

```text
SPECIFY
  → INDEX / RETRIEVE
  → LOCALIZE
  → PLAN
  → CREATE WORKTREE
  → PATCH
  → TEST
  → REVIEW
  → ARTIFACT
  → EVALUATION
  → MEMORY CANDIDATE
```

默认角色：

```text
Planner/Localizer  —— 找相关文件、底座、约束，生成 plan
Implementer        —— 只在 worktree 内修改
Verifier           —— 不复用 Implementer 的结论，独立运行测试和验收
```

P0 限制：

- 默认最多 2 个并行 Agent；
- 最大迭代 3 轮；
- 每轮必须有 delta、测试结果和停止条件；
- 子代理只能处理可独立验收的子任务；
- 不允许任何 Agent 直接写 main；
- merge/push/dependency install/network access 均由 policy 控制。

### 6.3 Template Package

利用现有 `template_packages`，增加或规范以下 schema：

```json
{
  "scenario": "local-coding-project",
  "roles": ["planner", "implementer", "verifier"],
  "workflow": [
    "specify", "retrieve", "localize", "plan",
    "worktree", "patch", "test", "review", "artifact"
  ],
  "execution_bounds": {
    "max_agents": 2,
    "max_iterations": 3,
    "max_runtime_minutes": 30,
    "max_changed_files": 20
  },
  "approval_policy": {
    "git_push": "required",
    "network": "required",
    "outside_worktree_write": "deny",
    "secret_use": "scoped"
  },
  "quality_gates": {
    "acceptance_criteria_present": true,
    "tests_required": true,
    "diff_required": true,
    "verifier_required": true
  }
}
```

### 6.4 Artifact 契约

每次 coding run 至少输出：

```text
plan.md
repo-map.json
changed-files.json
patch.diff
test-results.json
review.md
run-summary.md
```

可选：screenshots、coverage、benchmark、PR link。

### 6.5 第一条自举任务

用 MIS 开发 MIS：

> 将 `/api/integrations/hermes/run-task` 从固定 dry-run 入口迁移为统一 durable run orchestrator，并通过 Approval Wall 执行一个受控本地任务。

这条任务能同时验证 5 个 P0，而不是只录 UI 演示。

### 6.6 P0 验收

- 每个 run 有独立 worktree 和 branch/ref；
- Agent 先产生 repo map 和 localization 结果，再改代码；
- 实现者与验证者职责分离；
- 测试失败时不产生“completed”假成功；
- 所有修改以 diff Artifact 保存；
- merge/push 不自动进行；
- 可从一个失败 run 复盘所用 spec、知识、计划、工具、审批、测试和结果。

---

## 7. 性能与可靠性计划

“移植开源方法”不必然变快。响应速度要拆成：

```text
控制面延迟
检索延迟
排队延迟
模型首 token 延迟
工具执行延迟
整体任务完成时间
```

### 7.1 PR-00 先建立 baseline

记录：

- cold start；
- `/api/dashboard/metrics` p50/p95；
- knowledge search p50/p95；
- `POST /api/runs` accepted latency；
- first SSE event latency；
- approval-to-resume latency；
- SQLite lock/busy 次数；
- 10 个固定真实任务的完成率和回归结果。

### 7.2 P0 目标值

| 指标 | 初始目标 |
|---|---:|
| 本地 cold start | ≤ 3s |
| 普通控制面 API p95（不含模型） | < 150ms |
| 10k chunks FTS 查询 p95 | < 100ms |
| run accepted → first event | < 500ms |
| approval decision → resumed event | < 1s |
| 未授权副作用 | 0 |
| 真实本地任务基础设施闭环成功率 | ≥ 80% / 10 tasks |

目标必须在目标机器上校准；若 baseline 已更慢，先记录，再以不回退和逐步改善为准。

### 7.3 优化优先级

1. SQLite WAL、busy timeout、索引、短事务；
2. runtime worker 与 HTTP 分离；
3. 增量知识索引；
4. repo map/search 缓存；
5. SSE 增量事件，不轮询整表；
6. 只在检索质量不足时增加 embedding/reranker；
7. 最后再进行框架/语言层重写。

---

## 8. 建议 PR 顺序

```text
PR-00 perf/baseline-and-safety-tests
PR-01 feature/agent-method-block
PR-02 feature/shared-knowledge-index
PR-03 runtime/durable-local-runner
PR-04 feature/approval-resume
PR-05 template/local-coding-project
PR-06 perf/p0-hardening
```

每个 PR 必须可独立验收，不允许一个 PR 同时重写 UI、数据库、runtime 和知识库。

### PR-00

- SQLite WAL/busy timeout；
- 建立测试 runner；
- 保存性能 baseline；
- 把现有 `demo_acceptance.py` 纳入回归。

### PR-01

- `AGENTS.md`；
- `.agents/skills`；
- specs 工件；
- `agent_plans` 表/API/执行门。

### PR-02

- knowledge documents/chunks/FTS；
- 增量索引；
- repo map；
- search tests；
- MCP read-only resources。

### PR-03

- run_steps/checkpoints；
- background worker；
- RuntimeAdapter；
- SSE；
- Hermes controlled arbitrary run。

### PR-04

- prepared_actions；
- action hash；
- policy evaluator；
- checkpoint resume；
- idempotency/security tests。

### PR-05

- local coding template；
- worktree manager；
- planner/implementer/verifier；
- artifacts；
- 第一条自举任务。

### PR-06

- 真实 10-task suite；
- 性能回归；
- failure injection；
- 文档和本地一键启动；
- release candidate checklist。

---

## 9. P0 完成定义

P0 只有满足以下条件才算完成：

1. 用户能在 MIS 创建一个带 acceptance criteria 的真实任务；
2. Agent 工作前读取项目规则、spec、共享知识和开源底座索引；
3. MIS 生成并保存 Agent Plan；
4. Hermes/本地 runtime 在后台真正执行，而不是随机 mock；
5. 高风险动作暂停并生成与具体 action hash 绑定的审批；
6. 批准后从 checkpoint 恢复并真正执行；
7. 运行生成 Artifact、Evaluation、Memory Candidate 和 Audit；
8. Codex 能通过同一 MIS/MCP 上下文开发 MIS 自己；
9. 失败可解释、可重试、可复盘；
10. 无原始密钥泄漏、无未授权副作用。

---

## 10. 后续愿景如何承接

P0 不是终点，后续能力直接复用本设计：

- **科研团队/深度学习实验室**：将 coding template 扩展为 literature → dataset → GPU run → metric → paper artifact；
- **一人公司**：将 roles/workflow/quality gates/approval policy 组合成公司模板；
- **JiuwenSwarm 类集群**：把 `roles + workflow + execution_bounds + evaluation` 升级为 Swarm Skill；
- **Agent Marketplace**：发布的不是一个 prompt，而是带版本、能力、工具权限、评价、成本和执行边界的 Agent/Skill/Template；
- **商业化**：本地优先版验证真实使用，之后再增加 tenant、RBAC、vault、Postgres、BYOC/SaaS 和计费。

---

## 11. 主要参考资料

### 方法块与商业模式

- GitHub Spec Kit: https://github.com/github/spec-kit
- Agent Skills specification: https://agentskills.io/specification
- OpenAI Codex `AGENTS.md`: https://developers.openai.com/codex/guides/agents-md
- OpenAI Codex Skills: https://developers.openai.com/codex/skills
- Devin Knowledge: https://docs.devin.ai/product-guides/knowledge
- Swarm Skills paper: https://arxiv.org/abs/2605.10052

### 检索与记忆

- SQLite FTS5: https://sqlite.org/fts5.html
- Aider Repo Map: https://aider.chat/docs/repomap.html
- Anthropic Contextual Retrieval: https://www.anthropic.com/engineering/contextual-retrieval
- MemGPT: https://arxiv.org/abs/2310.08560
- Mem0: https://arxiv.org/abs/2504.19413
- Zep/Graphiti: https://arxiv.org/abs/2501.13956

### 协议与运行

- MCP introduction: https://modelcontextprotocol.io/docs/getting-started/intro
- MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- A2A: https://github.com/a2aproject/A2A
- ACP: https://agentclientprotocol.com/get-started/introduction
- LangGraph persistence/interrupts: https://docs.langchain.com/oss/python/langgraph/interrupts

### 审批与安全

- Codex agent approvals & security: https://developers.openai.com/codex/agent-approvals-security
- Open Policy Agent: https://www.openpolicyagent.org/docs
- Cedar: https://www.cedarpolicy.com/

### 编码代理工作流

- SWE-agent: https://arxiv.org/abs/2405.15793
- Agentless: https://arxiv.org/abs/2407.01489
- MetaGPT: https://arxiv.org/abs/2308.00352
- Git worktree: https://git-scm.com/docs/git-worktree

---

## 12. 第三方代码移植规则

每个拟移植项目必须建立记录：

```text
source_repository
source_commit_or_release
license
files_or_algorithms_used
modifications
security_review
update_strategy
SBOM entry
```

优先级：

```text
采用标准/协议
  > 复刻算法思想并自行实现
  > 引入稳定 SDK
  > 复制少量有清晰许可证的代码
  > fork/嵌入整个框架
```

任何底座不能绕过 MIS 的 Task/Run/Approval/Artifact/Evaluation/Memory/Audit 权威链路。