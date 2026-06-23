import Link from "next/link";
import { Activity, Bot, ClipboardList, Database, FileText, KeyRound, Map, Plug, ShieldCheck, Workflow } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { AgentSummary, ApprovalSummary, AuditSummary, DashboardMetrics, MemorySummary, RunSummary, TaskSummary } from "@/lib/mis";

type ZoneTone = "cyan" | "green" | "amber" | "red" | "purple" | "slate";

type PixelZone = {
  id: string;
  label: string;
  route: string;
  description: string;
  metric: string;
  x: number;
  y: number;
  w: number;
  h: number;
  tone: ZoneTone;
};

type PixelAgent = {
  id: string;
  name: string;
  runtime: string;
  status: string;
  route: string;
  zoneId: string;
};

type PixelOfficeFeedback = {
  localBriefStatus?: string;
  localBriefError?: string;
  localBriefPromptHash?: string;
  localBriefStateHash?: string;
  localBriefAgentsTotal?: string;
  localBriefPendingApprovals?: string;
  localBriefRecentRealRuns?: string;
  localBriefPreparedActionId?: string;
  localBriefApprovalId?: string;
  localBriefPreparedStatus?: string;
  localBriefRunId?: string;
  localBriefArtifactId?: string;
};

function countWhere<T>(rows: T[], predicate: (row: T) => boolean) {
  return rows.filter(predicate).length;
}

function statusIs(row: { status?: string }, values: string[]) {
  return values.includes(String(row.status || "").toLowerCase());
}

function riskIs(row: { risk_level?: string }, values: string[]) {
  return values.includes(String(row.risk_level || "").toLowerCase());
}

function firstText(value: unknown, fallback: string) {
  const text = String(value || "").trim();
  return text || fallback;
}

function zoneForAgent(agent: AgentSummary, tasks: TaskSummary[], runs: RunSummary[], approvals: ApprovalSummary[], memories: MemorySummary[]) {
  const pendingApproval = approvals.some((approval) => approval.decision === "pending" && approval.requested_by_agent_id === agent.agent_id);
  const activeRun = runs.some((run) => run.agent_id === agent.agent_id && statusIs(run, ["running", "waiting_approval", "pending_approval"]));
  const failedRun = runs.some((run) => run.agent_id === agent.agent_id && statusIs(run, ["failed", "error", "blocked", "timeout"]));
  const activeTask = tasks.find((task) => task.owner_agent_id === agent.agent_id && statusIs(task, ["planned", "running", "waiting_approval", "blocked", "failed"]));
  const memoryCandidate = memories.some((memory) => memory.agent_id === agent.agent_id && memory.review_status === "candidate");
  if (pendingApproval) return "approval_gate";
  if (failedRun || activeTask?.status === "failed" || activeTask?.status === "blocked") return "incident_corner";
  if (activeRun) return "runtime_lab";
  if (activeTask?.status === "planned") return "dispatch_hall";
  if (activeTask) return "task_hall";
  if (memoryCandidate) return "memory_archive";
  if (["openclaw", "hermes"].includes(String(agent.runtime_type || "").toLowerCase())) return "runtime_lab";
  return "agent_lobby";
}

function buildZones(input: {
  metrics: DashboardMetrics;
  agents: AgentSummary[];
  tasks: TaskSummary[];
  runs: RunSummary[];
  approvals: ApprovalSummary[];
  memories: MemorySummary[];
  audit: AuditSummary[];
}): PixelZone[] {
  const { metrics, agents, tasks, runs, approvals, memories, audit } = input;
  const runningRuns = countWhere(runs, (run) => statusIs(run, ["running", "waiting_approval", "pending_approval"]));
  const failedRuns = countWhere(runs, (run) => statusIs(run, ["failed", "error", "blocked", "timeout"]));
  const blockedTasks = countWhere(tasks, (task) => statusIs(task, ["blocked", "failed"]));
  const pendingApprovals = metrics.pending_approvals ?? countWhere(approvals, (approval) => approval.decision === "pending");
  const memoryCandidates = metrics.stale_or_due_memories ?? countWhere(memories, (memory) => memory.review_status === "candidate");

  return [
    { id: "control_tower", label: "Control Tower", route: "/workspace", description: "Commercial command center, readiness, risk and account state.", metric: "live MIS", x: 3, y: 5, w: 18, h: 14, tone: "purple" },
    { id: "agent_lobby", label: "Agent Lobby", route: "/workspace/agents", description: "Agent identities, runtime type, safety status and worker controls.", metric: `${metrics.agents_total ?? agents.length} agents`, x: 25, y: 6, w: 17, h: 14, tone: "cyan" },
    { id: "dispatch_hall", label: "Dispatch Hall", route: "/workspace/dispatch", description: "Customer template, worker dispatch and async job entry points.", metric: `${countWhere(tasks, (task) => statusIs(task, ["planned", "backlog"]))} queued`, x: 46, y: 5, w: 23, h: 19, tone: "green" },
    { id: "run_stream", label: "Run Stream", route: "/workspace/runs", description: "Run ledger, delegation chain, runtime history and replay evidence.", metric: `${runs.length || metrics.recent_runs?.length || 0} runs`, x: 73, y: 6, w: 22, h: 14, tone: "cyan" },
    { id: "runtime_lab", label: "Runtime Lab", route: "/workspace/connectors", description: "Connector trust, allow-real-run, require-confirm and live adapter gates.", metric: `${runningRuns} active`, x: 6, y: 28, w: 22, h: 17, tone: "purple" },
    { id: "task_hall", label: "Task Hall", route: "/workspace/tasks", description: "Task ownership, priority, risk and acceptance criteria.", metric: `${tasks.length} tasks`, x: 32, y: 30, w: 22, h: 16, tone: "green" },
    { id: "approval_gate", label: "Approval Gate", route: "/workspace/approvals", description: "High-risk action approval, rejection and evidence capture.", metric: `${pendingApprovals} pending`, x: 59, y: 32, w: 17, h: 16, tone: "amber" },
    { id: "evaluation_room", label: "Evaluation Room", route: "/workspace/evaluations", description: "Quality gates, evaluator scores and failed-run diagnostics.", metric: `${failedRuns} failed`, x: 80, y: 29, w: 16, h: 17, tone: failedRuns ? "red" : "green" },
    { id: "memory_archive", label: "Memory Archive", route: "/workspace/memory", description: "SOPs, candidate memories, provenance and review workflow.", metric: `${memoryCandidates} review`, x: 6, y: 54, w: 22, h: 18, tone: "slate" },
    { id: "tool_workshop", label: "Tool Workshop", route: "/workspace/tool-calls", description: "Tool-call risk, execution evidence and run links.", metric: `${countWhere(tasks, (task) => riskIs(task, ["high", "critical"]))} high risk`, x: 33, y: 56, w: 20, h: 17, tone: "cyan" },
    { id: "audit_vault", label: "Audit Vault", route: "/workspace/audit", description: "Append-only audit trail, actor/action/entity evidence and hash-chain proof.", metric: `${audit.length} events`, x: 59, y: 56, w: 18, h: 17, tone: "slate" },
    { id: "incident_corner", label: "Incident Corner", route: "/workspace/runs", description: "Failed runs, blocked tasks, runtime errors and recovery pointers.", metric: `${failedRuns + blockedTasks} open`, x: 81, y: 55, w: 16, h: 18, tone: failedRuns + blockedTasks ? "red" : "green" },
    { id: "external_base_dock", label: "External Base Dock", route: "/workspace/external-bases/notion", description: "Notion dry-run, writeback blocking and external-base evidence.", metric: "dry-run", x: 9, y: 80, w: 22, h: 12, tone: "slate" },
    { id: "template_market", label: "Template Market", route: "/workspace/dispatch", description: "Template packages, entitlement gates and safe customer workflow entry.", metric: "templates", x: 38, y: 80, w: 25, h: 12, tone: "green" },
    { id: "report_desk", label: "Report Desk", route: "/workspace/reports", description: "Customer delivery board, report artifacts and archive evidence.", metric: "reports", x: 70, y: 80, w: 23, h: 12, tone: "amber" },
  ];
}

function toneClass(tone: ZoneTone) {
  return `pixelZone ${tone}`;
}

function buildAgents(agents: AgentSummary[], tasks: TaskSummary[], runs: RunSummary[], approvals: ApprovalSummary[], memories: MemorySummary[]): PixelAgent[] {
  return agents.slice(0, 10).map((agent) => ({
    id: agent.agent_id,
    name: firstText(agent.name, agent.agent_id),
    runtime: firstText(agent.runtime_type, "mock"),
    status: firstText(agent.status, "unknown"),
    route: `/workspace/agents/${encodeURIComponent(agent.agent_id)}`,
    zoneId: zoneForAgent(agent, tasks, runs, approvals, memories),
  }));
}

export function PixelOfficeParityPage({
  metrics,
  agents,
  tasks,
  runs,
  approvals,
  memories,
  audit,
  errors,
  feedback,
}: Readonly<{
  metrics: DashboardMetrics;
  agents: AgentSummary[];
  tasks: TaskSummary[];
  runs: RunSummary[];
  approvals: ApprovalSummary[];
  memories: MemorySummary[];
  audit: AuditSummary[];
  errors: Record<string, string | null>;
  feedback?: PixelOfficeFeedback;
}>) {
  const zones = buildZones({ metrics, agents, tasks, runs, approvals, memories, audit });
  const pixelAgents = buildAgents(agents, tasks, runs, approvals, memories);
  const activeErrors = Object.entries(errors).filter(([, value]) => value);
  const recentTasks = tasks.slice(0, 6);
  const recentRuns = runs.slice(0, 6);

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Pixel Office parity route</p>
          <h1>Pixel Office</h1>
          <p className="subtle">Read-only commercial-safe Pixel Operating Map backed by live MIS ledgers</p>
        </div>
        <Link className="miniButton" href="/workspace/dispatch"><Workflow size={13} /> Dispatch</Link>
      </header>

      {activeErrors.length ? (
        <div className="banner warn">
          Partial Pixel Office readback: {activeErrors.map(([key, value]) => `${key}: ${value}`).join(" | ")}
        </div>
      ) : null}
      {feedback?.localBriefStatus === "dry_run" ? (
        <div className="banner success">
          Local brief dry-run recorded: prompt {feedback.localBriefPromptHash?.slice(0, 16) || "hash omitted"} · state {feedback.localBriefStateHash?.slice(0, 16) || "hash omitted"}
        </div>
      ) : null}
      {feedback?.localBriefStatus === "waiting_approval" ? (
        <div className="banner warn">
          <strong>Local brief prepared action waiting approval:</strong> {feedback.localBriefApprovalId || "approval id omitted"}
        </div>
      ) : null}
      {feedback?.localBriefStatus === "live_run" ? (
        <div className="banner success">
          Local brief live run recorded: run {feedback.localBriefRunId || "run id omitted"} · prepared action {feedback.localBriefPreparedStatus || "consumed"}
        </div>
      ) : null}
      {feedback?.localBriefStatus === "failed" ? <div className="banner error">Local brief action failed: {feedback.localBriefError || "unknown"}</div> : null}

      <section className="metrics">
        <div className="metric compactMetric"><Map className="metricIcon" size={18} /><span>mapped rooms</span><strong>{zones.length}</strong></div>
        <div className="metric compactMetric"><Bot className="metricIcon" size={18} /><span>agents placed</span><strong>{pixelAgents.length}</strong></div>
        <div className="metric compactMetric"><ClipboardList className="metricIcon" size={18} /><span>task cards</span><strong>{tasks.length}</strong></div>
        <div className="metric compactMetric"><ShieldCheck className="metricIcon" size={18} /><span>pending approvals</span><strong>{metrics.pending_approvals ?? countWhere(approvals, (approval) => approval.decision === "pending")}</strong></div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Map size={14} /> Pixel Operating Map</h2>
          <span>read-only route contract</span>
        </div>
        <div className="proofStrip">
          <span>commercial-safe geometry</span>
          <span>no Star Office assets</span>
          <span>server shell false</span>
          <span>live runtime disabled</span>
          <span>token omitted true</span>
        </div>
        <div className="pixelMapShell">
          <div className="pixelGrid" />
          {zones.map((zone) => (
            <Link
              className={toneClass(zone.tone)}
              href={zone.route}
              key={zone.id}
              style={{ left: `${zone.x}%`, top: `${zone.y}%`, width: `${zone.w}%`, height: `${zone.h}%` }}
            >
              <strong>{zone.label}</strong>
              <span>{zone.metric}</span>
            </Link>
          ))}
          {pixelAgents.map((agent, index) => {
            const zone = zones.find((item) => item.id === agent.zoneId) || zones[0];
            return (
              <Link
                className="pixelAgentDot"
                href={agent.route}
                key={agent.id}
                style={{
                  left: `${zone.x + 2 + ((index % 4) * 3)}%`,
                  top: `${zone.y + zone.h - 4 - (Math.floor(index / 4) * 3)}%`,
                }}
                title={`${agent.name} · ${agent.runtime} · ${agent.status}`}
              >
                {agent.name.slice(0, 1).toUpperCase()}
              </Link>
            );
          })}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><FileText size={14} /> Local brief controls</h2>
          <span>prepared-action gated</span>
        </div>
        <div className="proofStrip">
          <span>workflow local_ai_brief</span>
          <span>dry-run allowed</span>
          <span>live brief approval-gated</span>
          <span>prompt body omitted</span>
          <span>token omitted true</span>
        </div>
        <div className="grid tightGrid">
          <div>
            <p className="subtle">
              Dry-run local brief records structured MIS state hashes and an audit/runtime event without sending a prompt to Agnesfallback.
            </p>
            <form className="buttonRow" method="post" action="/workspace/pixel-office/local-brief">
              <button className="miniButton good" type="submit"><FileText size={13} /> Run dry-run brief</button>
            </form>
          </div>
          <div>
            <p className="subtle">
              Confirmed local brief execution prepares an approval-bound action first; Agnesfallback is not called until an approved exact resume.
            </p>
            <form className="buttonRow" method="post" action="/workspace/pixel-office/local-brief">
              <input type="hidden" name="confirm_run" value="true" />
              <button className="miniButton bad" type="submit"><ShieldCheck size={13} /> Prepare live brief</button>
            </form>
            {feedback?.localBriefPreparedActionId ? (
              <form className="buttonRow" method="post" action="/workspace/pixel-office/local-brief">
                <input type="hidden" name="confirm_run" value="true" />
                <input type="hidden" name="prepared_action_id" value={feedback.localBriefPreparedActionId} />
                <input type="hidden" name="prompt_hash" value={feedback.localBriefPromptHash || ""} />
                <input type="hidden" name="state_hash" value={feedback.localBriefStateHash || ""} />
                <button className="miniButton good" type="submit"><Activity size={13} /> Resume approved brief</button>
              </form>
            ) : null}
          </div>
        </div>
        <div className="proofStrip">
          <span>prompt {feedback?.localBriefPromptHash?.slice(0, 16) || "none"}</span>
          <span>state {feedback?.localBriefStateHash?.slice(0, 16) || "none"}</span>
          <span>prepared {feedback?.localBriefPreparedActionId?.slice(0, 18) || "none"}</span>
          <span>approval {feedback?.localBriefApprovalId?.slice(0, 18) || "none"}</span>
          <span>agents {feedback?.localBriefAgentsTotal || metrics.agents_total || agents.length}</span>
          <span>pending approvals {feedback?.localBriefPendingApprovals || metrics.pending_approvals || 0}</span>
          <span>run {feedback?.localBriefRunId?.slice(0, 18) || "none"}</span>
          <span>artifact {feedback?.localBriefArtifactId?.slice(0, 18) || "none"}</span>
        </div>
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><Activity size={14} /> Zone routing contract</h2>
            <span>{zones.length} routes</span>
          </div>
          <div className="list compact">
            {zones.slice(0, 8).map((zone) => (
              <Link className="row linkRow" href={zone.route} key={zone.id}>
                <div>
                  <strong>{zone.label}</strong>
                  <span>{zone.description}</span>
                </div>
                <span className="status">{zone.metric}</span>
              </Link>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><Database size={14} /> State source</h2>
            <span>live MIS ledgers</span>
          </div>
          <div className="proofStrip">
            <span>dashboard {metrics.agents_total ?? "loaded"}</span>
            <span>agents {agents.length}</span>
            <span>tasks {tasks.length}</span>
            <span>runs {runs.length}</span>
            <span>audit {audit.length}</span>
          </div>
          <div className="list compact">
            {pixelAgents.slice(0, 6).map((agent) => (
              <Link className="row linkRow" href={agent.route} key={agent.id}>
                <div>
                  <strong>{agent.name}</strong>
                  <span>{agent.id} · {agent.runtime} · {agent.status}</span>
                </div>
                <span className="status">{zones.find((zone) => zone.id === agent.zoneId)?.label || "Agent Lobby"}</span>
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ClipboardList size={14} /> Task cards</h2>
            <span>{recentTasks.length} recent</span>
          </div>
          <div className="list compact">
            {recentTasks.map((task) => (
              <Link className="row linkRow" href={`/workspace/tasks/${encodeURIComponent(task.task_id)}`} key={task.task_id}>
                <div>
                  <strong>{task.title || task.task_id}</strong>
                  <span>{task.status} · {task.owner_agent_id || "unassigned"} · risk {task.risk_level || "medium"}</span>
                </div>
                <span className="status">{task.priority || "normal"}</span>
              </Link>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><KeyRound size={14} /> Run and audit proof</h2>
            <span>{recentRuns.length} runs</span>
          </div>
          <div className="list compact">
            {recentRuns.map((run) => (
              <Link className="row linkRow" href={`/workspace/runs/${encodeURIComponent(run.run_id)}`} key={run.run_id}>
                <div>
                  <strong>{run.run_id}</strong>
                  <span>{run.status} · {run.agent_id || "agent unknown"} · {run.task_id || "task unknown"}</span>
                </div>
                <span className="status">{run.runtime_type || "runtime"}</span>
              </Link>
            ))}
            {recentRuns.length ? null : <p className="empty">No recent runs loaded.</p>}
          </div>
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Plug size={14} /> Authority boundary</h2>
          <span>orientation layer only</span>
        </div>
        <p className="subtle">
          This Next.js Pixel Office route is a commercial-safe read-only map. It links back to formal ledgers for mutation, approval, runtime trust, delivery, memory and audit evidence.
        </p>
      </section>
    </AppFrame>
  );
}
