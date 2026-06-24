import { useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  ArrowRight,
  Bot,
  Brain,
  CheckCircle,
  ExternalLink,
  Map,
  Play,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
  Wifi,
} from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import {
  decideApproval,
  loadApprovals,
  loadDashboard,
  loadMemories,
  loadRuns,
  loadTasks,
  runLocalBrief,
  useLiveData,
  type LocalBriefResult,
} from "../../data/liveApi";

const STAR_OFFICE_URL = import.meta.env.VITE_STAR_OFFICE_URL as string | undefined;

function formatRuntime(value: unknown) {
  if (!value || typeof value !== "object") return "unknown";
  const row = value as Record<string, unknown>;
  return String(row.status || row.provider || "unknown");
}

export function WorkspaceHome() {
  const [briefResult, setBriefResult] = useState<LocalBriefResult | null>(null);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const { data, loading, error, refresh } = useLiveData(async () => {
    const [metrics, tasks, approvals, runs, memories] = await Promise.all([
      loadDashboard(),
      loadTasks(),
      loadApprovals(),
      loadRuns(),
      loadMemories(),
    ]);
    return { metrics, tasks, approvals, runs, memories };
  }, []);

  const tasks = data?.tasks || [];
  const approvals = data?.approvals || [];
  const runs = data?.runs || [];
  const memories = data?.memories || [];
  const metrics = data?.metrics;
  const activeTasks = tasks.filter(t => ["running", "waiting_approval", "planned", "blocked"].includes(t.status)).slice(0, 5);
  const pendingApprovals = approvals.filter(a => a.decision === "pending").slice(0, 4);
  const recentRuns = runs.slice(0, 5);
  const memoryCandidates = memories.filter(m => m.review_status === "candidate").slice(0, 3);
  const latestRun = briefResult?.run_id || recentRuns[0]?.run_id;
  const runtimeLabel = metrics?.runtime_health?.[0] ? formatRuntime(metrics.runtime_health[0]) : "demo-safe";
  const runCount = runs.length || metrics?.openclaw_import?.cron_runs || 0;

  const runBrief = async (confirmRun: boolean) => {
    setActionBusy(confirmRun ? "confirm-brief" : "dry-brief");
    try {
      const result = await runLocalBrief(confirmRun);
      setBriefResult(result);
      await refresh();
    } finally {
      setActionBusy(null);
    }
  };

  const handleApproval = async (id: string, decision: "approve" | "reject") => {
    setActionBusy(`${decision}:${id}`);
    try {
      await decideApproval(id, decision);
      await refresh();
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <div className="space-y-4 max-w-none">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>
              Workspace Home
            </h1>
            <span
              className="text-[10px] px-2 py-1 rounded uppercase tracking-wide"
              style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
            >
              MIS live cockpit
            </span>
            <span
              className="text-[10px] px-2 py-1 rounded uppercase tracking-wide"
              style={{ background: "rgba(168,85,247,0.12)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,0.24)" }}
            >
              Pixel map ready
            </span>
          </div>
          <p className="text-xs mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>
            Front desk for real local work: approvals, runs, memory review, local AI brief workflow, and the native Pixel Operating Map.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/workspace/pixel-office"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
            style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
          >
            <Map size={13} />
            Open Pixel Office
          </Link>
          <button
            onClick={refresh}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
          >
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />
            Refresh
          </button>
        </div>
      </div>

      {loading && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>Loading live MIS state...</p>}
      {error && <p className="text-xs" style={{ color: "#F87171" }}>Live backend unavailable: {error}</p>}

      <section className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {[
          {
            to: "/workspace/pixel-office",
            icon: <Play size={15} />,
            title: "Start a customer project",
            body: "Choose a template, assign AI workers, and generate a ledger-backed delivery.",
            color: "var(--mis-cyan)",
          },
          {
            to: "/workspace/agents",
            icon: <TerminalSquare size={15} />,
            title: "Check worker readiness",
            body: "See Hermes, OpenClaw, local daemon and remote agent enrollment state.",
            color: "var(--mis-purple)",
          },
          {
            to: "/workspace/reports",
            icon: <CheckCircle size={15} />,
            title: "Open delivery reports",
            body: "Return to customer project reports and confirm report artifact archive status.",
            color: "var(--mis-success)",
          },
        ].map((item) => (
          <Link
            key={item.to}
            to={item.to}
            className="rounded-lg p-3 hover:opacity-85"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
              <span style={{ color: item.color }}>{item.icon}</span>
              {item.title}
            </div>
            <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{item.body}</p>
          </Link>
        ))}
      </section>

      <div className="grid grid-cols-12 gap-4 items-start">
        <section
          className="col-span-12 xl:col-span-8 rounded-lg overflow-hidden"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="p-4 border-b" style={{ borderColor: "var(--mis-border)" }}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
                  <Sparkles size={15} style={{ color: "var(--mis-cyan)" }} />
                  Pixel Office Mode
                </div>
                <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--mis-dim)" }}>
                  Live visual navigator for AgentOps MIS. It shows where AI digital employees are working, then routes users into formal MIS pages for evidence and decisions.
                </p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Link
                  to="/workspace/pixel-office"
                  className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
                  style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
                >
                  Open Pixel Office
                  <ArrowRight size={13} />
                </Link>
                {STAR_OFFICE_URL && (
                  <a
                    href={STAR_OFFICE_URL}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
                    style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
                  >
                    <ExternalLink size={13} />
                    Legacy Star Office View
                  </a>
                )}
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4 p-4">
            <div className="lg:col-span-3 rounded-lg overflow-hidden relative min-h-[260px]" style={{ background: "linear-gradient(135deg, rgba(15,23,42,0.98), rgba(2,6,23,0.98))", border: "1px solid rgba(148,163,184,0.16)" }}>
              <div
                className="absolute inset-0 opacity-45"
                style={{
                  backgroundImage:
                    "linear-gradient(rgba(148,163,184,0.06) 1px, transparent 1px), linear-gradient(90deg, rgba(148,163,184,0.05) 1px, transparent 1px)",
                  backgroundSize: "18px 18px",
                }}
              />
              {[
                { label: "Control", x: 6, y: 8, w: 24, h: 22, color: "var(--mis-purple)" },
                { label: "Tasks", x: 36, y: 10, w: 30, h: 28, color: "var(--mis-cyan)" },
                { label: "Runs", x: 70, y: 9, w: 23, h: 22, color: "var(--mis-primary)" },
                { label: "Runtime", x: 8, y: 43, w: 28, h: 24, color: "var(--mis-purple)" },
                { label: "Approvals", x: 43, y: 47, w: 22, h: 23, color: "#FBBF24" },
                { label: "Audit", x: 70, y: 48, w: 22, h: 24, color: "#94A3B8" },
              ].map((zone) => (
                <div
                  key={zone.label}
                  className="absolute rounded-sm p-2 text-[10px] font-mono"
                  style={{
                    left: `${zone.x}%`,
                    top: `${zone.y}%`,
                    width: `${zone.w}%`,
                    height: `${zone.h}%`,
                    color: zone.color,
                    border: `1px solid ${zone.color}`,
                    background: "rgba(2,6,23,0.58)",
                    boxShadow: `0 0 18px rgba(34,211,238,0.08)`,
                    clipPath: "polygon(0 0, calc(100% - 6px) 0, 100% 6px, 100% 100%, 6px 100%, 0 calc(100% - 6px))",
                  }}
                >
                  {zone.label}
                </div>
              ))}
              {[0, 1, 2, 3, 4].map((agent) => (
                <div
                  key={agent}
                  className="absolute h-7 w-5 rounded-sm"
                  style={{
                    left: `${18 + agent * 13}%`,
                    top: `${30 + (agent % 3) * 15}%`,
                    background: agent === 2 ? "#FBBF24" : "var(--mis-cyan)",
                    border: "2px solid #0B1020",
                    boxShadow: "0 0 12px rgba(34,211,238,0.32)",
                  }}
                />
              ))}
              <div className="absolute left-4 bottom-4 right-4 rounded px-3 py-2 text-[10px]" style={{ background: "rgba(2,6,23,0.72)", color: "var(--mis-muted)", border: "1px solid rgba(148,163,184,0.18)" }}>
                Original CSS preview only · no Star-Office assets copied
              </div>
            </div>

            <div className="lg:col-span-2 space-y-3">
              <div className="grid grid-cols-2 gap-2">
                {[
                  { icon: <Bot size={14} />, label: "Agents", value: metrics?.agents_total ?? "—", color: "var(--mis-cyan)" },
                  { icon: <Activity size={14} />, label: "Runs", value: runCount || "—", color: "var(--mis-success)" },
                  { icon: <ShieldAlert size={14} />, label: "Approvals", value: metrics?.pending_approvals ?? pendingApprovals.length, color: "#FBBF24" },
                  { icon: <Wifi size={14} />, label: "Runtime", value: runtimeLabel, color: "var(--mis-purple)" },
                ].map(item => (
                  <div key={item.label} className="rounded p-2" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,0.12)" }}>
                    <div className="flex items-center gap-1.5 text-[10px]" style={{ color: item.color }}>
                      {item.icon}
                      <span style={{ color: "var(--mis-muted)" }}>{item.label}</span>
                    </div>
                    <div className="text-lg font-semibold mt-1 truncate" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                  </div>
                ))}
              </div>
              <div className="rounded p-3" style={{ background: "rgba(34,211,238,0.08)", border: "1px solid rgba(34,211,238,0.18)" }}>
                <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-cyan)" }}>Map contract</div>
                <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
                  The map is a navigation and operations layer. It does not replace Run Ledger, Audit, Approvals, Tool Calls or Memory.
                </p>
              </div>
              {!STAR_OFFICE_URL && (
                <div className="rounded p-3 text-[11px]" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)", border: "1px solid rgba(148,163,184,0.12)" }}>
                  Legacy Star Office link is hidden because VITE_STAR_OFFICE_URL is not configured.
                </div>
              )}
            </div>
          </div>
        </section>

        <aside className="col-span-12 xl:col-span-4 space-y-3">
          <section className="rounded-lg p-3" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="grid grid-cols-2 gap-2">
              {[
                { icon: <Bot size={14} />, label: "Agents", value: metrics?.agents_total ?? "—", color: "var(--mis-cyan)" },
                { icon: <Activity size={14} />, label: "Runs", value: runCount || "—", color: "var(--mis-success)" },
                { icon: <ShieldAlert size={14} />, label: "Approvals", value: metrics?.pending_approvals ?? pendingApprovals.length, color: "#FBBF24" },
                { icon: <Brain size={14} />, label: "Memory", value: metrics?.stale_or_due_memories ?? memoryCandidates.length, color: "var(--mis-purple)" },
              ].map(item => (
                <div key={item.label} className="rounded p-2" style={{ background: "var(--mis-surface2)" }}>
                  <div className="flex items-center gap-1.5 text-[10px]" style={{ color: item.color }}>
                    {item.icon}
                    <span style={{ color: "var(--mis-muted)" }}>{item.label}</span>
                  </div>
                  <div className="text-lg font-semibold mt-1" style={{ color: "var(--mis-text)" }}>{item.value}</div>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-lg p-3" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold flex items-center gap-2" style={{ color: "var(--mis-text)" }}>
                <TerminalSquare size={14} style={{ color: "var(--mis-cyan)" }} />
                Local AI Work Brief
              </h2>
              <StatusBadge status={briefResult?.dry_run === false ? "completed" : "planned"} />
            </div>
            <p className="text-[11px] leading-relaxed mb-3" style={{ color: "var(--mis-dim)" }}>
              Uses safe structured MIS metrics. Dry-run is default; confirmed run records into Run Ledger, Evaluations and Audit.
            </p>
            <div className="flex gap-2">
              <button
                onClick={() => runBrief(false)}
                disabled={!!actionBusy}
                className="flex-1 flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded disabled:opacity-50"
                style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
              >
                <Play size={13} />
                Dry-run
              </button>
              <button
                onClick={() => runBrief(true)}
                disabled={!!actionBusy}
                className="flex-1 flex items-center justify-center gap-1.5 text-xs px-3 py-2 rounded disabled:opacity-50"
                style={{ background: "rgba(42,157,143,0.18)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.3)" }}
              >
                <CheckCircle size={13} />
                Confirm
              </button>
            </div>
            {briefResult && (
              <div className="mt-3 rounded p-2 text-[11px] leading-relaxed" style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)" }}>
                <div style={{ color: "var(--mis-text)" }}>
                  {briefResult.dry_run ? "Dry-run planned" : briefResult.ok ? "Real run completed" : "Run failed"}
                </div>
                {briefResult.run_id && (
                  <Link to={`/workspace/runs/${briefResult.run_id}`} style={{ color: "var(--mis-cyan)" }}>
                    Open run {briefResult.run_id}
                  </Link>
                )}
                <div className="mt-1 line-clamp-4">
                  {briefResult.output_summary || briefResult.note || briefResult.error || JSON.stringify(briefResult.state_preview || {})}
                </div>
              </div>
            )}
          </section>

          <section className="rounded-lg p-3" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>Pending Approvals</h2>
              <Link to="/workspace/approvals" className="text-[11px]" style={{ color: "var(--mis-cyan)" }}>Review all</Link>
            </div>
            <div className="space-y-2">
              {pendingApprovals.length === 0 && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>No pending approvals.</p>}
              {pendingApprovals.map(ap => (
                <div key={ap.approval_id} className="rounded p-2" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(251,191,36,0.16)" }}>
                  <div className="text-xs leading-snug" style={{ color: "var(--mis-text)" }}>{ap.reason}</div>
                  <div className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>{ap.requested_by_agent_id} · {ap.run_id}</div>
                  <div className="flex gap-2 mt-2">
                    <button
                      onClick={() => handleApproval(ap.approval_id, "approve")}
                      disabled={!!actionBusy}
                      className="text-[11px] px-2 py-1 rounded disabled:opacity-50"
                      style={{ background: "rgba(42,157,143,0.2)", color: "var(--mis-success)" }}
                    >
                      Approve
                    </button>
                    <button
                      onClick={() => handleApproval(ap.approval_id, "reject")}
                      disabled={!!actionBusy}
                      className="text-[11px] px-2 py-1 rounded disabled:opacity-50"
                      style={{ background: "rgba(248,113,113,0.15)", color: "#F87171" }}
                    >
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </aside>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>Work Queue</h2>
            <Link to="/workspace/tasks" className="text-[11px]" style={{ color: "var(--mis-cyan)" }}>Tasks</Link>
          </div>
          <div className="space-y-2">
            {activeTasks.length === 0 && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>No active tasks.</p>}
            {activeTasks.map(task => (
              <Link key={task.task_id} to={`/workspace/tasks/${task.task_id}`} className="block rounded p-2.5 hover:opacity-80" style={{ background: "var(--mis-surface2)" }}>
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-xs font-medium truncate" style={{ color: "var(--mis-text)" }}>{task.title}</div>
                    <div className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>{task.owner_agent_id}</div>
                  </div>
                  <RiskBadge risk={task.risk_level} />
                </div>
              </Link>
            ))}
          </div>
        </section>

        <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>Run Ledger</h2>
            <Link to="/workspace/runs" className="text-[11px]" style={{ color: "var(--mis-cyan)" }}>Runs</Link>
          </div>
          <div className="space-y-2">
            {recentRuns.length === 0 && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>No recent runs.</p>}
            {recentRuns.map(run => (
              <Link key={run.run_id} to={`/workspace/runs/${run.run_id}`} className="flex items-center justify-between gap-3 rounded p-2.5 hover:opacity-80" style={{ background: "var(--mis-surface2)" }}>
                <div className="min-w-0">
                  <div className="text-xs font-mono truncate" style={{ color: "var(--mis-text)" }}>{run.run_id}</div>
                  <div className="text-[10px] mt-1" style={{ color: "var(--mis-muted)" }}>{run.runtime_type} · {run.agent_id}</div>
                </div>
                <StatusBadge status={run.status} />
              </Link>
            ))}
          </div>
        </section>

        <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>Memory & Runtime</h2>
            <Link to="/workspace/memory" className="text-[11px]" style={{ color: "var(--mis-cyan)" }}>Memory</Link>
          </div>
          <div className="space-y-2">
            {(metrics?.runtime_health || []).slice(0, 3).map((runtime, idx) => (
              <div key={idx} className="flex items-center justify-between rounded p-2.5" style={{ background: "var(--mis-surface2)" }}>
                <span className="text-xs" style={{ color: "var(--mis-text)" }}>{String((runtime as Record<string, unknown>).provider || "runtime")}</span>
                <StatusBadge status={formatRuntime(runtime)} />
              </div>
            ))}
            {memoryCandidates.map(m => (
              <div key={m.memory_id} className="rounded p-2.5" style={{ background: "var(--mis-surface2)" }}>
                <div className="text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{m.canonical_text.slice(0, 96)}...</div>
              </div>
            ))}
            {latestRun && (
              <Link to={`/workspace/runs/${latestRun}`} className="block text-[11px] pt-1" style={{ color: "var(--mis-cyan)" }}>
                Latest ledger entry: {latestRun}
              </Link>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
