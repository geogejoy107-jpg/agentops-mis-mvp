# 测试计划

## 手工验收

1. 启动服务：`python3 server.py --reset && python3 server.py`。
2. 打开 `/dashboard`，确认指标显示。
3. 打开 `/agents`，创建 Agent。
4. 打开 `/tasks`，创建 Task。
5. 进入任务详情，点击 Start mock run。
6. 如果 run 等待审批，打开 `/approvals` 批准。
7. 回到 run detail，确认 status completed 或 blocked。
8. 打开 `/evaluations`，确认 rule-based evaluation 生成。
9. 打开 `/memory`，批准或拒绝 candidate。
10. 打开 `/audit`，确认有关键事件。
11. 导出 runs / memories JSON。

## API 快速测试

```bash
curl http://127.0.0.1:8787/api/agents
curl http://127.0.0.1:8787/api/tasks
curl -X POST http://127.0.0.1:8787/api/mock-runs/start \
  -H 'Content-Type: application/json' \
  -d '{"task_id":"tsk_competitor","agent_id":"agt_research"}'
```

## 质量门测试

- 任务无 acceptance_criteria -> fail。
- run cost_usd > task budget_limit_usd -> fail。
- high-risk tool call 未审批 -> fail。
- run error_message 非空 -> fail。

## 安全测试

- 确认没有真实 API key。
- 确认外部调用默认关闭。
- high-risk tool call 必须进入 approval。
- 审批拒绝后 run blocked。
- 每次写操作写 audit log。

## 回归测试建议

本沙盒实现未引入测试框架。Next.js 版建议增加：

- Unit: schema validators, rule evaluator, risk classifier。
- Integration: mock run lifecycle。
- E2E: create task -> start run -> approve -> memory review。
