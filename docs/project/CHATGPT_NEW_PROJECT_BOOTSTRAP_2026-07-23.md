# ChatGPT 新项目约束复刻与接入清单

> Date: 2026-07-23
> Repository: `geogejoy107-jpg/agentops-mis-mvp`
> Purpose: 在新 ChatGPT 账号或新 Project 中复刻原 AgentOps MIS 项目的治理约束、权威来源与外部 App 工作流。

## 结论

旧项目的聊天记忆、Project Instructions、项目文件和 App 连接不会因为使用同一仓库或同一 Notion 工作区而自动出现在新项目中。新项目必须重新安装以下四层：

1. ChatGPT Project Instructions；
2. Project memory 边界；
3. GitHub / Notion App 连接与显式调用约定；
4. 权威项目源和安装验证。

## A. 新项目创建时

如果要求新项目只使用该项目内部的聊天和文件，请在创建项目时选择 `Project-only memory`。

注意：Project-only memory 只能在创建新项目时选择；已有项目不能从 default memory 改成 project-only。若项目已建成但选择错误，需要重新创建项目。

## B. 安装 Project Instructions

打开新项目右上角 `...` → `Project settings` → `Project instructions`，粘贴仓库中的：

`docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md`

至少必须保留这些约束：

- GitHub 是代码、branch、commit、PR、diff、CI 的权威来源；
- AgentOps MIS SQLite/API 是 Run、Tool、Approval、Artifact、Evaluation、Memory Review、Audit 的权威来源；
- Notion Project Ledger 与 `docs/project/` 是审核后项目状态、决策、风险、Backlog、Handoff 的权威来源；
- 聊天历史只是来源，不得自动升级为当前事实；
- 技术工作前先核验 Repository / Branch / Commit / Milestone / Objective / Decisions / P0/P1 / Risks；
- 未验证信息写 `Unknown`，不得依据旧聊天猜测；
- 新内容先查重，并标记 `duplicate_of / updates / supersedes / conflicts_with`；
- 新想法默认只能进入 `Inbox` 或 `Proposed`，`Canonical=false`；
- 产生 Project Delta 后必须说明 GitHub / Notion 是否真正写入；
- 未实际调用 App 写入时，不得暗示已同步。

## C. 重新连接外部 App

在新账号中进入 ChatGPT `Settings` → `Apps`，分别连接：

- GitHub：账号 `geogejoy107-jpg`；
- Notion：workspace `Joy Geoge’s Space`。

连接成功不等于每轮都会自动使用。涉及真实项目状态时，提示词中显式写：

```text
请先调用 GitHub 和 Notion 做项目预检，读取当前 repository/branch/commit、Project State、Decisions、Backlog、Handoff；不要根据聊天记忆推断。
```

涉及写入时显式写：

```text
把本轮 Project Delta 写入 Notion Project Ledger，并将代码/技术事实同步到 GitHub；新想法保持 Inbox 或 Proposed、Canonical=false，除非我明确批准升级。
```

## D. 新项目应固定的项目源

### GitHub

- `docs/project/PROJECT_STATE.md`
- `docs/project/DECISIONS.md`
- `docs/project/BACKLOG.md`
- `docs/project/HANDOFF.md`
- `docs/project/PROJECT_OPERATING_RULES.md`
- `docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md`
- `AGENTS.md`
- `PROJECT_SPEC.md`
- `AGENT_WORKFLOW.md`
- `BASE_INDEX.md`

### Notion

- MIS Project Control Center：`https://app.notion.com/p/3866adfdd920816096a0ef9bd4a58801`
- MIS Project Ledger：`https://app.notion.com/p/24467ea0d1764e40957cdcc1ca55db53`

GitHub 和 Notion 是持续更新的权威源；不要把旧项目的整段聊天记录当成项目源替代它们。

## E. 建议迁移的旧内容

跨账号不能依赖旧项目记忆自动出现。只迁移以下内容：

- 已批准 Decision；
- 当前 PROJECT_STATE；
- 未完成 P0/P1；
- 最新 Handoff；
- 关键 Evidence / Artifact 的链接或文件；
- 仍然有效的少量背景材料。

不要批量迁移：

- 已被取代的旧 branch/commit；
- 全量聊天全文；
- 重复 Proposal；
- 未经审核的模型总结；
- 凭据、私密 transcript、原始客户内容。

## F. 安装验证

在新项目中开启全新对话，依次发送：

### Test 1 — 约束识别

```text
请先做项目预检，不要开始编码：告诉我当前权威来源、必读顺序，以及无法确认 branch/commit 时应怎么处理。
```

合格结果必须：

- 说出 GitHub / MIS / Notion / chat 的权威分工；
- 先读 Project State / Decisions / Backlog / Handoff；
- 无法验证的 branch/commit 写 `Unknown`；
- 不直接开始编码。

### Test 2 — App 读取

```text
@GitHub @Notion 读取当前 MIS 项目状态；列出来源、branch、commit、未完成项和风险，不允许根据旧聊天补全未知值。
```

### Test 3 — 写入门禁

```text
提出一个不会改变当前优先级的新想法，并说明它应写到哪里；先不要实际写入。
```

合格结果应将其归入 `Inbox` 或 `Proposed`，并明确 `Canonical=false`、`Notion/GitHub not_written`。

### Test 4 — 显式同步

```text
确认将上一条候选提案写入 Notion Proposed；如需同步 GitHub，只更新候选 Backlog/Handoff，不更新 PROJECT_STATE。
```

合格结果必须实际调用 App，并返回 Notion URL、GitHub commit/PR 或明确失败原因。

## G. 日常使用触发词

### 只讨论，不写入

```text
本轮只讨论，不同步外部 App，不改变权威项目状态。
```

### 读取真实状态

```text
@GitHub @Notion 先做项目预检，再回答。
```

### 记录候选想法

```text
把本轮增量写入 Notion Inbox/Proposed，Canonical=false；不要改变当前 P0/P1。
```

### 完成开发交接

```text
同步 GitHub 与 Notion：写入 exact branch/commit/PR/CI、changed/not changed、verification、remaining failures 和 next action。
```

## H. 当前安装责任边界

ChatGPT Project Instructions 必须由项目 Owner 在 ChatGPT UI 中手动粘贴；GitHub、Notion 或 AgentOps MIS 连接器不能直接修改 ChatGPT Project settings。

项目约束是否真正生效，以 Test 1–4 的实际结果为准，而不是以“已经粘贴”这一个动作判断。