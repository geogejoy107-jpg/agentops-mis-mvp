import { useState } from "react";
import { Link } from "react-router";
import {
  Activity,
  Bot,
  Brain,
  CheckCircle,
  ExternalLink,
  Play,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TerminalSquare,
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

const STAR_OFFICE_URL =
  import.meta.env.VITE_STAR_OFFICE_URL || "http://127.0.0.1:19000/workspace";

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
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>
              Pixel Office Workbench
            </h1>
            <span
              className="text-[10px] px-2 py-1 rounded"
              style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
            >
              Star-Office base + live MIS ledger
            </span>
          </div>
          <p className="text-xs mt-1" style={{ color: "var(--mis-dim)" }}>
            Front desk for real local work: visual office, approvals, runs, memory review and local AI brief workflow.
          </p>
        </div>
        <div className="flex gap-2">
          <a
            href={STAR_OFFICE_URL}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
          >
            <ExternalLink size={13} />
            Pixel view
          </a>
          <button
            onClick={refresh}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
            style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
          >
            <RefreshCw size={13} />
            Refresh
          </button>
        </div>
      </div>

      {loading && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>Loading live MIS state...</p>}
      {error && <p className="text-xs" style={{ color: "#F87171" }}>Live backend unavailable: {error}</p>}

      <div className="grid grid-cols-12 gap-4 items-start">
        <section
          className="col-span-12 xl:col-span-8 overflow-hidden rounded-lg"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="flex items-center justify-between px-3 py-2 border-b" style={{ borderColor: "var(--mis-border)" }}>
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--mis-text)" }}>
              <Sparkles size={14} style={{ color: "var(--mis-cyan)" }} />
              Live Pixel Office
            </div>
            <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
              state source: AgentOps MIS SQLite
            </div>
          </div>
          <div className="relative bg-black" style={{ aspectRatio: "16 / 9" }}>
            <iframe
              title="Star Office Pixel Workbench"
              src={STAR_OFFICE_URL}
              className="absolute inset-0 h-full w-full"
              style={{ border: 0 }}
            />
          </div>
        </section>

        <aside className="col-span-12 xl:col-span-4 space-y-3">
          <section className="rounded-lg p-3" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="grid grid-cols-2 gap-2">
              {[
                { icon: <Bot size={14} />, label: "Agents", value: metrics?.agents_total ?? "—", color: "var(--mis-cyan)" },
                { icon: <Activity size={14} />, label: "Runs", value: runs.length || metrics?.openclaw_import?.cron_runs || "—", color: "var(--mis-success)" },
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
                  <Link to={`/admin/runs/${briefResult.run_id}`} style={{ color: "var(--mis-cyan)" }}>
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
            {activeTasks.map(task => (
              <Link key={task.task_id} to={`/admin/tasks/${task.task_id}`} className="block rounded p-2.5 hover:opacity-80" style={{ background: "var(--mis-surface2)" }}>
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
            <Link to="/admin/runs" className="text-[11px]" style={{ color: "var(--mis-cyan)" }}>Runs</Link>
          </div>
          <div className="space-y-2">
            {recentRuns.map(run => (
              <Link key={run.run_id} to={`/admin/runs/${run.run_id}`} className="flex items-center justify-between gap-3 rounded p-2.5 hover:opacity-80" style={{ background: "var(--mis-surface2)" }}>
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
              <Link to={`/admin/runs/${latestRun}`} className="block text-[11px] pt-1" style={{ color: "var(--mis-cyan)" }}>
                Latest ledger entry: {latestRun}
              </Link>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
