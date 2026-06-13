# Seed Data

运行 `python3 server.py --reset` 会自动生成种子数据。

## Users

- `usr_founder`: Founder
- `usr_ops`: Ops Reviewer
- `usr_admin`: Platform Admin

## Agents

- `agt_cos`: CoS Agent
- `agt_research`: Research Agent
- `agt_builder`: Builder Agent
- `agt_qa`: QA Agent
- `agt_ops`: Ops Agent

## Tasks

- `tsk_competitor`: 竞品调研
- `tsk_prd`: 生成 PRD
- `tsk_code`: 写代码
- `tsk_issue`: 审查 GitHub issue
- `tsk_meeting`: 整理会议纪要
- `tsk_commitments`: 抽取承诺
- `tsk_cost`: 成本分析
- `tsk_risk`: 风险扫描
- `tsk_report`: 生成报告
- `tsk_release`: 发布前 QA

## 其他数据

- 30 条 seed runs
- 40+ tool calls
- 8 approvals
- 10 memories
- 12 evaluations
- 50+ audit logs

导出样例位于：

- `artifacts/sample_export_runs.json`
- `artifacts/sample_export_memories.json`
