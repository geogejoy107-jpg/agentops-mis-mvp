# 竞品矩阵

> 说明：本矩阵按“Agent-MIS / AI 数字员工管理系统”的视角整理。重点不是谁的 agent 更聪明，而是谁更接近 agent 管理控制面。

| 项目 | 产品定位 | 是否开源 | 核心管理对象 | 任务模型 | Agent 身份/权限 | 成本统计 | 审批/质量门 | 组织记忆 | 审计日志 | 技术栈/形态 | 可借鉴点 | 不足和风险 | 对 MVP 的启发 |
|---|---|---:|---|---|---|---|---|---|---|---|---|---|---|
| AgentHub | Claude Code 虚拟软件团队管理 | 是 | PM、Tech Lead、前端、后端、设计师、hooks、skills、FileWatcher | 有 | 偏本地角色/agent 配置 | 未见完整财务成本模型 | 强：hooks enforce quality | 有 .knowledge / rules | 偏 workflow trace | Electron / Claude Code 周边 | 角色分工、hook 质量门、技能标准化 | 绑定 Claude Code 心智，企业审计/成本不完整 | 借鉴“质量门不是 prompt，而是可执行 hook” |
| Paperclip | AI company control plane | 部分开源/网页产品 | org chart、goals、tasks、budgets、governance、agents | 有 | 有组织结构抽象 | 有 budgets | 有 approvals / governance 心智 | 未完全公开 | 未完全公开 | Node.js + React 方向 | 把 agent 从工具提升为组织资源 | 项目真实性与活跃度需要继续验证 | 借鉴 org chart + budget + accountability |
| OneManCompany | 一人公司 AI OS | 是 | CEO/COO/员工、层级团队、Talent Market、任务阶段、绩效 | 有 | 有岗位/员工抽象 | 有 project cost | 有质量门/绩效/PIP 心智 | 部分 | 未完全公开 | Web OS | 讲故事强，贴合一人公司 | 过度拟人化可能稀释严肃 MIS | 借鉴层级团队，但 MVP 少做“招聘/开除” |
| Mission Control | 自托管 Agent orchestration dashboard | 是 | agent fleet、tasks、costs、workflows、panels | 有 | 有 agent fleet | 有 costs | 有 quality gates / panels | 弱于 Rowboat | 有 telemetry | Self-hosted + SQLite | Dashboard 信息架构、SQLite MVP | Alpha，schema/API 可能变 | 借鉴 self-hosted zero-dependency MVP |
| Rowboat | local-first AI coworker with memory | 是 | people、projects、decisions、commitments、Markdown vault | 间接 | 弱 | 弱 | 弱 | 强：Markdown backlinks / living knowledge graph | 证据链需要扩展 | Local-first app | 组织记忆不是 RAG，而是事实/决策/承诺 | 不是任务/成本/审批系统 | 借鉴 memory schema 与 evidence/provenance |
| OpenHands | Coding agent runtime / enterprise coding agent | 是 + Enterprise | sessions、workspace、sandbox、repo integrations | 有 coding tasks | Enterprise 有 RBAC/multi-user | 企业版相关 | 依赖 review workflow | 弱 | 企业版有审计方向 | Python/React/Docker sandbox | 真实执行层 adapter 参考 | Docker sandbox、端口、镜像、权限易出问题 | MVP 不直接接真实 runtime；先记录 adapter envelope |
| CrewAI | 多 agent 编排框架与企业平台 | 是 + 企业功能 | agents、tasks、crews、flows、telemetry、tools | 强 | 企业版较强 | 有 traces/costs 方向 | 部分 | 弱 | tracing/telemetry | Python framework | 多 agent task/run 概念 | telemetry 争议说明需 mask/no hidden telemetry | MVP 明确 telemetry policy |
| Dify | Agentic workflow / AI app builder | source-available | apps、workflows、plugins、models、tools | 有 workflow | 平台权限 | 有用量/应用成本 | workflow 节点可控 | 知识库/RAG 强 | 企业版更强 | Python/React/Plugin marketplace | 插件/工作流生态 | 自托管插件市场 404/500 风险 | MVP 不依赖远程 marketplace |
| LangGraph / LangSmith | Stateful agent runtime + observability/eval | 部分开源 + SaaS | graphs、nodes、state、checkpoints、traces、evals | 强 | runtime 内身份较弱 | LangSmith 成本/trace | 有 eval / HITL 模式 | LangGraph memory/state | 强 trace | Python/JS | durable execution、state、eval | 不是 AI 员工 MIS | 后续 adapter 接 graph/run/node events |
| Langfuse / AgentOps / Helicone | LLM/agent observability | 是/商业混合 | traces、sessions、token、cost、latency、tool calls | 间接 | 弱于 IAM | 强 | 部分 eval | 弱 | 强 trace/export | SaaS/self-host | 不重造 observability UI | authority/approval/side-effect ledger 不足 | MVP 自建 ledger，后接这些工具 |

## 失败案例应进入产品需求

1. OpenHands 类 runtime 的 Docker sandbox、镜像、端口、权限问题，不应被 Agent-MIS 隐藏；应记录成 `runtime_error` 与 `adapter_health`。
2. CrewAI telemetry 争议说明：任何 telemetry 都应默认可见、可关闭、可脱敏。
3. Dify plugin marketplace 404/500 说明：企业演示不应依赖远程插件市场在线状态。
4. Langflow 默认认证行为说明：自托管 AI 工具的默认安全配置必须在控制面中显式检查。

## MVP 差异化

本 MVP 不做 builder，而做：

```text
Registry + Task + Run Ledger + Tool Risk + Approval + Memory Governance + Evaluation + Audit
```
