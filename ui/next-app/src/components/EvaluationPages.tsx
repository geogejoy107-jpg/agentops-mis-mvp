"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ClipboardCheck, Filter, Gauge, RefreshCw } from "lucide-react";
import { AppFrame } from "./AppFrame";
import { loadEvaluations, type EvaluationSummary } from "@/lib/mis";

type LoadState<T> = {
  data: T;
  error: string | null;
  loading: boolean;
};

function statusClass(status?: string) {
  const normalized = status || "unknown";
  if (normalized === "pass") return "status statusGood";
  if (normalized === "fail") return "status statusBad";
  return "status";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function scoreValue(evaluation: EvaluationSummary) {
  const score = Number(evaluation.score || 0);
  return Number.isFinite(score) ? score : 0;
}

export function EvaluationsParityPage() {
  const [resultFilter, setResultFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const [state, setState] = useState<LoadState<EvaluationSummary[]>>({ data: [], error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadEvaluations(), error: null, loading: false });
    } catch (err) {
      setState({ data: [], error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const counts = useMemo(() => {
    const byResult = new Map<string, number>();
    const byType = new Map<string, number>();
    let totalScore = 0;
    for (const evaluation of state.data) {
      const result = evaluation.pass_fail || "unknown";
      const type = evaluation.evaluator_type || "unknown";
      byResult.set(result, (byResult.get(result) || 0) + 1);
      byType.set(type, (byType.get(type) || 0) + 1);
      totalScore += scoreValue(evaluation);
    }
    const averageScore = state.data.length ? Math.round(totalScore / state.data.length) : 0;
    return { averageScore, byResult, byType };
  }, [state.data]);

  const filtered = state.data.filter((evaluation) => {
    if (resultFilter !== "all" && (evaluation.pass_fail || "unknown") !== resultFilter) return false;
    if (typeFilter !== "all" && (evaluation.evaluator_type || "unknown") !== typeFilter) return false;
    return true;
  });
  const resultFilters = ["all", "pass", "fail", "unknown"];
  const typeFilters = ["all", "rule", "llm_mock", "human", "unknown"];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Next.js parity route</p>
          <h1>Evaluation Room</h1>
          <p className="subtle">
            {state.data.length} evaluations · {counts.byResult.get("fail") || 0} failed gates · average score {counts.averageScore}/100
          </p>
        </div>
        <button className="iconButton" onClick={refresh} disabled={state.loading} aria-label="Refresh evaluations">
          <RefreshCw size={17} className={state.loading ? "spin" : ""} />
        </button>
      </header>

      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/evaluations: {state.error}</div> : null}

      <section className="metricGrid">
        <article className="metric">
          <span><Gauge size={15} />Average score</span>
          <strong>{counts.averageScore}/100</strong>
          <small>quality gate signal</small>
        </article>
        <article className="metric">
          <span><ClipboardCheck size={15} />Passed gates</span>
          <strong>{counts.byResult.get("pass") || 0}</strong>
          <small>{state.data.length} total evaluations</small>
        </article>
        <article className="metric">
          <span><ClipboardCheck size={15} />Failed gates</span>
          <strong>{counts.byResult.get("fail") || 0}</strong>
          <small>needs review or remediation</small>
        </article>
      </section>

      <div className="filterBar">
        {resultFilters.map((result) => (
          <button className={`filterChip ${resultFilter === result ? "active" : ""}`} key={result} onClick={() => setResultFilter(result)}>
            {result}
            <span>{result === "all" ? state.data.length : counts.byResult.get(result) || 0}</span>
          </button>
        ))}
        {typeFilters.map((type) => (
          <button className={`filterChip ${typeFilter === type ? "active" : ""}`} key={type} onClick={() => setTypeFilter(type)}>
            {type}
            <span>{type === "all" ? state.data.length : counts.byType.get(type) || 0}</span>
          </button>
        ))}
      </div>

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Evaluation</th>
              <th>Result</th>
              <th>Score</th>
              <th>Run</th>
              <th>Task</th>
              <th>Agent</th>
              <th>Evaluator</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {filtered.slice(0, 160).map((evaluation) => (
              <tr key={evaluation.evaluation_id}>
                <td>
                  <strong>{evaluation.evaluation_id}</strong>
                  <span>{evaluation.notes || "No notes recorded."}</span>
                </td>
                <td><span className={statusClass(evaluation.pass_fail)}>{evaluation.pass_fail || "unknown"}</span></td>
                <td>{scoreValue(evaluation)}</td>
                <td className="mono">
                  {evaluation.run_id ? (
                    <Link className="tableLink" href={`/workspace/runs/${encodeURIComponent(evaluation.run_id)}`}>
                      {evaluation.run_id}
                    </Link>
                  ) : "-"}
                </td>
                <td className="mono">
                  {evaluation.task_id ? (
                    <Link className="tableLink" href={`/workspace/tasks/${encodeURIComponent(evaluation.task_id)}`}>
                      {evaluation.task_id}
                    </Link>
                  ) : "-"}
                </td>
                <td className="mono">{evaluation.agent_id || "-"}</td>
                <td>{evaluation.evaluator_type || "unknown"}</td>
                <td>{formatDate(evaluation.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && !state.loading ? (
          <div className="emptyState">
            <Filter size={24} />
            <p>No evaluations match these filters.</p>
          </div>
        ) : null}
        {state.loading ? (
          <div className="emptyState">
            <ClipboardCheck size={24} />
            <p>Loading evaluation ledger...</p>
          </div>
        ) : null}
      </div>
    </AppFrame>
  );
}
