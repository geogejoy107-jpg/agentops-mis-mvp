# 页面信息架构

## /dashboard

展示：

- 总 Agent 数
- 运行中 Agent 数
- 完成任务数
- 总成本
- 平均任务成本
- 失败率
- 待审批数量
- 过期/待复核记忆数量
- 任务状态分布
- Top Cost Agents
- Top Failing Agents
- 最近 20 条 run ledger

## /agents

- 创建 Agent
- Agent 列表
- status、runtime、tools、budget

## /agents/:id

- Agent 档案
- 该 Agent 负责的任务
- 该 Agent 的运行记录

## /tasks

- 创建任务
- 任务表
- Kanban 状态视图

## /tasks/:id

- 任务详情
- 启动 mock run
- Run history
- Approvals
- Evaluations
- Memory candidates
- Artifacts

## /runs

- Run Ledger 全表

## /runs/:id

- Run 元数据
- Tool calls
- Approvals
- Evaluations

## /tool-calls

- Tool Call Ledger
- risk level
- target_resource
- request approval 按钮

## /approvals

- 审批队列
- 批准 / 拒绝

## /memory

- 组织记忆候选
- scope: task / project / org
- memory_type: decision / commitment / SOP / failure case 等
- review_status
- TTL
- source_ref

## /evaluations

- 质量门结果
- score
- pass/fail
- evaluator_type

## /audit

- 关键事件审计记录
- before_hash / after_hash
- tamper_chain_hash 预留

## /integrations

- Notion connector status
- Notion report export preview
- dry-run export
- configured export to Notion page/database
- privacy boundary

## /settings

- runtime policy
- high-risk actions
- future adapters
