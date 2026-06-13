# AgentOps MIS Capability Roadmap

## Current State

The current demo is a local Python/SQLite sandbox with OpenClaw import/probe, Hermes/Agnesfallback runtime connector shape, Notion External Base dry-run, template/base switching preview and a redacted scale seed. It proves the core control-plane object model:

- Agent registry
- Task ledger
- Run ledger
- Tool call ledger
- Approval workflow
- Evaluation records
- Memory candidates
- Audit logs
- Runtime connectors
- External bases
- Template packages
- Migration previews

It is not yet the full Agent-MIS vision from the research notes.

## Time Estimate

### Completed: v1.1 usable local control plane

- Import OpenClaw agents from safe config metadata.
- Import cron jobs as tasks.
- Import cron/subagent run metadata as runs.
- Add Agent-MIS research/search protocol to project workflow.
- Add a sharper dashboard section for OpenClaw runtime health.

### Current: v1.2.1 video-ready local MVP

- Add Hermes runtime probe.
- Add parent/child delegation chain view.
- Add memory review workflow with provenance, TTL, confidence, ACL tags.
- Add policy/approval rules for risky actions.
- Add basic cost-quality metrics and agent performance cards.
- Add test/smoke scripts and Playwright visual checks.
- Add Agnesfallback fixed-probe dry-run adapter.
- Add Notion External Base dry-run connector.
- Add Template + Base Switching preview.
- Add redacted OpenClaw-scale demo seed and acceptance script.
- Add demo video and reproducibility docs.

### 1-2 weeks: product-shaped private alpha

- Move from mock-only API to adapter-based ingestion.
- Add workspace/user/RBAC scaffolding.
- Add connector trust registry for tools/MCP/skills.
- Add append-only ledger tables for delegation, approvals, side effects, provenance edges.
- Add import/export, retention controls, and audit reports.

### 2-4 weeks: commercial SaaS/BYOC foundation

- Next.js/TypeScript frontend.
- Postgres + migrations.
- Multi-workspace tenancy.
- API-first adapter SDK.
- Billing/event metering design.
- SSO/RBAC/audit retention.
- Private deployment story.

## What Should Use Pro / Deep Model Runs

Use a stronger/pro model for tasks with high ambiguity, broad research, or architecture tradeoffs:

- Re-running broad market research across GitHub, HN, Reddit, X, docs, pricing, and recent release notes.
- Designing canonical Agent-MIS schema v2 from the GPT research reports.
- Designing Agent IAM and policy-as-code architecture.
- Designing the delegated-execution ledger: delegation, approval, side_effect, provenance edges.
- Threat modeling tool/skill/MCP marketplace trust.
- Product positioning and pricing against Agent 365, Gemini Enterprise Agent Platform, LangSmith, CrewAI AMP, Relevance AI, AgentOps, Paperclip, OneManCompany, Mission Control.

Use the normal coding model for implementation once the spec is clear:

- SQLite/Postgres migrations.
- API endpoints.
- import scripts.
- dashboard UI.
- tests/smoke scripts.
- documentation updates.

## Research Already Visible

The local `gpt-research` folder contains enough source material to guide v1.1-v2:

- `deep-research-report.md`: AI Agent Control Plane / AI Workforce Management Platform.
- `deep-research-report (1).md`: Agent-MIS / AI digital employee management system.
- `AgentOps 与 AI Agent 可观测性深度研究报告.docx`: observability and Agent Run Ledger.
- `AI 智能体安全治理、非人类身份与 Agent IAM 研究报告.pdf`: Agent IAM, approvals, audit, kill switch.
- `AI 协作体记忆、组织记忆与上下文图研究报告.pdf`: organizational memory, provenance, TTL, ACL.
- `人在回路代理工作流、质量门与代理绩效评估研究报告.pdf`: HITL, quality gates, evaluation, performance review.

## Installed Codex Skills

Installed official curated skills:

- `pdf`
- `playwright`
- `screenshot`
- `jupyter-notebook`
- `cli-creator`
- `define-goal`
- `sentry`
- `security-threat-model`
- `security-best-practices`
- `security-ownership-map`
- `notion-knowledge-capture`
- `notion-research-documentation`
- `notion-spec-to-implementation`
- `gh-address-comments`
- `gh-fix-ci`

Created local project skill:

- `broad-community-research`: forces alias expansion, recent/community source coverage, GitHub/HN/Reddit/X checks when available, candidate tables, evidence quality, and explicit uncertainty notes.

Restart Codex to pick up newly installed skills.

## Third-Party Skill Policy

Do not auto-install random GitHub skill packs into the live Codex environment. Community skill collections can be useful, but they may include high-risk automation, scraping, outreach, or unreviewed tool instructions.

Recommended process:

1. Add community repos to a watchlist.
2. Inspect `SKILL.md` and scripts before installation.
3. Install only skills with clear source, narrow permissions, no credential exfiltration, and good fit for Agent-MIS work.
4. Prefer official OpenAI curated skills for active work.

## Recommended Next Build

Next concrete target: private alpha hardening.

Inputs:

- v1.2.1 local schema and API.
- Research traceability docs.
- OpenClaw/Hermes/Notion adapter boundaries.
- Template/base switching preview.

Outputs:

- RBAC scaffolding.
- Connector trust registry.
- Stronger ledger/provenance model.
- Postgres migration plan.
- Production OAuth/export path.
- Next.js UI handoff.

Privacy boundary:

- Store structured metadata, hashes, counts, status, duration, token usage, and local path refs.
- Do not copy credentials, private messages, full transcripts, or raw command bodies into MIS.
