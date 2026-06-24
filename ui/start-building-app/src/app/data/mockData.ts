// Mock data shaped to match real agentops-mis-mvp schema field names exactly.
// Field names and enum values match sql/schema.sql so wiring to the live API
// at http://127.0.0.1:8787 requires only replacing these constants with fetch calls.

export type AgentStatus = 'idle' | 'running' | 'paused' | 'error' | 'disabled';
export type RuntimeType = 'mock' | 'claude_code' | 'codex' | 'openhands' | 'crewai' | 'langgraph' | 'openclaw' | 'hermes';
export type TaskStatus = 'backlog' | 'planned' | 'running' | 'waiting_approval' | 'blocked' | 'completed' | 'failed' | 'canceled';
export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';
export type Priority = 'low' | 'medium' | 'high' | 'critical';
export type ToolCategory = 'browser' | 'github' | 'file' | 'shell' | 'email' | 'notion' | 'discord' | 'database' | 'mcp' | 'custom';
export type ApprovalDecision = 'pending' | 'approved' | 'rejected' | 'expired';
export type MemoryReviewStatus = 'candidate' | 'approved' | 'rejected' | 'stale' | 'superseded';
export type MemoryScope = 'task' | 'project' | 'org';
export type PassFail = 'pass' | 'fail';
export type ActorType = 'user' | 'agent' | 'system';

export interface Agent {
  agent_id: string;
  name: string;
  role: string;
  description: string;
  runtime_type: RuntimeType;
  model_provider: string;
  model_name: string;
  status: AgentStatus;
  permission_level: string;
  allowed_tools: string[];
  budget_limit_usd: number;
  budget_used_usd: number;
  owner_user_id: string;
  success_rate: number;
  run_count: number;
  failure_count: number;
  approval_count: number;
  created_at: string;
  updated_at: string;
}

export interface Task {
  task_id: string;
  title: string;
  description: string;
  requester_id: string;
  owner_agent_id: string;
  collaborator_agent_ids: string[];
  status: TaskStatus;
  priority: Priority;
  due_date: string;
  acceptance_criteria: string;
  risk_level: RiskLevel;
  budget_limit_usd: number;
  created_at: string;
  updated_at: string;
}

export interface Run {
  run_id: string;
  task_id: string;
  agent_id: string;
  runtime_type: RuntimeType;
  status: string;
  started_at: string;
  ended_at: string | null;
  duration_ms: number;
  input_summary: string;
  output_summary: string;
  model_provider: string;
  model_name: string;
  input_tokens: number;
  output_tokens: number;
  reasoning_tokens: number;
  cost_usd: number;
  error_type: string | null;
  error_message: string | null;
  trace_id: string;
  parent_run_id: string | null;
  delegation_id: string | null;
  approval_required: boolean;
  created_at: string;
}

export interface ToolCall {
  tool_call_id: string;
  run_id: string;
  agent_id: string;
  tool_name: string;
  tool_version: string;
  tool_category: ToolCategory;
  normalized_args_json: string;
  target_resource: string;
  risk_level: RiskLevel;
  status: string;
  result_summary: string;
  started_at: string;
  ended_at: string;
  created_at: string;
}

export interface Approval {
  approval_id: string;
  task_id: string;
  run_id: string;
  tool_call_id: string;
  requested_by_agent_id: string;
  approver_user_id: string | null;
  decision: ApprovalDecision;
  reason: string;
  expires_at: string;
  created_at: string;
  decided_at: string | null;
}

export interface Memory {
  memory_id: string;
  scope: MemoryScope;
  memory_type: string;
  canonical_text: string;
  source_type: string;
  confidence: number;
  review_status: MemoryReviewStatus;
  task_id: string | null;
  agent_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Evaluation {
  evaluation_id: string;
  task_id: string;
  run_id: string;
  agent_id: string;
  evaluator_type: string;
  score: number;
  pass_fail: PassFail;
  notes: string;
  created_at: string;
}

export interface AuditLog {
  audit_id: string;
  actor_type: ActorType;
  actor_id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  metadata_json: string;
  created_at: string;
}

export interface RuntimeConnector {
  connector_id: string;
  provider: string;
  mode: string;
  status: string;
  last_checked: string;
  real_run_enabled: boolean;
  confirm_required: boolean;
  trust_status?: string;
  trust_note?: string;
  trust_updated_at?: string;
  observation_level?: string;
  risk_floor?: string;
  commercial_readiness?: string;
  capability_policy_hash?: string;
  capability_manifest?: Record<string, unknown>;
  endpoint: string;
  import_count?: number;
  last_event?: string;
}

export interface TemplatePackage {
  template_id: string;
  name: string;
  description: string;
  agent_roles: string[];
  base_bindings: string[];
  status: string;
}

// --- Agents ---
export const agents: Agent[] = [
  {
    agent_id: 'agt_research',
    name: 'Research Agent',
    role: 'Researcher',
    description: 'Performs competitive analysis, literature review, and market research.',
    runtime_type: 'claude_code',
    model_provider: 'anthropic',
    model_name: 'claude-sonnet-4-5',
    status: 'running',
    permission_level: 'standard',
    allowed_tools: ['browser.search', 'github.read', 'memory.propose', 'notion.read'],
    budget_limit_usd: 10,
    budget_used_usd: 3.42,
    owner_user_id: 'usr_jiwu',
    success_rate: 0.87,
    run_count: 47,
    failure_count: 6,
    approval_count: 3,
    created_at: '2026-06-01T08:00:00Z',
    updated_at: '2026-06-14T09:30:00Z',
  },
  {
    agent_id: 'agt_writer',
    name: 'Content Writer',
    role: 'Writer',
    description: 'Drafts reports, summaries, and documentation from research outputs.',
    runtime_type: 'codex',
    model_provider: 'openai',
    model_name: 'gpt-4o',
    status: 'idle',
    permission_level: 'standard',
    allowed_tools: ['file.write', 'notion.write', 'memory.propose'],
    budget_limit_usd: 5,
    budget_used_usd: 1.18,
    owner_user_id: 'usr_jiwu',
    success_rate: 0.94,
    run_count: 31,
    failure_count: 2,
    approval_count: 1,
    created_at: '2026-06-01T08:10:00Z',
    updated_at: '2026-06-14T08:00:00Z',
  },
  {
    agent_id: 'agt_ops',
    name: 'Ops Agent',
    role: 'Operator',
    description: 'Handles CI/CD, GitHub operations, and shell automation tasks.',
    runtime_type: 'openhands',
    model_provider: 'anthropic',
    model_name: 'claude-opus-4-8',
    status: 'paused',
    permission_level: 'elevated',
    allowed_tools: ['shell.exec', 'github.push', 'file.delete', 'database.write'],
    budget_limit_usd: 20,
    budget_used_usd: 9.75,
    owner_user_id: 'usr_jiwu',
    success_rate: 0.72,
    run_count: 25,
    failure_count: 7,
    approval_count: 12,
    created_at: '2026-06-02T10:00:00Z',
    updated_at: '2026-06-13T16:00:00Z',
  },
  {
    agent_id: 'agt_eval',
    name: 'Eval Agent',
    role: 'Evaluator',
    description: 'Runs quality gate checks and LLM-based evaluation on task outputs.',
    runtime_type: 'mock',
    model_provider: 'anthropic',
    model_name: 'claude-haiku-4-5',
    status: 'idle',
    permission_level: 'read_only',
    allowed_tools: ['memory.read', 'github.read'],
    budget_limit_usd: 2,
    budget_used_usd: 0.31,
    owner_user_id: 'usr_jiwu',
    success_rate: 0.98,
    run_count: 88,
    failure_count: 2,
    approval_count: 0,
    created_at: '2026-06-03T09:00:00Z',
    updated_at: '2026-06-14T07:00:00Z',
  },
  {
    agent_id: 'agt_openclaw',
    name: 'OpenClaw Import Agent',
    role: 'Importer',
    description: 'Imported from OpenClaw. Handles cron-based recurring research jobs.',
    runtime_type: 'openclaw',
    model_provider: 'openai',
    model_name: 'gpt-4o-mini',
    status: 'idle',
    permission_level: 'standard',
    allowed_tools: ['browser.search', 'file.read'],
    budget_limit_usd: 3,
    budget_used_usd: 0.88,
    owner_user_id: 'usr_jiwu',
    success_rate: 0.91,
    run_count: 22,
    failure_count: 2,
    approval_count: 0,
    created_at: '2026-06-10T12:00:00Z',
    updated_at: '2026-06-14T06:00:00Z',
  },
];

// --- Tasks ---
export const tasks: Task[] = [
  {
    task_id: 'tsk_competitor',
    title: 'Competitor Analysis: AgentOps vs LangSmith',
    description: 'Research top 5 competitors and produce a structured comparison report.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_research',
    collaborator_agent_ids: ['agt_writer'],
    status: 'running',
    priority: 'high',
    due_date: '2026-06-20T00:00:00Z',
    acceptance_criteria: 'Report covers pricing, features, positioning. Min 10 sources cited.',
    risk_level: 'low',
    budget_limit_usd: 8,
    created_at: '2026-06-10T09:00:00Z',
    updated_at: '2026-06-14T09:30:00Z',
  },
  {
    task_id: 'tsk_deploy',
    title: 'Deploy v1.2.2 to Staging Environment',
    description: 'Run migration scripts, update runtime connector config, verify probes.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_ops',
    collaborator_agent_ids: [],
    status: 'waiting_approval',
    priority: 'critical',
    due_date: '2026-06-15T18:00:00Z',
    acceptance_criteria: 'All health probes green. No regression in acceptance tests.',
    risk_level: 'high',
    budget_limit_usd: 5,
    created_at: '2026-06-13T14:00:00Z',
    updated_at: '2026-06-14T08:00:00Z',
  },
  {
    task_id: 'tsk_memo_review',
    title: 'Review Memory Candidates from Last Sprint',
    description: 'Approve or reject 6 memory candidates from tsk_competitor and tsk_eval runs.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_eval',
    collaborator_agent_ids: [],
    status: 'planned',
    priority: 'medium',
    due_date: '2026-06-16T00:00:00Z',
    acceptance_criteria: 'All candidates reviewed. Approved items promoted to project scope.',
    risk_level: 'low',
    budget_limit_usd: 1,
    created_at: '2026-06-12T10:00:00Z',
    updated_at: '2026-06-12T10:00:00Z',
  },
  {
    task_id: 'tsk_report',
    title: 'Write MIS Course Project Final Report',
    description: 'Produce 5000-word report covering system design, implementation, evaluation.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_writer',
    collaborator_agent_ids: ['agt_research', 'agt_eval'],
    status: 'completed',
    priority: 'high',
    due_date: '2026-06-12T23:59:00Z',
    acceptance_criteria: 'Report submitted. Score >= 85 on rubric evaluation.',
    risk_level: 'medium',
    budget_limit_usd: 6,
    created_at: '2026-06-05T08:00:00Z',
    updated_at: '2026-06-12T22:45:00Z',
  },
  {
    task_id: 'tsk_notion_export',
    title: 'Export Sprint Summary to Notion',
    description: 'Dry-run export of task summary and memory objects to Notion workspace.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_ops',
    collaborator_agent_ids: [],
    status: 'completed',
    priority: 'low',
    due_date: '2026-06-13T12:00:00Z',
    acceptance_criteria: 'Dry-run export succeeds. No real writeback without confirm.',
    risk_level: 'low',
    budget_limit_usd: 1,
    created_at: '2026-06-11T10:00:00Z',
    updated_at: '2026-06-13T11:30:00Z',
  },
  {
    task_id: 'tsk_failed_probe',
    title: 'Hermes Gateway Health Probe',
    description: 'Probe Hermes default gateway at 127.0.0.1:8642.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_eval',
    collaborator_agent_ids: [],
    status: 'failed',
    priority: 'medium',
    due_date: '2026-06-14T08:00:00Z',
    acceptance_criteria: 'Gateway responds with 200. Models endpoint reachable.',
    risk_level: 'medium',
    budget_limit_usd: 0.5,
    created_at: '2026-06-14T07:55:00Z',
    updated_at: '2026-06-14T08:01:00Z',
  },
  {
    task_id: 'tsk_cron_research',
    title: '[OpenClaw] Daily Market Signal Cron',
    description: 'Recurring OpenClaw cron job: scrape daily AI news signals.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_openclaw',
    collaborator_agent_ids: [],
    status: 'backlog',
    priority: 'low',
    due_date: '',
    acceptance_criteria: 'Output JSONL with min 5 signals per run.',
    risk_level: 'low',
    budget_limit_usd: 0.5,
    created_at: '2026-06-10T12:00:00Z',
    updated_at: '2026-06-14T06:00:00Z',
  },
  {
    task_id: 'tsk_eval_rubric',
    title: 'Setup Evaluation Rubric for Agent Outputs',
    description: 'Define rubric JSON for LLM-based quality gate across all agents.',
    requester_id: 'usr_jiwu',
    owner_agent_id: 'agt_eval',
    collaborator_agent_ids: [],
    status: 'blocked',
    priority: 'medium',
    due_date: '2026-06-17T00:00:00Z',
    acceptance_criteria: 'Rubric covers accuracy, format, citation, cost efficiency.',
    risk_level: 'low',
    budget_limit_usd: 0.5,
    created_at: '2026-06-09T09:00:00Z',
    updated_at: '2026-06-13T09:00:00Z',
  },
];

// --- Runs ---
export const runs: Run[] = [
  {
    run_id: 'run_001',
    task_id: 'tsk_competitor',
    agent_id: 'agt_research',
    runtime_type: 'claude_code',
    status: 'completed',
    started_at: '2026-06-14T09:00:00Z',
    ended_at: '2026-06-14T09:18:32Z',
    duration_ms: 1112000,
    input_summary: 'Research competitors: LangSmith, Weights & Biases, AgentOps.ai',
    output_summary: 'Found 7 competitors. Pricing matrix complete. 12 sources cited.',
    model_provider: 'anthropic',
    model_name: 'claude-sonnet-4-5',
    input_tokens: 3240,
    output_tokens: 8811,
    reasoning_tokens: 1200,
    cost_usd: 0.48,
    error_type: null,
    error_message: null,
    trace_id: 'trace_abc123',
    parent_run_id: null,
    delegation_id: null,
    approval_required: false,
    created_at: '2026-06-14T09:00:00Z',
  },
  {
    run_id: 'run_002',
    task_id: 'tsk_competitor',
    agent_id: 'agt_writer',
    runtime_type: 'codex',
    status: 'running',
    started_at: '2026-06-14T09:20:00Z',
    ended_at: null,
    duration_ms: 0,
    input_summary: 'Draft competitor comparison report from research output',
    output_summary: '',
    model_provider: 'openai',
    model_name: 'gpt-4o',
    input_tokens: 8811,
    output_tokens: 0,
    reasoning_tokens: 0,
    cost_usd: 0.12,
    error_type: null,
    error_message: null,
    trace_id: 'trace_def456',
    parent_run_id: 'run_001',
    delegation_id: 'del_001',
    approval_required: false,
    created_at: '2026-06-14T09:20:00Z',
  },
  {
    run_id: 'run_003',
    task_id: 'tsk_deploy',
    agent_id: 'agt_ops',
    runtime_type: 'openhands',
    status: 'waiting_approval',
    started_at: '2026-06-14T08:00:00Z',
    ended_at: null,
    duration_ms: 0,
    input_summary: 'Deploy v1.2.2: run migrations, restart services',
    output_summary: 'Migration step complete. Awaiting approval for shell.exec restart.',
    model_provider: 'anthropic',
    model_name: 'claude-opus-4-8',
    input_tokens: 1200,
    output_tokens: 400,
    reasoning_tokens: 800,
    cost_usd: 0.31,
    error_type: null,
    error_message: null,
    trace_id: 'trace_ghi789',
    parent_run_id: null,
    delegation_id: null,
    approval_required: true,
    created_at: '2026-06-14T08:00:00Z',
  },
  {
    run_id: 'run_004',
    task_id: 'tsk_report',
    agent_id: 'agt_writer',
    runtime_type: 'codex',
    status: 'completed',
    started_at: '2026-06-12T20:00:00Z',
    ended_at: '2026-06-12T22:41:00Z',
    duration_ms: 9660000,
    input_summary: 'Write final MIS course project report',
    output_summary: '5240 words. All sections complete. Rubric score 91/100.',
    model_provider: 'openai',
    model_name: 'gpt-4o',
    input_tokens: 12000,
    output_tokens: 18000,
    reasoning_tokens: 0,
    cost_usd: 1.32,
    error_type: null,
    error_message: null,
    trace_id: 'trace_jkl012',
    parent_run_id: null,
    delegation_id: null,
    approval_required: false,
    created_at: '2026-06-12T20:00:00Z',
  },
  {
    run_id: 'run_005',
    task_id: 'tsk_failed_probe',
    agent_id: 'agt_eval',
    runtime_type: 'hermes',
    status: 'failed',
    started_at: '2026-06-14T07:55:00Z',
    ended_at: '2026-06-14T07:55:12Z',
    duration_ms: 12000,
    input_summary: 'Probe Hermes gateway at 127.0.0.1:8642',
    output_summary: '',
    model_provider: '',
    model_name: '',
    input_tokens: 0,
    output_tokens: 0,
    reasoning_tokens: 0,
    cost_usd: 0,
    error_type: 'ConnectionRefusedError',
    error_message: 'Connection refused: 127.0.0.1:8642. Gateway not listening.',
    trace_id: 'trace_mno345',
    parent_run_id: null,
    delegation_id: null,
    approval_required: false,
    created_at: '2026-06-14T07:55:00Z',
  },
];

// --- Tool Calls ---
export const toolCalls: ToolCall[] = [
  {
    tool_call_id: 'tc_001',
    run_id: 'run_001',
    agent_id: 'agt_research',
    tool_name: 'browser.search',
    tool_version: 'v1',
    tool_category: 'browser',
    normalized_args_json: '{"query": "LangSmith pricing 2026"}',
    target_resource: 'https://smith.langchain.com',
    risk_level: 'low',
    status: 'completed',
    result_summary: 'Retrieved pricing page. Developer: free, Plus: $39/mo.',
    started_at: '2026-06-14T09:01:00Z',
    ended_at: '2026-06-14T09:01:08Z',
    created_at: '2026-06-14T09:01:00Z',
  },
  {
    tool_call_id: 'tc_002',
    run_id: 'run_001',
    agent_id: 'agt_research',
    tool_name: 'github.read',
    tool_version: 'v1',
    tool_category: 'github',
    normalized_args_json: '{"repo": "langchain-ai/langsmith-sdk"}',
    target_resource: 'github.com/langchain-ai/langsmith-sdk',
    risk_level: 'low',
    status: 'completed',
    result_summary: 'Read README and feature list. 3.2k stars.',
    started_at: '2026-06-14T09:03:00Z',
    ended_at: '2026-06-14T09:03:05Z',
    created_at: '2026-06-14T09:03:00Z',
  },
  {
    tool_call_id: 'tc_003',
    run_id: 'run_001',
    agent_id: 'agt_research',
    tool_name: 'memory.propose',
    tool_version: 'v1',
    tool_category: 'custom',
    normalized_args_json: '{"text": "LangSmith is priced at $39/mo for Plus tier"}',
    target_resource: 'memory_store',
    risk_level: 'low',
    status: 'completed',
    result_summary: 'Memory candidate created: mem_langsmith_pricing',
    started_at: '2026-06-14T09:15:00Z',
    ended_at: '2026-06-14T09:15:01Z',
    created_at: '2026-06-14T09:15:00Z',
  },
  {
    tool_call_id: 'tc_004',
    run_id: 'run_003',
    agent_id: 'agt_ops',
    tool_name: 'shell.exec',
    tool_version: 'v1',
    tool_category: 'shell',
    normalized_args_json: '{"cmd": "python3 scripts/migrate.py --version 1.2.1"}',
    target_resource: 'localhost',
    risk_level: 'high',
    status: 'pending_approval',
    result_summary: 'Awaiting human approval before execution.',
    started_at: '2026-06-14T08:10:00Z',
    ended_at: '',
    created_at: '2026-06-14T08:10:00Z',
  },
  {
    tool_call_id: 'tc_005',
    run_id: 'run_003',
    agent_id: 'agt_ops',
    tool_name: 'github.push',
    tool_version: 'v1',
    tool_category: 'github',
    normalized_args_json: '{"branch": "release/v1.2.2", "message": "deploy: v1.2.2 staging"}',
    target_resource: 'github.com/geogejoy107-jpg/agentops-mis-mvp',
    risk_level: 'high',
    status: 'pending_approval',
    result_summary: 'Awaiting approval: high-risk push to release branch.',
    started_at: '2026-06-14T08:11:00Z',
    ended_at: '',
    created_at: '2026-06-14T08:11:00Z',
  },
  {
    tool_call_id: 'tc_006',
    run_id: 'run_004',
    agent_id: 'agt_writer',
    tool_name: 'file.write',
    tool_version: 'v1',
    tool_category: 'file',
    normalized_args_json: '{"path": "outputs/final_report.md"}',
    target_resource: 'outputs/final_report.md',
    risk_level: 'medium',
    status: 'completed',
    result_summary: 'Wrote 5240 words to outputs/final_report.md',
    started_at: '2026-06-12T22:38:00Z',
    ended_at: '2026-06-12T22:38:02Z',
    created_at: '2026-06-12T22:38:00Z',
  },
  {
    tool_call_id: 'tc_007',
    run_id: 'run_004',
    agent_id: 'agt_writer',
    tool_name: 'notion.write',
    tool_version: 'v1',
    tool_category: 'notion',
    normalized_args_json: '{"page_title": "Final Report v1", "dry_run": true}',
    target_resource: 'notion.so/workspace',
    risk_level: 'low',
    status: 'completed',
    result_summary: 'Dry-run export preview generated. No real write performed.',
    started_at: '2026-06-12T22:40:00Z',
    ended_at: '2026-06-12T22:40:03Z',
    created_at: '2026-06-12T22:40:00Z',
  },
];

// --- Approvals ---
export const approvals: Approval[] = [
  {
    approval_id: 'apr_001',
    task_id: 'tsk_deploy',
    run_id: 'run_003',
    tool_call_id: 'tc_004',
    requested_by_agent_id: 'agt_ops',
    approver_user_id: null,
    decision: 'pending',
    reason: 'shell.exec: python3 scripts/migrate.py --version 1.2.1 on localhost',
    expires_at: '2026-06-14T20:00:00Z',
    created_at: '2026-06-14T08:10:00Z',
    decided_at: null,
  },
  {
    approval_id: 'apr_002',
    task_id: 'tsk_deploy',
    run_id: 'run_003',
    tool_call_id: 'tc_005',
    requested_by_agent_id: 'agt_ops',
    approver_user_id: null,
    decision: 'pending',
    reason: 'github.push to release/v1.2.2 branch',
    expires_at: '2026-06-14T20:00:00Z',
    created_at: '2026-06-14T08:11:00Z',
    decided_at: null,
  },
  {
    approval_id: 'apr_003',
    task_id: 'tsk_report',
    run_id: 'run_004',
    tool_call_id: 'tc_006',
    requested_by_agent_id: 'agt_writer',
    approver_user_id: 'usr_jiwu',
    decision: 'approved',
    reason: 'Low-risk file write reviewed. Output matches expected format.',
    expires_at: '2026-06-13T00:00:00Z',
    created_at: '2026-06-12T22:37:00Z',
    decided_at: '2026-06-12T22:37:45Z',
  },
];

// --- Memory Candidates ---
export const memories: Memory[] = [
  {
    memory_id: 'mem_001',
    scope: 'project',
    memory_type: 'decision',
    canonical_text: 'LangSmith Plus tier is priced at $39/month as of June 2026.',
    source_type: 'run_log',
    confidence: 0.92,
    review_status: 'candidate',
    task_id: 'tsk_competitor',
    agent_id: 'agt_research',
    created_at: '2026-06-14T09:15:00Z',
    updated_at: '2026-06-14T09:15:00Z',
  },
  {
    memory_id: 'mem_002',
    scope: 'project',
    memory_type: 'risk',
    canonical_text: 'Hermes default gateway at 127.0.0.1:8642 is unavailable in current environment.',
    source_type: 'run_log',
    confidence: 1.0,
    review_status: 'candidate',
    task_id: 'tsk_failed_probe',
    agent_id: 'agt_eval',
    created_at: '2026-06-14T07:56:00Z',
    updated_at: '2026-06-14T07:56:00Z',
  },
  {
    memory_id: 'mem_003',
    scope: 'org',
    memory_type: 'policy',
    canonical_text: 'All shell.exec tool calls require human approval before execution.',
    source_type: 'manual',
    confidence: 1.0,
    review_status: 'approved',
    task_id: null,
    agent_id: null,
    created_at: '2026-06-01T00:00:00Z',
    updated_at: '2026-06-01T00:00:00Z',
  },
  {
    memory_id: 'mem_004',
    scope: 'project',
    memory_type: 'agent_lesson',
    canonical_text: 'Research Agent achieves best output quality when given structured competitor template before starting browser search.',
    source_type: 'run_log',
    confidence: 0.78,
    review_status: 'candidate',
    task_id: 'tsk_competitor',
    agent_id: 'agt_research',
    created_at: '2026-06-14T09:18:00Z',
    updated_at: '2026-06-14T09:18:00Z',
  },
  {
    memory_id: 'mem_005',
    scope: 'task',
    memory_type: 'artifact_summary',
    canonical_text: 'Final report submitted: outputs/final_report.md, 5240 words, rubric score 91/100.',
    source_type: 'run_log',
    confidence: 1.0,
    review_status: 'approved',
    task_id: 'tsk_report',
    agent_id: 'agt_writer',
    created_at: '2026-06-12T22:45:00Z',
    updated_at: '2026-06-12T22:45:00Z',
  },
  {
    memory_id: 'mem_006',
    scope: 'project',
    memory_type: 'commitment',
    canonical_text: 'Notion export defaults to dry_run=true. Real write requires confirm_export=true explicitly.',
    source_type: 'manual',
    confidence: 1.0,
    review_status: 'candidate',
    task_id: null,
    agent_id: null,
    created_at: '2026-06-11T09:00:00Z',
    updated_at: '2026-06-11T09:00:00Z',
  },
];

// --- Evaluations ---
export const evaluations: Evaluation[] = [
  {
    evaluation_id: 'eval_001',
    task_id: 'tsk_report',
    run_id: 'run_004',
    agent_id: 'agt_writer',
    evaluator_type: 'llm_mock',
    score: 91,
    pass_fail: 'pass',
    notes: 'All acceptance criteria met. 5240 words, 12 sources cited, sections complete.',
    created_at: '2026-06-12T22:42:00Z',
  },
  {
    evaluation_id: 'eval_002',
    task_id: 'tsk_competitor',
    run_id: 'run_001',
    agent_id: 'agt_research',
    evaluator_type: 'rule',
    score: 84,
    pass_fail: 'pass',
    notes: '7 competitors found. Pricing matrix complete. Slight gaps in enterprise tier data.',
    created_at: '2026-06-14T09:18:00Z',
  },
  {
    evaluation_id: 'eval_003',
    task_id: 'tsk_failed_probe',
    run_id: 'run_005',
    agent_id: 'agt_eval',
    evaluator_type: 'rule',
    score: 0,
    pass_fail: 'fail',
    notes: 'Gateway probe failed: connection refused. Health state recorded as unavailable.',
    created_at: '2026-06-14T07:56:00Z',
  },
  {
    evaluation_id: 'eval_004',
    task_id: 'tsk_notion_export',
    run_id: 'run_004',
    agent_id: 'agt_ops',
    evaluator_type: 'human',
    score: 100,
    pass_fail: 'pass',
    notes: 'Dry-run export preview verified. No unintended write occurred.',
    created_at: '2026-06-13T11:30:00Z',
  },
];

// --- Audit Logs ---
export const auditLogs: AuditLog[] = [
  {
    audit_id: 'aud_001',
    actor_type: 'agent',
    actor_id: 'agt_research',
    action: 'run.created',
    entity_type: 'run',
    entity_id: 'run_001',
    metadata_json: '{"task_id": "tsk_competitor", "runtime": "claude_code"}',
    created_at: '2026-06-14T09:00:00Z',
  },
  {
    audit_id: 'aud_002',
    actor_type: 'agent',
    actor_id: 'agt_ops',
    action: 'tool_call.approval_requested',
    entity_type: 'tool_call',
    entity_id: 'tc_004',
    metadata_json: '{"tool": "shell.exec", "risk_level": "high"}',
    created_at: '2026-06-14T08:10:00Z',
  },
  {
    audit_id: 'aud_003',
    actor_type: 'system',
    actor_id: 'mis_system',
    action: 'connector.health_check',
    entity_type: 'runtime_connector',
    entity_id: 'rtc_hermes_default',
    metadata_json: '{"status": "unavailable", "port": 8642}',
    created_at: '2026-06-14T07:55:12Z',
  },
  {
    audit_id: 'aud_004',
    actor_type: 'user',
    actor_id: 'usr_jiwu',
    action: 'approval.approved',
    entity_type: 'approval',
    entity_id: 'apr_003',
    metadata_json: '{"tool": "file.write", "decision": "approved"}',
    created_at: '2026-06-12T22:37:45Z',
  },
  {
    audit_id: 'aud_005',
    actor_type: 'agent',
    actor_id: 'agt_writer',
    action: 'memory.proposed',
    entity_type: 'memory',
    entity_id: 'mem_005',
    metadata_json: '{"scope": "task", "confidence": 1.0}',
    created_at: '2026-06-12T22:45:00Z',
  },
  {
    audit_id: 'aud_006',
    actor_type: 'system',
    actor_id: 'mis_system',
    action: 'openclaw.import_completed',
    entity_type: 'agent',
    entity_id: 'agt_openclaw',
    metadata_json: '{"agents": 1, "tasks": 3, "runs": 22}',
    created_at: '2026-06-10T12:05:00Z',
  },
  {
    audit_id: 'aud_007',
    actor_type: 'user',
    actor_id: 'usr_jiwu',
    action: 'notion.dry_run_export',
    entity_type: 'connector',
    entity_id: 'con_notion',
    metadata_json: '{"dry_run": true, "confirm_export": false}',
    created_at: '2026-06-13T11:25:00Z',
  },
  {
    audit_id: 'aud_008',
    actor_type: 'agent',
    actor_id: 'agt_eval',
    action: 'evaluation.created',
    entity_type: 'evaluation',
    entity_id: 'eval_001',
    metadata_json: '{"score": 91, "pass_fail": "pass"}',
    created_at: '2026-06-12T22:42:00Z',
  },
  {
    audit_id: 'aud_009',
    actor_type: 'system',
    actor_id: 'mis_system',
    action: 'run.failed',
    entity_type: 'run',
    entity_id: 'run_005',
    metadata_json: '{"error": "ConnectionRefusedError", "connector": "rtc_hermes_default"}',
    created_at: '2026-06-14T07:55:12Z',
  },
  {
    audit_id: 'aud_010',
    actor_type: 'user',
    actor_id: 'usr_jiwu',
    action: 'task.created',
    entity_type: 'task',
    entity_id: 'tsk_deploy',
    metadata_json: '{"priority": "critical", "risk_level": "high"}',
    created_at: '2026-06-13T14:00:00Z',
  },
];

// --- Runtime Connectors ---
export const runtimeConnectors: RuntimeConnector[] = [
  {
    connector_id: 'rtc_openclaw',
    provider: 'OpenClaw',
    mode: 'import_only',
    status: 'ready',
    last_checked: '2026-06-14T06:00:00Z',
    real_run_enabled: false,
    confirm_required: false,
    endpoint: '~/.openclaw/',
    import_count: 26,
    last_event: 'Import completed: 1 agent, 3 tasks, 22 runs',
  },
  {
    connector_id: 'rtc_hermes_default',
    provider: 'Hermes Default Gateway',
    mode: 'health_only',
    status: 'unavailable',
    last_checked: '2026-06-14T07:55:12Z',
    real_run_enabled: false,
    confirm_required: true,
    endpoint: 'http://127.0.0.1:8642',
    last_event: 'Health check failed: connection refused on port 8642',
  },
  {
    connector_id: 'rtc_agnesfallback_cli',
    provider: 'Agnesfallback CLI',
    mode: 'cli_probe',
    status: 'live',
    last_checked: '2026-06-14T08:30:00Z',
    real_run_enabled: true,
    confirm_required: true,
    endpoint: '~/.local/bin/agnesfallback',
    last_event: 'Fixed probe completed. Safe prompt executed without --yolo.',
  },
  {
    connector_id: 'rtc_agnesfallback_openai_api',
    provider: 'Agnesfallback OpenAI API',
    mode: 'openai_compatible',
    status: 'dry_run',
    last_checked: '2026-06-14T08:31:00Z',
    real_run_enabled: false,
    confirm_required: true,
    endpoint: 'http://127.0.0.1:8643',
    last_event: 'Dry-run preview only. Real run requires HERMES_ALLOW_REAL_RUN=true.',
  },
];

// --- Template Packages ---
export const templatePackages: TemplatePackage[] = [
  {
    template_id: 'tpl_ai_software_team',
    name: 'AI Software Team',
    description: 'Full-stack AI engineering team: researcher, writer, ops agent, eval agent. Covers sprint-based task management.',
    agent_roles: ['Researcher', 'Writer', 'Operator', 'Evaluator'],
    base_bindings: ['Agent-MIS Local', 'GitHub', 'Notion'],
    status: 'active',
  },
  {
    template_id: 'tpl_ai_experiment_eval',
    name: 'AI Experiment Evaluation',
    description: 'Evaluation-first template for ML experiment tracking with W&B integration and structured rubric QA.',
    agent_roles: ['Evaluator', 'Researcher'],
    base_bindings: ['Agent-MIS Local', 'W&B'],
    status: 'planned',
  },
  {
    template_id: 'tpl_content_studio',
    name: 'Content Studio',
    description: 'Content production pipeline: research → draft → review → publish. Notion as primary content base.',
    agent_roles: ['Researcher', 'Writer', 'Reviewer'],
    base_bindings: ['Agent-MIS Local', 'Notion', 'Docmost'],
    status: 'planned',
  },
  {
    template_id: 'tpl_ai_knowledge_base_bot',
    name: 'AI Knowledge Base / Q&A Bot',
    description: 'Document cleaning, Dify/OpenAI File Search/AnythingLLM connector choice, chunking, embeddings, citations, evaluation and approval-gated upload.',
    agent_roles: ['Planner', 'Document Cleaner', 'Knowledge Builder', 'Evaluator', 'Reporter'],
    base_bindings: ['Agent-MIS Local', 'Dify', 'OpenAI File Search', 'AnythingLLM'],
    status: 'active',
  },
  {
    template_id: 'tpl_one_person_ops',
    name: 'One-Person Company Ops',
    description: 'Solo operator template: single agent handling research, writing, and lightweight ops with minimal approval overhead.',
    agent_roles: ['GeneralistAgent'],
    base_bindings: ['Agent-MIS Local', 'Notion'],
    status: 'planned',
  },
];

// --- Dashboard metrics (matches /api/dashboard/metrics shape) ---
export const dashboardMetrics = {
  total_agents: 5,
  total_tasks: 8,
  total_runs: 10,
  pending_approvals: 2,
  runtime_health: { openclaw: 'ready', hermes: 'unavailable', notion: 'dry_run' },
  failure_rate: 0.12,
  total_cost_usd: 2.22,
  memory_candidates: 4,
  openclaw_import: { agents: 1, tasks: 3, runs: 22, failed_gates: 0 },
  audit_risk_flags: 2,
  run_volume_by_day: [
    { date: '06-08', runs: 3 },
    { date: '06-09', runs: 5 },
    { date: '06-10', runs: 8 },
    { date: '06-11', runs: 6 },
    { date: '06-12', runs: 12 },
    { date: '06-13', runs: 7 },
    { date: '06-14', runs: 5 },
  ],
  cost_by_agent: [
    { agent: 'Research', cost: 0.48 },
    { agent: 'Writer', cost: 1.44 },
    { agent: 'Ops', cost: 0.31 },
    { agent: 'Eval', cost: 0.31 },
    { agent: 'OpenClaw', cost: 0.88 },
  ],
};
