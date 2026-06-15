import type { Approval, Memory, Run, Task } from "../../data/mockData";
import type { DashboardMetrics } from "../../data/liveApi";

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

export function derivePixelMetrics(input: {
  metrics?: DashboardMetrics | null;
  tasks?: Task[];
  approvals?: Approval[];
  runs?: Run[];
  memories?: Memory[];
}): PixelMetrics {
  const tasks = input.tasks || [];
  const approvals = input.approvals || [];
  const runs = input.runs || [];
  const memories = input.memories || [];
  const metrics = input.metrics || null;
  const runtime = metrics?.runtime_health?.[0] as Record<string, unknown> | undefined;
  const failedRuns = runs.filter((run) => ["failed", "error", "blocked", "timeout"].includes(run.status)).length;
  const pendingApprovals = approvals.filter((approval) => approval.decision === "pending").length;
  const memoryCandidates = memories.filter((memory) => memory.review_status === "candidate").length;
  return {
    totalAgents: metrics?.agents_total ?? Math.max(DEMO_AGENTS.length, metrics?.agent_performance_summary?.length || 0),
    totalRuns: runs.length || metrics?.recent_runs?.length || metrics?.openclaw_import?.cron_runs || 0,
    activeRuns: runs.filter((run) => ["running", "waiting_approval", "pending_approval"].includes(run.status)).length,
    pendingApprovals: metrics?.pending_approvals ?? pendingApprovals,
    failedQualityGates: metrics?.openclaw_import?.failed_quality_gates ?? failedRuns,
    memoryCandidates: metrics?.stale_or_due_memories ?? memoryCandidates,
    failedRuns: metrics?.openclaw_import?.failed_runs ?? failedRuns,
    blockedTasks: tasks.filter((task) => ["blocked", "failed"].includes(task.status)).length,
    auditEvents: runs.length + approvals.length + memories.length,
    runtimeHealth: String(runtime?.status || runtime?.provider || (metrics?.runtime_health?.length ? "mixed" : "demo-safe")),
    externalSyncState: memoryCandidates > 0 ? "review queue" : "Notion dry-run ready",
    latestAudit: runs[0]?.run_id || approvals[0]?.approval_id || "demo_audit_event",
  };
}

export function formatZoneMetric(zoneId: PixelZoneId, metrics: PixelMetrics): string {
  switch (zoneId) {
    case "agent_lobby":
      return String(metrics.totalAgents);
    case "task_hall":
      return String(metrics.blockedTasks + metrics.activeRuns);
    case "runtime_lab":
      return metrics.runtimeHealth;
    case "tool_workshop":
      return `${metrics.activeRuns} active`;
    case "approval_gate":
      return `${metrics.pendingApprovals} pending`;
    case "evaluation_room":
      return `${metrics.failedQualityGates} failed`;
    case "memory_archive":
      return `${metrics.memoryCandidates} candidates`;
    case "audit_vault":
      return `${metrics.auditEvents} events`;
    case "external_base_dock":
      return metrics.externalSyncState;
    case "run_stream":
      return `${metrics.totalRuns} runs`;
    case "incident_corner":
      return `${metrics.failedRuns + metrics.blockedTasks} open`;
    case "template_market":
      return "packages";
    case "control_tower":
    default:
      return "live MIS";
  }
}

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
