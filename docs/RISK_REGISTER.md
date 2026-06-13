# 风险登记册

| 风险 | 说明 | 影响 | MVP 控制 | 后续增强 |
|---|---|---|---|---|
| Runtime 接入失败 | OpenHands/Claude Code/Codex 等可能受 Docker、CLI、key、端口影响 | Demo/生产不可用 | 第一版只做 mock runtime | Adapter health check + retry + sandbox diagnostics |
| 隐藏 Telemetry | 运行框架可能默认上传 telemetry 或字段不透明 | 隐私/合规风险 | 默认不引入外部 telemetry | outbound telemetry registry + masking + opt-in |
| 高风险工具越权 | shell/email/db/github push 等可造成外部副作用 | 高 | 高风险动作进入 approval | Policy engine + scoped tokens + gateway |
| 组织记忆污染 | Agent 自动写入错误、过期或无证据的记忆 | 高 | candidate/review queue + confidence + TTL | evidence store + provenance graph + ACL |
| 审计不完整 | 无法解释谁让 Agent 做了什么 | 高 | audit_logs + run/tool/approval IDs | tamper-evident log + export + retention |
| 只看成本不看质量 | 低成本 Agent 可能输出差 | 中 | evaluation + quality gate | human review + LLM judge calibration |
| 平台锁定 | 过度绑定某个 builder/runtime | 中 | runtime_type 适配器字段 | plugin adapter SDK |
| 过度拟人化 | 过多 CEO/员工叙事影响严肃治理 | 中 | MVP 用“角色/权限/任务”替代“人格” | 仅在营销层使用 AI workforce language |
