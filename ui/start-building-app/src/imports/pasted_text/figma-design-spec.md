能做，而且我建议下一步就按 **“Figma Make 先产设计稿，我这边负责产品信息架构 + 提示词 + 验收标准 + 后续落代码 spec”** 来走。

你可以让 Figma 连接 GitHub 仓库，但我建议不要直接让 Make “自由改代码”。先让它生成 **设计稿/页面方案**，确认方向后，再把设计转成前端实现任务交给 Codex。否则很容易变成：UI 看起来很炫，但和 Agent-MIS 的对象模型、接口、demo 路线脱节。

---

## 我这边下一步能做什么

我可以分三步帮你做：

### 第一步：给 Figma Make 一份完整 UI 生成提示词

内容包括：

```text
产品定位
客户端 / 管理端分层
8 个核心页面
视觉风格
组件要求
数据字段
页面状态
demo 视频重点
```

你直接复制到 Figma Make。

### 第二步：你把 Figma 生成结果发我

可以发：

```text
Figma 链接
截图
导出的页面结构
Make 生成的代码片段
```

我可以帮你判断：

```text
哪些页面适合保留
哪些信息结构错了
哪些太像普通后台
哪些没有体现 MIS
哪些没有体现 AgentOps / Runtime / Notion / Base Switching
```

### 第三步：我把 Figma 结果转成 Codex UI 实现 spec

再交给 Codex 改仓库：

```text
static/index.html
static/styles.css
static/app.js
```

或者后面迁移：

```text
Next.js + Tailwind + shadcn/ui
```

---

## 我建议你在 Figma 里怎么做

你可以让 Figma 连接 GitHub 仓库，但 Make 的目标先写成：

> **Generate design only / do not modify production code yet.**

或者如果它一定要读 repo，就让它读取这些文件作为上下文：

```text
README.md
docs/PAGE_INFORMATION_ARCHITECTURE.md
docs/RUNTIME_CONNECTOR_SPEC.md
docs/HERMES_AGNESFALLBACK_CONNECTOR_SPEC.md
docs/TEMPLATE_BASE_SWITCHING_SPEC.md
docs/DEMO_VIDEO_SCRIPT.md
static/index.html
static/app.js
static/styles.css
```

核心是让它知道你现在已经有：

```text
Dashboard
Agents
Tasks
Runs
Tool Calls
Approvals
Memory
Evaluations
Audit
Integrations
Runtime Connectors
External Bases
Template Packages
Base Switching
```

---

## 给 Figma Make 的提示词：第一版

你可以直接复制下面这段。

```text
Create a high-fidelity SaaS product UI design for the GitHub repository “agentops-mis-mvp”.

Product name:
AgentOps MIS / AI Workforce MIS

Product positioning:
This is not an AI chatbot and not an agent builder. It is a Management Information System for AI digital employees and multi-agent workflows. It acts as a vendor-neutral control plane above different runtimes and external bases.

The product manages:
- Agent Registry
- Task Management
- Run Ledger
- Tool Call Ledger
- Human Approval Workflow
- Organizational Memory Governance
- Evaluation / Quality Gate
- Audit Log
- Runtime Connectors
- External Bases
- Template + Base Switching

Runtime connectors:
- OpenClaw: imported and ready
- Hermes default gateway: unavailable health state recorded
- Agnesfallback: explicit confirmed live probe available
- Future: OpenAI-compatible APIs, Claude, Codex, OpenHands, CrewAI, LangGraph

External bases:
- Notion: dry-run, parent/database export, workspace-private export mode
- Future: W&B, Plane, Docmost, Mattermost, n8n

Design goal:
Create a polished enterprise SaaS UI that looks like a serious MIS / control plane, not a toy chatbot app.

Separate the product into two experiences:

1. Client Workspace
For founder, operator, reviewer, normal team member.
Pages:
- Workspace Home
- My Tasks
- AI Employees
- Approvals
- Memory
- Reports
- Templates

2. Admin Console
For owner, admin, auditor, system operator.
Pages:
- Control Tower
- Agent Registry
- Run Ledger
- Tool Call Ledger
- Runtime Connectors
- External Bases
- Template Bindings
- Audit
- Settings

Create these 8 high-fidelity screens:

1. Workspace Home
Show:
- Today’s agent work
- My pending approvals
- Active tasks
- Recently completed runs
- Memory candidates
- Connected bases
- Quick actions

2. Admin Control Tower
Show:
- Total agents
- Total tasks
- Total runs
- Pending approvals
- Runtime health
- Failure rate
- Total cost
- Memory candidates
- OpenClaw import summary
- Audit risk summary

3. Agent Detail
Show:
- Agent profile
- Runtime type
- Role
- Tool permissions
- Budget
- Success rate
- Failure count
- Recent runs
- Recent tasks
- Approval-required actions
- Performance card

4. Task Detail
Show:
- Task title
- Owner agent
- Status
- Risk level
- Acceptance criteria
- Related runs
- Related approvals
- Related memory candidates
- Artifacts
- Quality gate status

5. Run Detail
Show:
- Run metadata
- Runtime provider
- Parent run / delegation id
- Child run graph
- Tool calls
- Token/cost/latency
- Evaluation result
- Audit timeline
- Error summary if failed

6. Runtime Connectors
Show connector cards:
- OpenClaw: ready, imported, last probe success
- Hermes default: unavailable but recorded as health state
- Agnesfallback CLI: live probe available, explicit confirmation required
- Agnesfallback API gateway: OpenAI-compatible mode, optional
Each card should show:
- Provider
- Status
- Mode
- Last checked
- Real run enabled or disabled
- Confirmation required
- Recent runtime events
- View ledger button

7. Notion External Base
Show:
- Export mode: dry_run_only / page_parent / database_parent / workspace_private
- Token configured or not, without exposing token
- Dry-run default
- Writeback allowed or not
- Linked memory objects
- Linked task objects
- Sync events
- Export preview
- Security note: leaked tokens must be rotated
Explain visually that Notion is an external memory/task/template base, not the core ledger.

8. Template + Base Switching Preview
Show:
- Template package: AI Software Team / AI Experiment Evaluation / Content Studio / One-Person Company Ops
- Current base: Agent-MIS Local Base
- Target base: Notion / W&B / Plane / Docmost
- Field mapping table
- Capability comparison
- Migration preview
- Non-migratable fields
- Audit impact
- What stays in Agent-MIS Core:
  Run Ledger, Tool Call Ledger, Approval, Audit, Agent IAM, Evaluation

Visual directions:
Create a design system with 3 style variants:

A. Enterprise MIS Light
- Clean white / light gray background
- Blue and green accents
- Professional, readable, management-system oriented
- Suitable for classroom report and enterprise customers

B. Dark Ops Control Plane
- Dark navy background
- Cyan / purple accents
- Runtime health, trace, audit, SOC-like control tower feel
- Suitable for demo video and AgentOps monitoring

C. AI Workforce OS
- Modern SaaS workspace
- Soft gradients
- Rounded cards
- AI employee cards
- Template marketplace feeling
- Suitable for future product launch

Use these colors:
- Primary blue: #2E86AB
- Success green: #2A9D8F
- Risk orange-red: #E76F51
- AI purple: #7A5AF8
- Neutral gray: #6B7280
- Light background: #F7FAFC
- Dark background: #0B1020

Design requirements:
- Left navigation with grouped sections
- Topbar with workspace switcher, search, live mode status, and user avatar
- Cards with 16-20px radius
- Professional tables
- Clear badges for ready, unavailable, dry-run, live, approved, pending, failed
- Risk badges for low, medium, high, critical
- Connector cards
- Agent performance cards
- Run delegation graph
- Audit timeline
- Template migration preview
- Empty states and error states
- Responsive desktop-first layout

Tone:
Professional, trustworthy, modern, suitable for a Management Information Systems course project and future SaaS product.

Do not make it look like a generic chatbot.
Do not make it look like only a monitoring dashboard.
It should feel like an AI workforce management system.
```

---

## 你在 Figma Make 里要特别加一句

为了避免它乱改仓库，加这一句：

```text
For now, generate Figma design screens and design system only. Do not directly modify repository source code. The implementation will be handled later after design review.
```

如果它必须生成代码，那就加：

```text
If code is generated, keep it as a separate prototype branch or design preview. Do not overwrite existing server.py or API logic.
```

---

## 我建议 Figma 先输出什么

让它至少输出：

```text
Design system page
Client Workspace page
Admin Control Tower page
Runtime Connectors page
Notion External Base page
Template Switching page
Run Detail page
Agent Detail page
```

不用一开始追求所有页面。

---

## 你发回来后我会看什么

我会重点看 7 个点：

```text
1. 是否真的分出了客户端和管理端
2. 是否像 MIS，而不是普通 AI 工具
3. 是否把 OpenClaw / Hermes / Agnesfallback 讲清楚
4. 是否把 Notion 定位成外部底座，不是核心
5. 是否把 Run Ledger / Audit / Approval 做成核心视觉
6. 是否适合录 demo 视频
7. 是否能被 Codex 按现有 API 落地
```

然后我会给你一版：

```text
UI_IMPLEMENTATION_SPEC.md
FRONTEND_REFACTOR_PROMPT.md
Figma-to-static-app mapping
页面组件表
API 对应表
Codex 修改提示词
```

---

## 现在不要让 Figma 做太多

尤其不要让它现在就做：

```text
移动端完整适配
复杂动画
完整官网
完整品牌系统
所有页面
真实代码合并
```

先拿 **8 个核心页面 + 3 个风格方向**。
我们看完后再决定：课程版用 Enterprise MIS Light，录屏版用 Dark Ops Control Plane，商业包装版用 AI Workforce OS。
