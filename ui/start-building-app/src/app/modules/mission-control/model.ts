import type { LocaleMode } from "../../context/PreferencesContext";
import type { ActivityView, AttentionView, WorkforceView, WorkPackageView } from "./types";
import type { useMissionControlData } from "./useMissionControlData";

type Snapshot = NonNullable<ReturnType<typeof useMissionControlData>["data"]>;

const INCIDENT_STATUSES = new Set(["failed", "blocked", "error", "timeout"]);
const ACTIVE_PACKAGE_STATUSES = new Set(["planned", "running", "still_running", "waiting_approval", "in_progress", "ready_for_review"]);

function reviewRoute(item: { item_type?: string; task_id?: string | null; run_id?: string | null; artifact_id?: string | null }) {
  if (item.run_id) return "/admin/runs/" + item.run_id;
  if (item.task_id) return "/admin/tasks/" + item.task_id;
  if (item.item_type === "approval") return "/govern/approvals";
  if (item.item_type === "memory_candidate") return "/govern/knowledge";
  if (item.artifact_id) return "/deliveries";
  return "/human-review";
}

function sumEvidence(values: Record<string, number> | undefined) {
  return Object.values(values || {}).reduce((sum, value) => sum + Number(value || 0), 0);
}

export function attentionViews(data: Snapshot): AttentionView[] {
  const actions = data.operatorPlan?.actions || [];
  if (actions.length) {
    return actions.slice(0, 6).map((item) => ({
      id: item.action_id,
      title: item.title,
      summary: item.summary || item.command,
      severity: item.severity,
      route: item.ui_route || "/workspace/agents",
      source: item.source,
    }));
  }
  return (data.reviewQueue?.review_items || []).slice(0, 6).map((item) => ({
    id: item.item_id,
    title: item.title,
    summary: item.summary || item.next_action || "",
    severity: item.status,
    route: reviewRoute(item),
    source: item.item_type,
  }));
}

export function packageViews(data: Snapshot, locale: LocaleMode): { available: boolean; visible: number; items: WorkPackageView[] } {
  const payload = data.workPackages;
  const available = Boolean(payload && payload.status !== "unavailable");
  const packages = payload?.work_packages || [];
  const items = available ? packages.filter((item) => ACTIVE_PACKAGE_STATUSES.has((item.package_status || item.status).toLowerCase())).map((item) => ({
    id: item.work_package_id || item.task_id,
    taskId: item.task_id,
    title: item.title,
    owner: item.owner_agent_id || (locale === "zh" ? "未分配" : "Unassigned"),
    project: item.project_id || item.plan_id || "—",
    status: item.package_status || item.status,
    risk: item.risk_level,
    evidence: sumEvidence(item.evidence_counts),
  })) : [];
  return { available, visible: packages.length, items };
}

export function workforceView(data: Snapshot): WorkforceView {
  const fleet = data.workerFleet;
  if (!fleet) {
    return { available: false, status: "unavailable", laneCount: 0, localDaemons: 0, runningDaemons: 0, stuckWork: 0, lanes: [] };
  }
  return {
    available: fleet.status !== "unavailable",
    status: fleet.status,
    laneCount: fleet.summary.lane_count,
    localDaemons: fleet.summary.local_daemon_count,
    runningDaemons: fleet.summary.running_local_daemons,
    stuckWork: fleet.summary.stuck_worker_tasks + fleet.summary.stuck_workflow_jobs,
    lanes: fleet.lanes.slice(0, 4).map((lane) => ({
      id: lane.lane_id,
      name: lane.agent_name || lane.adapter || lane.lane_type,
      status: lane.health || lane.status,
    })),
  };
}

export function incidentSummary(data: Snapshot) {
  const cutoff = Date.now() - 24 * 60 * 60 * 1000;
  const runs = data.runs.filter((run) => INCIDENT_STATUSES.has(run.status.toLowerCase()) && (!run.created_at || Number.isNaN(Date.parse(run.created_at)) || Date.parse(run.created_at) >= cutoff));
  const tasks = data.tasks.filter((task) => INCIDENT_STATUSES.has(task.status.toLowerCase()));
  return { runs, tasks };
}

export function activityViews(data: Snapshot): ActivityView[] {
  const incidents = incidentSummary(data);
  const rows: ActivityView[] = [
    ...incidents.runs.map((run) => ({ id: run.run_id, title: run.error_type || run.output_summary || run.run_id, status: run.status, route: "/admin/runs/" + run.run_id, meta: run.agent_id })),
    ...incidents.tasks.map((task) => ({ id: task.task_id, title: task.title, status: task.status, route: "/admin/tasks/" + task.task_id, meta: task.owner_agent_id })),
    ...data.runs.slice(0, 5).map((run) => ({ id: "recent-" + run.run_id, title: run.output_summary || run.run_id, status: run.status, route: "/admin/runs/" + run.run_id, meta: run.agent_id })),
  ];
  return rows.slice(0, 8);
}
