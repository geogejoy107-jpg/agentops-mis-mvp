import type { Agent, Approval, AuditLog, Memory, Run, Task } from "../../data/mockData";
import type { DashboardMetrics } from "../../data/liveApi";

export type PixelLocale = "en" | "zh";

export type PixelZoneId =
  | "control_tower"
  | "agent_lobby"
  | "task_hall"
  | "runtime_lab"
  | "tool_workshop"
  | "approval_gate"
  | "evaluation_room"
  | "memory_archive"
  | "audit_vault"
  | "external_base_dock"
  | "run_stream"
  | "incident_corner"
  | "template_market";

export type PixelTone = "neutral" | "ready" | "active" | "warning" | "danger" | "purple" | "dock";

export interface PixelZoneDefinition {
  id: PixelZoneId;
  label: string;
  route: string;
  description: string;
  x: number;
  y: number;
  w: number;
  h: number;
  tone: PixelTone;
  metricLabel: string;
}

export interface PixelMetrics {
  totalAgents: number;
  totalRuns: number;
  activeRuns: number;
  pendingApprovals: number;
  failedQualityGates: number;
  memoryCandidates: number;
  failedRuns: number;
  blockedTasks: number;
  auditEvents: number;
  runtimeHealth: string;
  externalSyncState: string;
  latestAudit: string;
}

export interface PixelAgent {
  id: string;
  name: string;
  role: string;
  runtime: string;
  status: string;
  currentZone: PixelZoneId;
  targetZone: PixelZoneId;
  taskTitle?: string;
  latestRunId?: string;
  risk: "low" | "medium" | "high" | "critical";
  approvalState?: string;
  routeToDetail?: string;
  isDemo?: boolean;
}

export type PixelTaskGroup = "New / Planned" | "Running" | "Waiting Approval" | "Completed" | "Failed / Blocked";

export interface PixelTaskCard {
  id: string;
  title: string;
  assignedAgent: string;
  risk: "low" | "medium" | "high" | "critical";
  status: string;
  group: PixelTaskGroup;
  route: string;
}

export const PIXEL_ZONES: PixelZoneDefinition[] = [
  {
    id: "control_tower",
    label: "Control Tower",
    route: "/admin",
    description: "KPI, runtime health, cost, risk and incident overview.",
    x: 3,
    y: 4,
    w: 18,
    h: 13,
    tone: "purple",
    metricLabel: "KPI",
  },
  {
    id: "agent_lobby",
    label: "Agent Lobby",
    route: "/workspace/agents",
    description: "Agent identity, role, permission, owner and runtime status.",
    x: 25,
    y: 6,
    w: 17,
    h: 14,
    tone: "neutral",
    metricLabel: "agents",
  },
  {
    id: "task_hall",
    label: "Task Hall",
    route: "/workspace/tasks",
    description: "Task queue, dispatch, assignment, priority and risk triage.",
    x: 46,
    y: 5,
    w: 24,
    h: 21,
    tone: "active",
    metricLabel: "tasks",
  },
  {
    id: "run_stream",
    label: "Run Stream",
    route: "/admin/runs",
    description: "Run ledger, delegation chain, runtime history and replay entry.",
    x: 73,
    y: 6,
    w: 22,
    h: 14,
    tone: "active",
    metricLabel: "runs",
  },
  {
    id: "runtime_lab",
    label: "Runtime Lab",
    route: "/admin/connectors",
    description: "OpenClaw, Hermes, Agnesfallback and OpenAI-compatible runtime connectors.",
    x: 6,
    y: 25,
    w: 23,
    h: 18,
    tone: "purple",
    metricLabel: "runtime",
  },
  {
    id: "tool_workshop",
    label: "Tool Workshop",
    route: "/admin/toolcalls",
    description: "GitHub, shell, browser, API, Notion and other tool-call execution evidence.",
    x: 33,
    y: 29,
    w: 20,
    h: 17,
    tone: "active",
    metricLabel: "tools",
  },
  {
    id: "approval_gate",
    label: "Approval Gate",
    route: "/workspace/approvals",
    description: "High-risk action approval, rejection, escalation and evidence capture.",
    x: 58,
    y: 32,
    w: 18,
    h: 16,
    tone: "warning",
    metricLabel: "pending",
  },
  {
    id: "evaluation_room",
    label: "Evaluation Room",
    route: "/admin/evaluations",
    description: "Quality gates, evaluator scores, pass/fail reasons and improvement loops.",
    x: 79,
    y: 28,
    w: 17,
    h: 18,
    tone: "ready",
    metricLabel: "quality",
  },
  {
    id: "memory_archive",
    label: "Memory Archive",
    route: "/workspace/memory",
    description: "SOPs, decisions, memory candidates, failure cases and provenance review.",
    x: 6,
    y: 51,
    w: 22,
    h: 19,
    tone: "dock",
    metricLabel: "memory",
  },
  {
    id: "external_base_dock",
    label: "External Base Dock",
    route: "/admin/bases/notion",
    description: "Notion, W&B, Plane, Docmost and Mattermost sync configuration.",
    x: 33,
    y: 56,
    w: 22,
    h: 18,
    tone: "dock",
    metricLabel: "sync",
  },
  {
    id: "audit_vault",
    label: "Audit Vault",
    route: "/admin/audit",
    description: "Append-only audit events, hash-chain proof, actor/action/entity evidence.",
    x: 59,
    y: 56,
    w: 18,
    h: 17,
    tone: "neutral",
    metricLabel: "audit",
  },
  {
    id: "incident_corner",
    label: "Incident Corner",
    route: "/admin/runs",
    description: "Failed runs, blocked tasks, runtime errors and recovery pointers.",
    x: 81,
    y: 55,
    w: 16,
    h: 18,
    tone: "danger",
    metricLabel: "failed",
  },
  {
    id: "template_market",
    label: "Template Market",
    route: "/admin/templates",
    description: "Template packages, base binding previews and safe migration checks.",
    x: 37,
    y: 80,
    w: 26,
    h: 13,
    tone: "ready",
    metricLabel: "templates",
  },
];

export const PIXEL_ZONE_BY_ID = PIXEL_ZONES.reduce<Record<PixelZoneId, PixelZoneDefinition>>((acc, zone) => {
  acc[zone.id] = zone;
  return acc;
}, {} as Record<PixelZoneId, PixelZoneDefinition>);

const ZONE_COPY: Record<PixelZoneId, { zh: { label: string; description: string; metricLabel: string }; en: { label: string; description: string; metricLabel: string } }> = {
  control_tower: {
    en: { label: "Control Tower", description: "KPI, runtime health, cost, risk and incident overview.", metricLabel: "KPI" },
    zh: { label: "控制塔", description: "查看 KPI、运行时健康、成本、风险和故障概览。", metricLabel: "指标" },
  },
  agent_lobby: {
    en: { label: "Agent Lobby", description: "Agent identity, role, permission, owner and runtime status.", metricLabel: "agents" },
    zh: { label: "代理大厅", description: "管理 AI 员工身份、角色、权限、负责人和运行状态。", metricLabel: "代理" },
  },
  task_hall: {
    en: { label: "Task Hall", description: "Task queue, dispatch, assignment, priority and risk triage.", metricLabel: "tasks" },
    zh: { label: "派活大厅", description: "客户任务队列、派工、优先级、风险和验收标准。", metricLabel: "任务" },
  },
  run_stream: {
    en: { label: "Run Stream", description: "Run ledger, delegation chain, runtime history and replay entry.", metricLabel: "runs" },
    zh: { label: "运行流水", description: "查看运行账本、父子代理链路、历史记录和复盘入口。", metricLabel: "运行" },
  },
  runtime_lab: {
    en: { label: "Runtime Lab", description: "OpenClaw, Hermes, Agnesfallback and OpenAI-compatible runtime connectors.", metricLabel: "runtime" },
    zh: { label: "运行时实验室", description: "管理 OpenClaw、Hermes、Agnesfallback 和 OpenAI-compatible 接口。", metricLabel: "连接器" },
  },
  tool_workshop: {
    en: { label: "Tool Workshop", description: "GitHub, shell, browser, API, Notion and other tool-call execution evidence.", metricLabel: "tools" },
    zh: { label: "工具工坊", description: "追踪 GitHub、Shell、浏览器、API、Notion 等工具调用证据。", metricLabel: "工具" },
  },
  approval_gate: {
    en: { label: "Approval Gate", description: "High-risk action approval, rejection, escalation and evidence capture.", metricLabel: "pending" },
    zh: { label: "审批闸口", description: "处理高风险动作的批准、拒绝、升级和证据留存。", metricLabel: "待审" },
  },
  evaluation_room: {
    en: { label: "Evaluation Room", description: "Quality gates, evaluator scores, pass/fail reasons and improvement loops.", metricLabel: "quality" },
    zh: { label: "质量评估室", description: "查看质量门、评分、通过/失败原因和改进闭环。", metricLabel: "质量" },
  },
  memory_archive: {
    en: { label: "Memory Archive", description: "SOPs, decisions, memory candidates, failure cases and provenance review.", metricLabel: "memory" },
    zh: { label: "记忆档案馆", description: "审核 SOP、决策、候选记忆、失败案例和来源证据。", metricLabel: "记忆" },
  },
  external_base_dock: {
    en: { label: "External Base Dock", description: "Notion, W&B, Plane, Docmost and Mattermost sync configuration.", metricLabel: "sync" },
    zh: { label: "外部库码头", description: "配置 Notion、W&B、Plane、Docmost、Mattermost 等外部库同步。", metricLabel: "同步" },
  },
  audit_vault: {
    en: { label: "Audit Vault", description: "Append-only audit events, hash-chain proof, actor/action/entity evidence.", metricLabel: "audit" },
    zh: { label: "审计保险库", description: "保存追加式审计事件、哈希链证明和操作者证据。", metricLabel: "审计" },
  },
  incident_corner: {
    en: { label: "Incident Corner", description: "Failed runs, blocked tasks, runtime errors and recovery pointers.", metricLabel: "failed" },
    zh: { label: "故障角", description: "集中处理失败运行、阻塞任务、运行时错误和恢复线索。", metricLabel: "故障" },
  },
  template_market: {
    en: { label: "Template Market", description: "Template packages, base binding previews and safe migration checks.", metricLabel: "templates" },
    zh: { label: "模板市场", description: "管理模板包、外部库绑定预览和安全迁移检查。", metricLabel: "模板" },
  },
};

const TASK_GROUP_COPY: Record<PixelTaskGroup, { en: string; zh: string }> = {
  "New / Planned": { en: "New / Planned", zh: "新建 / 已计划" },
  Running: { en: "Running", zh: "运行中" },
  "Waiting Approval": { en: "Waiting Approval", zh: "等待审批" },
  Completed: { en: "Completed", zh: "已完成" },
  "Failed / Blocked": { en: "Failed / Blocked", zh: "失败 / 阻塞" },
};

const STATUS_COPY: Record<string, { en: string; zh: string }> = {
  running: { en: "Running", zh: "运行中" },
  completed: { en: "Completed", zh: "已完成" },
  planned: { en: "Planned", zh: "已计划" },
  backlog: { en: "Backlog", zh: "待排期" },
  waiting_approval: { en: "Waiting approval", zh: "等待审批" },
  pending_approval: { en: "Pending approval", zh: "待审批" },
  failed: { en: "Failed", zh: "失败" },
  blocked: { en: "Blocked", zh: "阻塞" },
  error: { en: "Error", zh: "错误" },
  idle: { en: "Idle", zh: "空闲" },
  unavailable: { en: "Unavailable", zh: "不可用" },
  candidate_review: { en: "Candidate review", zh: "候选审核" },
  syncing: { en: "Syncing", zh: "同步中" },
  auditing: { en: "Auditing", zh: "审计中" },
};

export function zoneDisplay(zone: PixelZoneDefinition, locale: PixelLocale) {
  return ZONE_COPY[zone.id]?.[locale] || {
    label: zone.label,
    description: zone.description,
    metricLabel: zone.metricLabel,
  };
}

export function taskGroupDisplay(group: PixelTaskGroup, locale: PixelLocale) {
  return TASK_GROUP_COPY[group]?.[locale] || group;
}

export function statusDisplay(status: string, locale: PixelLocale) {
  return STATUS_COPY[status]?.[locale] || status.replaceAll("_", " ");
}

export function externalSyncDisplay(value: string, locale: PixelLocale) {
  if (locale !== "zh") return value;
  if (value === "review queue") return "审核队列";
  if (value === "Notion dry-run ready") return "Notion 安全预演就绪";
  return value;
}

export function runtimeHealthDisplay(value: string, locale: PixelLocale) {
  if (locale !== "zh") return value;
  if (value === "ready") return "就绪";
  if (value === "mixed") return "混合";
  if (value === "demo-safe") return "演示安全";
  if (value === "unavailable") return "不可用";
  return value;
}

export const DEMO_AGENTS: PixelAgent[] = [
  {
    id: "demo_research",
    name: "Research Agent",
    role: "Researcher",
    runtime: "claude_code",
    status: "running",
    currentZone: "agent_lobby",
    targetZone: "task_hall",
    taskTitle: "Competitor reference audit",
    latestRunId: "demo_run_research",
    risk: "low",
    routeToDetail: "/workspace/agents",
    isDemo: true,
  },
  {
    id: "demo_coder",
    name: "Coding Agent",
    role: "Builder",
    runtime: "codex",
    status: "running",
    currentZone: "task_hall",
    targetZone: "runtime_lab",
    taskTitle: "React/Vite UI update",
    latestRunId: "demo_run_coder",
    risk: "medium",
    routeToDetail: "/workspace/agents",
    isDemo: true,
  },
  {
    id: "demo_reviewer",
    name: "Reviewer Agent",
    role: "Quality Gate",
    runtime: "mock",
    status: "waiting_approval",
    currentZone: "runtime_lab",
    targetZone: "approval_gate",
    taskTitle: "High-risk tool approval",
    latestRunId: "demo_run_review",
    risk: "high",
    approvalState: "pending",
    routeToDetail: "/workspace/approvals",
    isDemo: true,
  },
  {
    id: "demo_memory",
    name: "Memory Curator",
    role: "Archivist",
    runtime: "hermes",
    status: "candidate_review",
    currentZone: "approval_gate",
    targetZone: "memory_archive",
    taskTitle: "Promote SOP memory",
    latestRunId: "demo_run_memory",
    risk: "low",
    routeToDetail: "/workspace/memory",
    isDemo: true,
  },
  {
    id: "demo_connector",
    name: "Connector Bot",
    role: "Sync",
    runtime: "openclaw",
    status: "syncing",
    currentZone: "memory_archive",
    targetZone: "external_base_dock",
    taskTitle: "Notion dry-run export",
    latestRunId: "demo_run_sync",
    risk: "medium",
    routeToDetail: "/admin/bases/notion",
    isDemo: true,
  },
  {
    id: "demo_audit",
    name: "Audit Bot",
    role: "Evidence",
    runtime: "mock",
    status: "auditing",
    currentZone: "external_base_dock",
    targetZone: "audit_vault",
    taskTitle: "Record approval evidence",
    latestRunId: "demo_run_audit",
    risk: "low",
    routeToDetail: "/admin/audit",
    isDemo: true,
  },
];

export const DEMO_AGENT_CYCLE: PixelZoneId[] = [
  "agent_lobby",
  "task_hall",
  "runtime_lab",
  "tool_workshop",
  "approval_gate",
  "evaluation_room",
  "memory_archive",
  "external_base_dock",
  "audit_vault",
  "run_stream",
  "incident_corner",
];

export function zoneCenter(zone: PixelZoneDefinition, index = 0) {
  const offsets = [
    { x: 0.2, y: 0.25 },
    { x: 0.55, y: 0.25 },
    { x: 0.35, y: 0.58 },
    { x: 0.68, y: 0.58 },
    { x: 0.18, y: 0.62 },
  ];
  const offset = offsets[index % offsets.length];
  return {
    x: zone.x + zone.w * offset.x,
    y: zone.y + zone.h * offset.y,
  };
}

export function taskGroup(status: string): PixelTaskGroup {
  if (["running"].includes(status)) return "Running";
  if (["waiting_approval", "pending_approval"].includes(status)) return "Waiting Approval";
  if (["completed"].includes(status)) return "Completed";
  if (["failed", "blocked", "error"].includes(status)) return "Failed / Blocked";
  return "New / Planned";
}

export function statusToZone(status: string): PixelZoneId {
  if (["running", "executing"].includes(status)) return "runtime_lab";
  if (["waiting_approval", "pending", "pending_approval", "paused"].includes(status)) return "approval_gate";
  if (["candidate", "candidate_review", "memory", "stale"].includes(status)) return "memory_archive";
  if (["failed", "blocked", "error", "unavailable"].includes(status)) return "incident_corner";
  if (["completed", "pass", "evaluating"].includes(status)) return "evaluation_room";
  if (["syncing", "dry_run"].includes(status)) return "external_base_dock";
  if (["auditing", "audit"].includes(status)) return "audit_vault";
  return "agent_lobby";
}

export function deriveTaskCards(tasks: Task[]): PixelTaskCard[] {
  return tasks.slice(0, 10).map((task) => ({
    id: task.task_id,
    title: task.title,
    assignedAgent: task.owner_agent_id || "unassigned",
    risk: task.risk_level,
    status: task.status,
    group: taskGroup(task.status),
    route: task.task_id ? `/admin/tasks/${task.task_id}` : "/workspace/tasks",
  }));
}

export function derivePixelAgents(input: {
  agents?: Agent[];
  tasks?: Task[];
  approvals?: Approval[];
  runs?: Run[];
  memories?: Memory[];
}): PixelAgent[] {
  const agents = input.agents || [];
  if (agents.length === 0) return DEMO_AGENTS;

  const tasks = input.tasks || [];
  const approvals = input.approvals || [];
  const runs = input.runs || [];
  const memories = input.memories || [];

  return agents.slice(0, 12).map((agent, index) => {
    const pendingApproval = approvals.find((approval) =>
      approval.decision === "pending" && approval.requested_by_agent_id === agent.agent_id,
    );
    const activeRun = runs.find((run) =>
      run.agent_id === agent.agent_id && ["running", "waiting_approval", "pending_approval"].includes(run.status),
    );
    const failedRun = runs.find((run) =>
      run.agent_id === agent.agent_id && ["failed", "error", "blocked", "timeout"].includes(run.status),
    );
    const activeTask = tasks.find((task) =>
      task.owner_agent_id === agent.agent_id && ["running", "waiting_approval", "blocked", "planned"].includes(task.status),
    );
    const memoryCandidate = memories.find((memory) =>
      memory.agent_id === agent.agent_id && memory.review_status === "candidate",
    );

    let targetZone: PixelZoneId = statusToZone(agent.status);
    let status = agent.status;

    if (pendingApproval) {
      targetZone = "approval_gate";
      status = "waiting_approval";
    } else if (failedRun || activeTask?.status === "failed" || activeTask?.status === "blocked") {
      targetZone = "incident_corner";
      status = failedRun?.status || activeTask?.status || agent.status;
    } else if (activeRun) {
      targetZone = statusToZone(activeRun.status);
      status = activeRun.status;
    } else if (activeTask) {
      targetZone = activeTask.status === "planned" ? "task_hall" : statusToZone(activeTask.status);
      status = activeTask.status;
    } else if (memoryCandidate) {
      targetZone = "memory_archive";
      status = "candidate_review";
    } else if (["openclaw", "hermes"].includes(agent.runtime_type)) {
      targetZone = "runtime_lab";
    }

    return {
      id: agent.agent_id,
      name: agent.name,
      role: agent.role,
      runtime: agent.runtime_type,
      status,
      currentZone: DEMO_AGENT_CYCLE[index % DEMO_AGENT_CYCLE.length],
      targetZone,
      taskTitle: activeTask?.title,
      latestRunId: activeRun?.run_id || failedRun?.run_id,
      risk: activeTask?.risk_level || (agent.failure_count > 5 ? "high" : "low"),
      approvalState: pendingApproval?.decision,
      routeToDetail: agent.agent_id ? `/admin/agents/${agent.agent_id}` : "/workspace/agents",
    };
  });
}

export function derivePixelMetrics(input: {
  metrics?: DashboardMetrics | null;
  tasks?: Task[];
  approvals?: Approval[];
  runs?: Run[];
  memories?: Memory[];
  audit?: AuditLog[];
}): PixelMetrics {
  const tasks = input.tasks || [];
  const approvals = input.approvals || [];
  const runs = input.runs || [];
  const memories = input.memories || [];
  const audit = input.audit || [];
  const metrics = input.metrics || null;
  const runtime = metrics?.runtime_health?.[0] as Record<string, unknown> | undefined;
  const failedRuns = runs.filter((run) => ["failed", "error", "blocked", "timeout"].includes(run.status)).length;
  const pendingApprovals = approvals.filter((approval) => approval.decision === "pending").length;
  const memoryCandidates = memories.filter((memory) => memory.review_status === "candidate").length;
  const latestAudit = audit[0]
    ? `${audit[0].action || "event"} · ${audit[0].entity_type || audit[0].actor_type}`
    : runs[0]?.run_id || approvals[0]?.approval_id || "demo_audit_event";

  return {
    totalAgents: metrics?.agents_total ?? Math.max(DEMO_AGENTS.length, metrics?.agent_performance_summary?.length || 0),
    totalRuns: runs.length || metrics?.recent_runs?.length || metrics?.openclaw_import?.cron_runs || 0,
    activeRuns: runs.filter((run) => ["running", "waiting_approval", "pending_approval"].includes(run.status)).length,
    pendingApprovals: metrics?.pending_approvals ?? pendingApprovals,
    failedQualityGates: metrics?.openclaw_import?.failed_quality_gates ?? failedRuns,
    memoryCandidates: metrics?.stale_or_due_memories ?? memoryCandidates,
    failedRuns: metrics?.openclaw_import?.failed_runs ?? failedRuns,
    blockedTasks: tasks.filter((task) => ["blocked", "failed"].includes(task.status)).length,
    auditEvents: audit.length || runs.length + approvals.length + memories.length,
    runtimeHealth: String(runtime?.status || runtime?.provider || (metrics?.runtime_health?.length ? "mixed" : "demo-safe")),
    externalSyncState: memoryCandidates > 0 ? "review queue" : "Notion dry-run ready",
    latestAudit,
  };
}

export function formatZoneMetric(zoneId: PixelZoneId, metrics: PixelMetrics, locale: PixelLocale = "en"): string {
  const zh = locale === "zh";
  switch (zoneId) {
    case "agent_lobby":
      return String(metrics.totalAgents);
    case "task_hall":
      return String(metrics.blockedTasks + metrics.activeRuns);
    case "runtime_lab":
      return runtimeHealthDisplay(metrics.runtimeHealth, locale);
    case "tool_workshop":
      return zh ? `${metrics.activeRuns} 个活跃` : `${metrics.activeRuns} active`;
    case "approval_gate":
      return zh ? `${metrics.pendingApprovals} 个待审` : `${metrics.pendingApprovals} pending`;
    case "evaluation_room":
      return zh ? `${metrics.failedQualityGates} 个失败` : `${metrics.failedQualityGates} failed`;
    case "memory_archive":
      return zh ? `${metrics.memoryCandidates} 条候选` : `${metrics.memoryCandidates} candidates`;
    case "audit_vault":
      return zh ? `${metrics.auditEvents} 条事件` : `${metrics.auditEvents} events`;
    case "external_base_dock":
      return externalSyncDisplay(metrics.externalSyncState, locale);
    case "run_stream":
      return zh ? `${metrics.totalRuns} 次运行` : `${metrics.totalRuns} runs`;
    case "incident_corner":
      return zh ? `${metrics.failedRuns + metrics.blockedTasks} 个未解` : `${metrics.failedRuns + metrics.blockedTasks} open`;
    case "template_market":
      return zh ? "模板包" : "packages";
    case "control_tower":
    default:
      return zh ? "实时 MIS" : "live MIS";
  }
}
