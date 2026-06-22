# Product Usage and Actor Model

## One Sentence Positioning

AgentOps MIS is a local-first control plane for turning a human goal into a managed AI workforce workflow with task assignment, runtime evidence, approval gates, memory governance, evaluation, reports, and audit.

## Example Customer Task: AI Knowledge Base / Q&A Bot

The "formal AI knowledge base / Q&A bot" task is a good example of the intended product model:

```text
Raw materials
  -> clean Markdown / PDF / DOCX
  -> Dify / OpenAI File Search / AnythingLLM
  -> chunking + embedding + vector store
  -> AI Q&A / workflow / agent
  -> evaluation, report, audit, and customer handoff
```

In AgentOps MIS, the customer does not manually supervise every runtime step. The customer creates the project, chooses a template, approves risky actions, reviews artifacts, and accepts the final result. AI digital employees pull tasks through the Agent Gateway, run work in OpenClaw, Hermes, Dify, OpenAI File Search, or another runtime, and report evidence back to MIS.

## Solo Company Mode

Solo company mode is for one founder, freelancer, student team lead, or independent operator who wants to run a small AI team alone.

- The solo owner creates a workspace and selects a template, such as "AI Knowledge Base Bot".
- The template creates the initial AI workforce: researcher, document cleaner, knowledge-base builder, evaluator, reporter, and operator.
- The owner provides materials and goals, not low-level runtime instructions.
- MIS tracks tasks, run ledger entries, tool calls, approvals, memory candidates, evaluation gates, cost, and audit.
- External tools such as Dify, OpenAI File Search, AnythingLLM, Notion, GitHub, OpenClaw, or Hermes remain execution or storage layers, not the authority system.
- The local-first default keeps raw materials, credentials, private prompts, and local runtime state out of the public repo and out of shared logs.

For the course demo, this mode should show a customer entering a project like "build a Q&A bot from course materials", then watching AI employees create structured tasks, request approval for external writes, and produce a report.

## Multi-User Human-AI Collaboration Mode

Multi-user mode is for a human team working with AI digital employees.

- Team members can create tasks, upload safe project materials, review outputs, and comment on work.
- Admins define templates, permission scopes, connector policy, and approval rules.
- Human approvers handle high-risk actions, such as external writes, public publishing, expensive model calls, or credential-dependent operations.
- AI employees execute assigned work through the Agent Gateway and submit structured evidence.
- The organization can audit who asked for what, which runtime acted, what tool calls happened, what approvals were required, and which evaluations passed.

This mode should later support RBAC and workspace-level identity. In the current local MVP, the same actor may play multiple roles, but the product model keeps them separate.

## Actor Model

### Solo Owner

The solo owner is the primary operator in one-person mode. They select templates, create goals, approve risky actions, review results, and decide what becomes persistent memory.

### Team Member

A team member contributes project context and reviews work. They can create or update tasks but may not approve high-risk operations unless granted permission.

### Admin / Owner

The admin or owner configures workspace policy, templates, runtime connectors, approval rules, memory schemas, evaluation gates, and external bases.

### Human Approver

The human approver reviews actions that can create external side effects or long-lived risk. Approval decisions must be recorded in `approvals` and `audit_logs`.

### AI Digital Employee

An AI digital employee is a managed agent identity, such as Researcher, Cleaner, Builder, Evaluator, Operator, or Reporter. It does not own authority. It pulls tasks, claims work, starts runs, records tool calls, proposes memory, and submits evaluations through the Agent Gateway.

### External Runtime

An external runtime is the execution substrate: OpenClaw, Hermes, Codex, Claude Code, Dify, OpenAI File Search, AnythingLLM, CrewAI, LangGraph, OpenHands, or a remote agent running on another machine. The runtime can perform work, but MIS remains the control plane and ledger.

## Surface Model

### Human Workspace

The Human Workspace is for customers and team members. It should answer: "What work is happening, what needs my input, and what can I use now?"

Expected surfaces:

- Pixel Office / operating map for visual status.
- My Tasks for customer-facing task queue.
- AI Employees for who is working.
- Approvals for actions requiring human consent.
- Memory for reviewable knowledge.
- Reports for final artifacts and project status.

### Governance Console / Admin Console

The Governance Console is for owners and operators. It should answer: "Is the AI workforce safe, accountable, cost-aware, and auditable?"

Expected surfaces:

- Control Tower.
- Agent Registry.
- Run Ledger.
- Tool Call Ledger.
- Runtime Connectors.
- External Bases.
- Evaluation Room.
- Audit Center.
- Template + Base Switching.

### Agent Gateway CLI/API/MCP

The Agent Gateway is the machine interface. Browser UI is for humans; CLI/API/MCP is for agents and runtimes.

Expected capabilities:

- Register or update an agent identity.
- Send heartbeat and status.
- Pull tasks and claim work.
- Start runs and send run heartbeats.
- Record tool calls and runtime events.
- Request approvals.
- Propose memory.
- Submit evaluations.
- Emit audit events.

### Pixel Operating Map

Pixel Office is a visual operating map, not the authority system. It should help humans see agent presence, task flow, incidents, approvals, and runtime health. It must derive from MIS tables and API state, not invent canonical state.

## Template Model

A template package creates an initial operating system for a project. For the AI Knowledge Base / Q&A Bot task, a template should include:

### Agent Roles

- Project Planner: decomposes the customer goal into tasks.
- Researcher: audits source materials and target tools.
- Document Cleaner: normalizes files into Markdown, PDF, or DOCX.
- Knowledge Base Builder: prepares Dify / OpenAI File Search / AnythingLLM import plans.
- Evaluator: tests retrieval quality, citation quality, and answer grounding.
- Operator: handles connector setup and safe export.
- Reporter: summarizes progress and creates customer-facing documentation.

### Task Types

- Source intake.
- Document cleaning.
- Chunking and metadata design.
- Connector setup.
- Retrieval evaluation.
- Q&A workflow design.
- Demo script and handoff report.
- Incident recovery.

### Approval Policies

- External writes require approval.
- Uploading customer files to third-party systems requires approval.
- Publishing public pages or demos requires approval.
- High-cost model runs require approval.
- Credential access or connector changes require approval.
- Deletion, overwrite, or destructive shell actions require approval.

### Memory Schemas

- Project decision.
- Stable SOP.
- Connector configuration note.
- Evaluation finding.
- Failure case.
- Customer requirement.
- Risk and mitigation.

Memory candidates must be reviewable. AI agents can propose memory, but approved memory is a human or policy decision.

### Evaluation Gates

- Source coverage gate.
- Retrieval relevance gate.
- Citation/source-grounding gate.
- Privacy and credential leakage gate.
- Cost/latency gate.
- Customer acceptance gate.
- Final artifact completeness gate.

### Connectors

- Local file import.
- Notion external base.
- Dify knowledge workflow.
- OpenAI File Search.
- AnythingLLM.
- GitHub artifacts.
- OpenClaw and Hermes runtime adapters.

### Reports

- Project plan.
- Source inventory.
- Connector readiness report.
- Evaluation report.
- Final customer handoff.
- Audit and approval summary.

## What Humans Do

- Define goals, constraints, and acceptance criteria.
- Select a template.
- Provide source materials and business context.
- Approve high-risk operations.
- Review outputs and evaluations.
- Decide what becomes approved memory.
- Accept final deliverables.
- Future billing setup is excluded from the current local MVP; humans currently
  configure credentials, connectors, and workspace permissions.

## What AI Agents Do

- Break goals into executable tasks.
- Pull and claim tasks through the Agent Gateway.
- Run safe local or remote work in their assigned runtime.
- Clean and structure documents.
- Propose connector plans.
- Draft reports and handoff materials.
- Record tool calls and runtime evidence.
- Request approval before risky steps.
- Propose memory candidates.
- Submit evaluation results.
- Emit audit events for important state changes.

## What Must Require Approval

The following actions must require approval in product mode:

- Sending customer files, private content, or proprietary data to an external service.
- Writing to Notion, GitHub, Dify, OpenAI File Search, AnythingLLM, Slack, email, or any external base.
- Publishing a public link, page, demo, dataset, report, or repository.
- Reading or using credentials beyond a scoped local token.
- Deleting, overwriting, or bulk-modifying files or external records.
- Running high-risk shell, browser, database, payment, deployment, or account actions.
- Running high-cost or long-running model jobs.
- Changing agent permissions, connector trust level, approval policy, or memory policy.
- Promoting memory candidates into approved workspace memory.

## How Templates Create The Initial AI Workforce

Templates should generate the initial workspace scaffold:

1. Agent roles with names, responsibilities, allowed tools, risk level, and runtime preference.
2. Task types with default status, priority, acceptance criteria, and owner role.
3. Approval policies for each tool or connector.
4. Memory schemas and review rules.
5. Evaluation gates and pass/fail thresholds.
6. Connector placeholders and dry-run defaults.
7. Report templates and demo checklist.

For the AI Knowledge Base / Q&A Bot template, the first task set should include intake, cleaning, knowledge-base setup, retrieval evaluation, and final report. Agents can execute the tasks, but the template and MIS tables remain the source of truth.

## How Pixel Office Fits Without Becoming The Authority System

Pixel Office is a human-friendly control-room visualization. It should:

- Render agents from `agents`.
- Render task cards from `tasks`.
- Render runs and incidents from `runs`, `tool_calls`, and `evaluations`.
- Render approvals from `approvals`.
- Render memory review state from `memories`.
- Render external-base status from connector and audit state.

Pixel Office should not:

- Store canonical project state outside MIS tables.
- Bypass approval policy.
- Directly run tools without Agent Gateway evidence.
- Invent hidden agent state that cannot be traced to the ledger.

The simple rule: Pixel Office shows and dispatches work; AgentOps MIS records and governs work.
