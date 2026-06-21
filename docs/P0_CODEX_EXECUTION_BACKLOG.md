# AgentOps MIS P0 Codex 执行任务书

> 配套文档：`docs/P0_OPEN_SOURCE_RESEARCH_AND_DELIVERY_PLAN.md`  
> 执行原则：一项 PR 一个可验收增量；禁止一次性重写整个项目。

## 0. Codex 总工作约定

在开始任何实现任务之前，Codex 必须：

1. 阅读根目录 `README.md`、`docs/TECHNICAL_SOLUTION.md`、`docs/RISK_REGISTER.md`、本任务书和对应 feature spec；
2. 搜索并阅读当前实现，不得假设接口不存在；
3. 输出“现状证据、拟复用底座、拟改文件、风险、验证计划”；
4. 保留现有本地零依赖 demo 的可运行性，除非对应 PR 的 spec 明确增加依赖；
5. 不删除 OpenClaw/Hermes/Notion/base/template/audit/memory 等已有能力；
6. 不把 Star-Office-UI 变成权威账本；
7. 不在数据库、日志、测试 fixture 或 Artifact 中写入真实 secret；
8. 所有写状态操作具有幂等键并写 audit；
9. 所有第三方代码复用先检查许可证并记录 source commit/release；
10. 每个 PR 给出测试、性能前后对比、剩余风险和回滚方式。

每个 PR 开始时必须生成如下计划：

```json
{
  "task_understanding": "...",
  "current_code_evidence": ["file:line or symbol"],
  "referenced_specs": ["..."],
  "referenced_bases": ["..."],
  "proposed_files": ["..."],
  "schema_changes": ["..."],
  "risk_level": "low|medium|high",
  "approval_required": false,
  "verification_plan": ["..."],
  "rollback_plan": ["..."]
}
```

---

## PR-00：`perf/baseline-and-safety-tests`

### 目标

建立不可伪造的性能/安全/生命周期基线，并解决 SQLite 并发的低成本问题。此 PR 不增加新产品功能。

### 实现范围

- 把 DB 初始化集中为一个函数；
- 增加：

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;
```

- 新增自动化测试 runner，至少覆盖：
  - server startup；
  - create agent/task；
  - mock run lifecycle；
  - approval reject；
  - memory review；
  - audit write；
  - Local AI brief dry-run；
- 把现有 `demo_acceptance.py` 纳入回归；
- 新增 benchmark 脚本：
  - cold start；
  - dashboard API p50/p95；
  - 100 次并发只读；
  - 20 次并发短写；
- 记录 baseline 到 `docs/performance/P0_BASELINE.md`。

### 禁止事项

- 不迁移 Web 框架；
- 不改 UI 视觉；
- 不引入向量库；
- 不声称模型调用速度得到优化，除非有数据。

### 验收

```text
python3 server.py --reset
python3 demo_acceptance.py
python3 tests/run_all.py
python3 benchmarks/run_baseline.py
```

均成功；DB busy/lock 错误为 0；现有手工演示链路不回退。

### Codex 指令

```text
请在 agentops-mis-mvp 中实现 PR-00 perf/baseline-and-safety-tests。
先审计 db()、seed()、ThreadingHTTPServer、demo_acceptance.py 和所有长事务。
只做数据库运行参数、自动化测试与性能基线，不增加产品功能，不迁移框架。
必须保持现有 API 和 demo 可用；输出基线数据和所有改动的回滚方式。
```

---

## PR-01：`feature/agent-method-block`

### 目标

让 Codex/Hermes/OpenClaw 在真实执行前先读取规范、参考已有底座、生成结构化 plan；避免凭空重写。

### 参考底座

- GitHub Spec Kit：constitution/spec/plan/tasks；
- Codex `AGENTS.md` 层级规则；
- Agent Skills `SKILL.md` progressive disclosure；
- Devin Knowledge trigger/scope 思路。

### 文件结构

```text
AGENTS.md
specs/README.md
specs/p0-local-usable-v0/
  spec.md
  plan.md
  tasks.md
  acceptance.md
.agents/skills/
  inspect-existing-bases/SKILL.md
  implement-mis-feature/SKILL.md
  verify-mis-change/SKILL.md
  propose-shared-memory/SKILL.md
knowledge/bases/README.md
knowledge/shared/README.md
knowledge/runbooks/README.md
```

### 数据库

新增 `agent_plans`；迁移必须幂等，不能删除现有表或 seed data。

### API

```text
GET  /api/project-context
POST /api/agent-plans
GET  /api/agent-plans/:id
POST /api/agent-plans/:id/validate
POST /api/agent-plans/:id/approve
```

### 关键规则

- real run 必须引用有效 plan；
- plan 必须引用 acceptance criteria；
- plan hash 绑定 task、spec refs、memory refs、base refs、文件列表和步骤；
- 高风险 plan 必须先批准；
- 相同输入重复提交返回同一 plan 或明确版本，不制造重复记录；
- instructions 不作为安全强制点，API 必须重新校验。

### 测试

- 缺 acceptance criteria → validation fail；
- 缺 spec ref → validation fail；
- high-risk unapproved plan → run rejected/waiting；
- 修改 plan 内容 → hash 变化，旧批准失效；
- plan create/validate/approve 全部有 audit。

### Codex 指令

```text
请实现 PR-01 feature/agent-method-block。
不要自行发明一套巨型 prompt；采用 AGENTS.md + Agent Skills + spec/plan/tasks 工件。
在当前 SQLite schema 增加 agent_plans，并在真实 run 入口建立强制验证门。
先创建最小文档和四个 repo skills，再完成 API 和测试。
不得删除或绕过现有 Task/Run/Audit 模型。
```

---

## PR-02：`feature/shared-knowledge-index`

### 目标

让所有本地 Agent 使用同一个、可治理、可追溯、低延迟的项目知识入口。

### P0 技术选择

- 权威内容：Markdown + approved memories + selected artifacts/evaluations；
- 索引：SQLite FTS5；
- 中文/路径/标识符：优先 trigram；
- 代码上下文：Aider-style token-budgeted Repo Map；
- 不引入远程 SaaS；
- 不在本 PR 引入 embedding/vector DB。

### 数据库

新增：

```text
knowledge_documents
knowledge_chunks
knowledge_fts (FTS5)
knowledge_index_runs
knowledge_queries
```

### 索引来源白名单

```text
AGENTS.md
docs/**/*.md
specs/**/*.md
knowledge/**/*.md
.agents/skills/**/SKILL.md
approved memories
selected artifacts/evaluations
```

必须排除：

```text
.env*
*.pem
*.key
auth.json
credential/token/secret 文件
.git/
agentops_mis.db
artifacts 中未显式允许索引的原始输出
```

### API

```text
POST /api/knowledge/reindex
GET  /api/knowledge/index-status
GET  /api/knowledge/search
GET  /api/knowledge/documents/:id
GET  /api/knowledge/repo-map
POST /api/knowledge/candidates
```

### Repo Map

- Python 使用 `ast`；
- 输出文件、类、函数、import、调用/引用摘要；
- 以 task query、git diff、引用度和 token budget 排序；
- 缓存键包含 git head、相关文件 hash 和 budget；
- 首版不要求完整解析所有语言，但必须明确 fallback 和未覆盖率。

### 检索结果契约

```json
{
  "query_id": "...",
  "results": [
    {
      "source_ref": "...",
      "title": "...",
      "snippet": "...",
      "score": 0.0,
      "scope": "project",
      "access_tags": [],
      "content_hash": "...",
      "chunk_id": "..."
    }
  ]
}
```

### MCP Server

引入官方 MCP Python SDK v1 时固定 `mcp>=1.27,<2`。第一版只暴露 read-only resources 和四个受控 MIS tools；MCP 不直接读 DB 文件，而调用 service layer。

### 测试与评估

- 创建 30 个真实 MIS 查询及期望文档；
- 记录 Recall@5、MRR、p95；
- 10k chunks p95 目标 `<100ms`；
- 重建索引对未变文档为 no-op；
- candidate/rejected memory 不进入默认权威结果；
- access tag 隔离测试；
- secret fixture 不可被检索。

### Codex 指令

```text
请实现 PR-02 feature/shared-knowledge-index。
使用当前 SQLite 加 FTS5，先做快速、可测、增量的本地 lexical index；不要直接上向量数据库。
借鉴 Aider Repo Map 的“高价值符号 + token budget”思想，但不要复制整个 Aider。
所有结果必须带来源、scope、hash 和 snippet；所有查询写受控 audit。
增加 MCP read resources，但 MCP 只能调用 service layer，不能绕过权限直接读数据库。
```

---

## PR-03：`runtime/durable-local-runner`

### 目标

将当前固定 probe/dry-run 升级为可持久化、后台执行、可恢复的真实本地 runtime，同时保持默认安全。

### 当前必须保留

```text
HERMES_ALLOW_REAL_RUN
HERMES_REQUIRE_CONFIRM_RUN
confirm_run
redaction
runtime_connectors
runtime_events
run/evaluation/audit/artifact
```

### 模块拆分

```text
agentops_mis/
  db.py
  services/
    runs.py
    runtime_events.py
  runtimes/
    base.py
    hermes.py
    openclaw.py
  workers/
    local_worker.py
  api/
    runs.py
```

允许循序拆分，不能一次改变所有 API。

### 状态机

```text
queued → preparing_context → planned → running
       → waiting_approval → resuming → verifying → completed
       → failed / blocked / canceled / timed_out
       → input_required / auth_required
```

### 数据库

新增 `run_steps`、`run_checkpoints` 和 DB-backed claim 字段。worker 不能只依赖内存 Queue。

### Adapter Contract

```text
probe
prepare
start
stream
cancel
resume
collect_artifacts
```

### Hermes 第一阶段

- arbitrary prompt/task 只能在：
  - connector health available；
  - env allow true；
  - request confirm true；
  - valid approved plan；
  - risk/policy pass；
  时运行；
- HTTP handler 只创建 run 并 enqueue；
- worker 执行 CLI/API；
- stdout/stderr 逐步 redaction；
- timeout/exit code/error 写结构化 event；
- 不默认保存完整 transcript。

### SSE

```text
GET /api/runs/:id/events
```

必须支持 reconnect（使用 event id/sequence），不能只能展示当前最后状态。

### 恢复

进程启动时扫描：

```text
queued
resuming
running but lease expired
```

按 lease/idempotency 规则恢复或标记失败，不能重复副作用。

### 测试

- fake runtime adapter；
- slow adapter 不阻塞普通 API；
- worker crash/restart；
- timeout/cancel；
- duplicate submit；
- invalid plan；
- runtime unavailable；
- SSE reconnect；
- 真实 Agnesfallback/Hermes smoke test 可由环境变量选择执行。

### Codex 指令

```text
请实现 PR-03 runtime/durable-local-runner。
不要把 MCP 当任务队列，也不要让 LangGraph 成为权威数据库。
在 MIS 中实现小型 durable state machine、DB-backed worker 和 RuntimeAdapter。
将现有 /api/integrations/hermes/run-task 兼容转入统一 orchestrator；默认仍 dry-run/fail-closed。
先用 fake adapter 完成自动化测试，再增加可选真实 Hermes smoke test。
```

---

## PR-04：`feature/approval-resume`

### 目标

将 Approval Wall 从 mock 状态变更升级为真正的“暂停、审批、恢复、执行、验证”。

### 数据模型

新增：

```text
prepared_actions
approval_events（或给 approvals 增加 append-only event 表）
```

给 approvals 增加：

```text
prepared_action_id
action_hash
policy_version
expires_at
consumed_at
decision_reason
```

### 安全模型

```text
sandbox capability + policy decision + explicit approval
```

三层全部通过才执行。

### Action Hash

规范化并 hash：

```text
tool + args + resource + run + step + policy version + nonce
```

批准后执行前再次计算；不一致则拒绝。

### 续跑

批准：

```text
approval approved
→ checkpoint consumed atomically
→ run status=resuming
→ enqueue same step
→ execute prepared action
→ verify result
```

拒绝：

```text
approval rejected
→ prepared action blocked
→ step blocked
→ run/task 根据策略 blocked/canceled
```

### 幂等

- prepared action 有 idempotency key；
- checkpoint token 一次性消费；
- 批准按钮重复提交只返回当前状态；
- 对非幂等外部调用使用 provider idempotency key 或执行前后 reconcile。

### P0 Policy Engine

先实现版本化 YAML/JSON，不部署独立 OPA；接口使用 principal/action/resource/context，方便 P1 切换 OPA/Cedar。

### 默认策略

```text
read project files              allow
write inside isolated worktree  allow/record
network                         require_approval
install dependency              require_approval
github push/merge               require_approval
write main worktree             deny
read raw secret                 deny
use scoped secret via tool      require scoped grant
email/database destructive      require_approval or deny
```

### 测试

- approve 后真实恢复；
- reject 后不执行；
- 参数篡改；
- approval expired；
- approval replay；
- worker crash during resume；
- policy error/timeout fail closed；
- side effect counter 证明恰好执行一次；
- secret redaction。

### Codex 指令

```text
请实现 PR-04 feature/approval-resume。
首先删除“审批通过直接 complete_run”的真实运行路径，但保留 mock 兼容测试。
新增 prepared action、action hash、checkpoint resume 和一次性消费。
借鉴 Codex 的 sandbox+approval 双层模型以及 LangGraph interrupt 的幂等约束。
任何解析、策略或恢复异常必须 fail closed；测试必须证明副作用只执行一次。
```

---

## PR-05：`template/local-coding-project`

### 目标

让 AgentOps MIS 用自身控制面完成一次真实软件工程任务，作为 P0 自举验收。

### 工作流

```text
SPECIFY
→ RETRIEVE
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

### 参考方法

- Agentless：localization → repair → patch validation；
- SWE-agent：为 Agent 设计结构化 ACI；
- MetaGPT：SOP 和中间产物验证；
- Git worktree：运行隔离；
- Swarm Skills：roles/workflow/execution_bounds 元数据兼容。

### 默认角色

```text
planner/localizer
implementer
verifier
```

默认只运行 implementer + verifier；planner 可由同一 Agent 的独立阶段完成。只有任务可独立切分时才启用第二 implementer。

### Worktree Manager

- 路径：`.agentops/worktrees/<run_id>`；
- branch：`agentops/<task_id>/<run_id>`；
- 所有写入限定在 worktree；
- main branch 不自动修改；
- run 完成后保留或按 retention policy 清理；
- worktree path 和 commit/diff 写 Artifact。

### Coding Tools

最小结构化工具：

```text
repo_tree
repo_map
read_file_range
search_code
apply_patch
run_test_command
show_diff
collect_artifact
```

工具输出必须可截断、可分页、有 exit status；禁止让 Agent 依赖无结构的超长 shell transcript。

### Artifact

```text
plan.md
repo-map.json
localization.json
patch.diff
changed-files.json
test-results.json
review.md
run-summary.md
```

### 第一条自举任务

```text
任务：把任意 Hermes run-task 接入 durable orchestrator，并验证一次低风险本地项目简报/代码审计任务。
验收：真实 run、SSE、Artifact、Evaluation、Memory Candidate、Audit 全链路存在。
```

### 质量门

- 有 acceptance criteria；
- 有有效 plan；
- 有至少一个 repo/base reference；
- 所有修改位于 worktree；
- 有 diff；
- 有测试命令与结果；
- verifier 独立判断；
- 失败测试不能完成 run；
- merge/push 需额外审批。

### Codex 指令

```text
请实现 PR-05 template/local-coding-project。
默认采用 Agentless 的 bounded workflow，不要为了展示而启动无边界 swarm。
每个真实 coding run 创建独立 git worktree；实现者与验证者分离；所有改动以 diff/test/review Artifact 记录。
使用现有 template_packages 表表达 roles、workflow、execution_bounds、quality_gates 和 approval_policy。
最终必须用该模板完成一次“MIS 开发 MIS”的自举任务。
```

---

## PR-06：`perf/p0-hardening`

### 目标

将 P0 从“单次演示成功”提升为可重复本地使用。

### 内容

- 10-task 固定真实任务 suite；
- runtime failure injection；
- approval replay/tamper suite；
- index corruption/rebuild；
- DB restart/recovery；
- p95 性能回归门；
- secret scan；
- license/SBOM 报告；
- 本地一键启动与诊断命令；
- release notes 和 known limitations。

### 10-task suite 建议

1. 生成 MIS 状态简报；
2. 定位一个 Python 函数；
3. 修复一个带测试的简单 bug；
4. 新增一个只读 API；
5. 生成 repo architecture report；
6. 触发并拒绝一个高风险操作；
7. 触发并批准一个 worktree 内写操作；
8. runtime 中途失败并恢复；
9. 检索一个历史失败案例；
10. 完成一次完整 coding template 自举。

### 发布门

```text
0 个未授权副作用
0 个 raw secret 泄漏
10-task 基础设施闭环成功率 ≥80%
所有失败均有 error type + audit + recovery/next action
性能不低于 PR-00 baseline 的约定预算
```

### Codex 指令

```text
请实现 PR-06 perf/p0-hardening。
不要新增大功能；只做真实任务测试、故障注入、安全回归、性能门和一键诊断。
把所有通过/失败证据写入 docs/P0_RELEASE_EVIDENCE.md。
```

---

## 7. 依赖引入策略

P0 允许新增的第一批依赖必须少而明确：

```text
mcp>=1.27,<2        # 仅 MCP server/client；在 v2 稳定前固定上限
PyYAML 或等价小依赖 # 仅在标准库解析无法满足 policy 时引入
```

在决定 tree-sitter、LangGraph、向量库、OPA sidecar 前，必须提交 ADR，包含：

```text
为何标准库/当前实现不够
延迟与内存成本
许可证与维护状态
离线能力
替换/卸载方式
是否会成为 source of truth
```

### 明确暂缓

```text
独立向量数据库
Neo4j/图记忆集群
Kafka/Redis 队列
Kubernetes
默认 LangGraph 主控
默认 CrewAI/JiuwenSwarm 主控
多租户 SaaS
Marketplace/计费
```

这些保留在 P1-P3 路线，不在 P0 混入。

---

## 8. 每个 PR 的统一交付格式

```text
1. Summary
2. Current code evidence
3. Open-source method adopted
4. Files/schema/API changed
5. Tests executed and raw results
6. Performance before/after
7. Security/privacy checks
8. License/SBOM changes
9. Known limitations
10. Rollback
11. Next PR prerequisites
```

Codex 不得只回复“已完成”；必须提供可核验的 commit、测试输出和数据库/API 证据。