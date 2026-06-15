import { Link } from "react-router";
import { Activity, ArrowRight, CheckCircle2, ClipboardCheck, Gauge, XCircle } from "lucide-react";
import { agents, evaluations, runs, tasks } from "../../data/mockData";
import { StatusBadge } from "../shared/StatusBadge";

function agentName(agentId: string) {
  return agents.find((agent) => agent.agent_id === agentId)?.name || agentId;
}

function taskTitle(taskId: string) {
  return tasks.find((task) => task.task_id === taskId)?.title || taskId;
}

export function EvaluationRoom() {
  const total = evaluations.length;
  const passed = evaluations.filter((evaluation) => evaluation.pass_fail === "pass").length;
  const failed = total - passed;
  const averageScore = total ? Math.round(evaluations.reduce((sum, evaluation) => sum + evaluation.score, 0) / total) : 0;
  const failedRuns = runs.filter((run) => ["failed", "error", "blocked", "timeout"].includes(run.status));

  const scoreTiles = [
    { label: "Avg score", value: `${averageScore}/100`, hint: "mock + live-ready", icon: <Gauge size={15} />, tone: "cyan" },
    { label: "Passed gates", value: passed, hint: `${total} evaluations`, icon: <CheckCircle2 size={15} />, tone: "green" },
    { label: "Failed gates", value: failed, hint: "open quality risks", icon: <XCircle size={15} />, tone: failed > 0 ? "red" : "green" },
    { label: "Failed runs", value: failedRuns.length, hint: "runtime incidents", icon: <Activity size={15} />, tone: failedRuns.length > 0 ? "red" : "cyan" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Evaluation Room</h1>
            <span className="rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.24)" }}>
              Quality gate surface
            </span>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            A lightweight room for evaluator results, failed gates and run-quality signals. The Pixel Operating Map links here when an agent needs quality review.
          </p>
        </div>
        <Link
          to="/admin/runs"
          className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
          style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
        >
          Run ledger
          <ArrowRight size={13} />
        </Link>
      </div>

      <section className="grid grid-cols-2 xl:grid-cols-4 gap-3">
        {scoreTiles.map((tile) => {
          const tone = tile.tone === "red" ? "#F87171" : tile.tone === "green" ? "var(--mis-success)" : "var(--mis-cyan)";
          return (
            <div key={tile.label} className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
              <div className="flex items-center gap-2 text-[11px]" style={{ color: tone }}>
                {tile.icon}
                <span style={{ color: "var(--mis-muted)" }}>{tile.label}</span>
              </div>
              <div className="mt-2 text-2xl font-semibold" style={{ color: "var(--mis-text)" }}>{tile.value}</div>
              <div className="mt-1 text-[10px]" style={{ color: "var(--mis-dim)" }}>{tile.hint}</div>
            </div>
          );
        })}
      </section>

      <section className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <div className="xl:col-span-2 rounded-lg overflow-hidden" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="p-4 border-b" style={{ borderColor: "var(--mis-border)" }}>
            <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
              <ClipboardCheck size={15} style={{ color: "var(--mis-cyan)" }} />
              Evaluator result queue
            </div>
            <p className="mt-1 text-[11px]" style={{ color: "var(--mis-dim)" }}>
              Result-level and trajectory-level scores should remain linked to runs, tasks and agents.
            </p>
          </div>
          <div className="divide-y" style={{ borderColor: "var(--mis-border)" }}>
            {evaluations.map((evaluation) => (
              <Link
                key={evaluation.evaluation_id}
                to={`/admin/runs/${evaluation.run_id}`}
                className="block p-4 hover:opacity-80"
                style={{ borderColor: "var(--mis-border)" }}
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[10px]" style={{ color: "var(--mis-cyan)" }}>{evaluation.evaluation_id}</span>
                      <StatusBadge status={evaluation.pass_fail} />
                    </div>
                    <div className="mt-1 text-sm font-medium truncate" style={{ color: "var(--mis-text)" }}>{taskTitle(evaluation.task_id)}</div>
                    <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{evaluation.notes}</p>
                    <div className="mt-2 text-[10px]" style={{ color: "var(--mis-muted)" }}>
                      {agentName(evaluation.agent_id)} · {evaluation.evaluator_type} · {new Date(evaluation.created_at).toLocaleString()}
                    </div>
                  </div>
                  <div className="rounded px-2.5 py-1.5 text-right" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,0.14)" }}>
                    <div className="text-lg font-semibold" style={{ color: evaluation.pass_fail === "pass" ? "var(--mis-success)" : "#F87171" }}>{evaluation.score}</div>
                    <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>score</div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <aside className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>Failure reason analysis</h2>
          <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            v1.3 keeps the Evaluation Room simple: surface failed gates, link to run evidence, and avoid replacing the full run ledger.
          </p>
          <div className="mt-4 space-y-2">
            {failedRuns.length === 0 && (
              <div className="rounded p-3 text-[11px]" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
                No failed runs in the current demo state.
              </div>
            )}
            {failedRuns.map((run) => (
              <Link
                key={run.run_id}
                to={`/admin/runs/${run.run_id}`}
                className="block rounded p-3 hover:opacity-80"
                style={{ background: "rgba(248,113,113,0.10)", border: "1px solid rgba(248,113,113,0.22)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-[10px]" style={{ color: "#FCA5A5" }}>{run.run_id}</span>
                  <StatusBadge status={run.status} />
                </div>
                <div className="mt-1 text-[11px]" style={{ color: "var(--mis-text)" }}>{run.error_type || "Runtime failure"}</div>
                <div className="mt-1 text-[10px] leading-relaxed" style={{ color: "var(--mis-muted)" }}>{run.error_message || run.output_summary}</div>
              </Link>
            ))}
          </div>
          <div className="mt-4 rounded p-3 text-[10px]" style={{ background: "rgba(34,211,238,0.08)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>
            Future v1.4/v1.5 can add evaluator filters, score trends and trace replay once the run ledger emits richer evaluator payloads.
          </div>
        </aside>
      </section>
    </div>
  );
}
