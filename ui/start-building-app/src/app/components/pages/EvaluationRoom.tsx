import { Link } from "react-router";
import { useState } from "react";
import { Activity, ArrowRight, CheckCircle2, ClipboardCheck, Gauge, Play, RefreshCw, ShieldCheck, XCircle } from "lucide-react";
import {
  decideEvaluationCase,
  loadAgents,
  loadEvaluationCaseCandidates,
  loadEvaluationCaseRuns,
  loadEvaluations,
  loadRuns,
  loadTasks,
  runEvaluationCases,
  useLiveData,
  type EvaluationCaseRunPayload,
} from "../../data/liveApi";
import { StatusBadge } from "../shared/StatusBadge";
import { pick, usePreferences } from "../../context/PreferencesContext";

export function EvaluationRoom() {
  const { locale } = usePreferences();
  const [caseAction, setCaseAction] = useState<string | null>(null);
  const [caseActionResult, setCaseActionResult] = useState<string | null>(null);
  const [caseRunPreview, setCaseRunPreview] = useState<EvaluationCaseRunPayload | null>(null);
  const { data, setData, loading, error, refresh } = useLiveData(async () => {
    const [agents, tasks, runs, evaluations, candidateCases, approvedCases, caseRuns] = await Promise.all([
      loadAgents(),
      loadTasks(),
      loadRuns(),
      loadEvaluations(),
      loadEvaluationCaseCandidates({ status: "candidate", limit: 8 }),
      loadEvaluationCaseCandidates({ status: "approved", limit: 8 }),
      loadEvaluationCaseRuns({ limit: 8 }),
    ]);
    return { agents, tasks, runs, evaluations, candidateCases, approvedCases, caseRuns };
  }, []);
  const copy = pick(locale, {
    en: {
      title: "Evaluation Room",
      badge: "Quality gate surface",
      subtitle: "A lightweight room for evaluator results, failed gates and run-quality signals. The Pixel Operating Map links here when an agent needs quality review.",
      runLedger: "Run ledger",
      avgScore: "Avg score",
      passedGates: "Passed gates",
      failedGates: "Failed gates",
      failedRuns: "Failed runs",
      mockHint: "mock + live-ready",
      evaluations: "evaluations",
      qualityRisks: "open quality risks",
      runtimeIncidents: "runtime incidents",
      queueTitle: "Evaluator result queue",
      queueBody: "Result-level and trajectory-level scores should remain linked to runs, tasks and agents.",
      score: "score",
      failureTitle: "Failure reason analysis",
      failureBody: "v1.3 keeps the Evaluation Room simple: surface failed gates, link to run evidence, and avoid replacing the full run ledger.",
      noFailedRuns: "No failed runs in the current demo state.",
      runtimeFailure: "Runtime failure",
      future: "Future v1.4/v1.5 can add evaluator filters, score trends and trace replay once the run ledger emits richer evaluator payloads.",
      caseCandidates: "Regression case candidates",
      caseCandidatesBody: "Approved failures, customer delivery reviews and Commander synthesis reports can become reusable test cases only after human review.",
      noCases: "No candidate evaluation cases yet.",
      approvedCases: "Approved benchmark set",
      noApprovedCases: "No approved evaluation cases yet.",
      recentCaseRuns: "Recent benchmark evidence",
      noCaseRuns: "No benchmark runs yet.",
      approve: "Approve",
      reject: "Reject",
      previewRun: "Preview run",
      confirmRun: "Run approved",
      selected: "selected",
      planned: "planned",
      created: "created",
      skipped: "skipped",
      passed: "passed",
      failed: "failed",
      refresh: "Refresh",
      loading: "Loading live evaluation ledger...",
      error: "Evaluation API error",
    },
    zh: {
      title: "评估室",
      badge: "质量门界面",
      subtitle: "用于展示评估结果、失败质量门和运行质量信号的轻量房间。当某个代理需要质量复核时，像素运营地图会跳到这里。",
      runLedger: "运行账本",
      avgScore: "平均分",
      passedGates: "通过质量门",
      failedGates: "失败质量门",
      failedRuns: "失败运行",
      mockHint: "模拟 + 可接实时",
      evaluations: "条评估",
      qualityRisks: "个开放质量风险",
      runtimeIncidents: "个运行事故",
      queueTitle: "评估结果队列",
      queueBody: "结果级和轨迹级评分需要持续关联到 runs、tasks 和 agents。",
      score: "分数",
      failureTitle: "失败原因分析",
      failureBody: "v1.3 先保持评估室轻量：暴露失败质量门，链接到运行证据，不替代完整运行账本。",
      noFailedRuns: "当前演示状态没有失败运行。",
      runtimeFailure: "运行失败",
      future: "后续 v1.4/v1.5 可以在运行账本输出更丰富评估载荷后，增加评估器筛选、分数趋势和 trace replay。",
      caseCandidates: "回归用例候选",
      caseCandidatesBody: "失败评估、客户交付复核和 Commander 合并报告，都必须先进入人工审核，才能变成可复用测试用例。",
      noCases: "暂无候选评估用例。",
      approvedCases: "已批准基准集",
      noApprovedCases: "暂无已批准评估用例。",
      recentCaseRuns: "最近基准证据",
      noCaseRuns: "暂无基准执行。",
      approve: "批准",
      reject: "拒绝",
      previewRun: "预览执行",
      confirmRun: "执行已批准",
      selected: "已选",
      planned: "计划",
      created: "已创建",
      skipped: "跳过",
      passed: "通过",
      failed: "失败",
      refresh: "刷新",
      loading: "正在加载真实评估账本...",
      error: "评估 API 错误",
    },
  });
  const agents = data?.agents || [];
  const tasks = data?.tasks || [];
  const runs = data?.runs || [];
  const evaluations = data?.evaluations || [];
  const candidateCases = data?.candidateCases;
  const approvedCases = data?.approvedCases;
  const caseRuns = data?.caseRuns;
  const agentName = (agentId: string) => agents.find((agent) => agent.agent_id === agentId)?.name || agentId;
  const taskTitle = (taskId: string) => tasks.find((task) => task.task_id === taskId)?.title || taskId;
  const total = evaluations.length;
  const passed = evaluations.filter((evaluation) => evaluation.pass_fail === "pass").length;
  const failed = total - passed;
  const rawAverageScore = total ? evaluations.reduce((sum, evaluation) => sum + evaluation.score, 0) / total : 0;
  const averageScore = Math.round(rawAverageScore <= 1 ? rawAverageScore * 100 : rawAverageScore);
  const failedRuns = runs.filter((run) => ["failed", "error", "blocked", "timeout"].includes(run.status));
  const handleCaseDecision = async (caseId: string, decision: "approve" | "reject") => {
    const action = `${decision}-${caseId}`;
    setCaseAction(action);
    setCaseActionResult(null);
    try {
      const updatedCase = await decideEvaluationCase(caseId, decision);
      setCaseActionResult(`${caseId} -> ${decision}`);
      setCaseRunPreview(null);
      setData((current) => {
        if (!current) return current;
        const removeCase = (items: typeof current.candidateCases.cases) => items.filter((item) => item.case_id !== updatedCase.case_id);
        const upsertCase = (items: typeof current.approvedCases.cases) => [
          updatedCase,
          ...items.filter((item) => item.case_id !== updatedCase.case_id),
        ].slice(0, 8);
        return {
          ...current,
          candidateCases: {
            ...current.candidateCases,
            cases: removeCase(current.candidateCases.cases),
            summary: {
              ...current.candidateCases.summary,
              candidate: Math.max(0, current.candidateCases.summary.candidate - (updatedCase.review_status === "candidate" ? 0 : 1)),
              approved: updatedCase.review_status === "approved" ? current.candidateCases.summary.approved + 1 : current.candidateCases.summary.approved,
              rejected: updatedCase.review_status === "rejected" ? current.candidateCases.summary.rejected + 1 : current.candidateCases.summary.rejected,
            },
          },
          approvedCases: updatedCase.review_status === "approved"
            ? { ...current.approvedCases, cases: upsertCase(current.approvedCases.cases) }
            : current.approvedCases,
        };
      });
    } catch (err) {
      setCaseActionResult(err instanceof Error ? err.message : String(err));
    } finally {
      setCaseAction(null);
    }
  };
  const handleRunCases = async (confirm_run: boolean, caseIds?: string[]) => {
    const action = `${confirm_run ? "confirm" : "preview"}-${caseIds?.join(",") || "batch"}`;
    setCaseAction(action);
    setCaseActionResult(null);
    try {
      const result = await runEvaluationCases({
        case_ids: caseIds,
        status: "approved",
        runner_type: "rule",
        limit: caseIds?.length || 8,
        confirm_run,
      });
      setCaseRunPreview(result);
      setCaseActionResult(`${result.status}: ${result.summary.created ?? result.summary.planned ?? 0}`);
      if (confirm_run) await refresh();
    } catch (err) {
      setCaseActionResult(err instanceof Error ? err.message : String(err));
    } finally {
      setCaseAction(null);
    }
  };

  const scoreTiles = [
    { label: copy.avgScore, value: `${averageScore}/100`, hint: copy.mockHint, icon: <Gauge size={15} />, tone: "cyan" },
    { label: copy.passedGates, value: passed, hint: `${total} ${copy.evaluations}`, icon: <CheckCircle2 size={15} />, tone: "green" },
    { label: copy.failedGates, value: failed, hint: copy.qualityRisks, icon: <XCircle size={15} />, tone: failed > 0 ? "red" : "green" },
    { label: copy.failedRuns, value: failedRuns.length, hint: copy.runtimeIncidents, icon: <Activity size={15} />, tone: failedRuns.length > 0 ? "red" : "cyan" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
            <span className="rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.24)" }}>
              {copy.badge}
            </span>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {copy.subtitle}
          </p>
        </div>
        <Link
          to="/admin/runs"
          className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
          style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
        >
          {copy.runLedger}
          <ArrowRight size={13} />
        </Link>
        <button
          onClick={() => void refresh()}
          className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
          style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
        >
          {copy.refresh}
        </button>
      </div>

      {(loading || error) && (
        <div className="rounded px-3 py-2 text-xs" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)", color: error ? "#F87171" : "var(--mis-muted)" }}>
          {error ? `${copy.error}: ${error}` : copy.loading}
        </div>
      )}

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
              {copy.queueTitle}
            </div>
            <p className="mt-1 text-[11px]" style={{ color: "var(--mis-dim)" }}>
              {copy.queueBody}
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
                    <div className="text-[9px]" style={{ color: "var(--mis-muted)" }}>{copy.score}</div>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>

        <aside className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.failureTitle}</h2>
          <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {copy.failureBody}
          </p>
          <div className="mt-4 space-y-2">
            {failedRuns.length === 0 && (
              <div className="rounded p-3 text-[11px]" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
                {copy.noFailedRuns}
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
                <div className="mt-1 text-[11px]" style={{ color: "var(--mis-text)" }}>{run.error_type || copy.runtimeFailure}</div>
                <div className="mt-1 text-[10px] leading-relaxed" style={{ color: "var(--mis-muted)" }}>{run.error_message || run.output_summary}</div>
              </Link>
            ))}
          </div>
          <div className="mt-4 rounded p-3 text-[10px]" style={{ background: "rgba(34,211,238,0.08)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>
            {copy.future}
          </div>
        </aside>
      </section>

      <section className="rounded-lg overflow-hidden" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <div className="p-4 border-b" style={{ borderColor: "var(--mis-border)" }}>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
                <ClipboardCheck size={15} style={{ color: "var(--mis-cyan)" }} />
                {copy.caseCandidates}
              </div>
              <p className="mt-1 text-[11px]" style={{ color: "var(--mis-dim)" }}>
                {copy.caseCandidatesBody}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge status={candidateCases?.status || "unknown"} />
              <button
                type="button"
                onClick={() => void handleRunCases(false)}
                disabled={Boolean(caseAction)}
                className="inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[10px]"
                style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)", opacity: caseAction ? 0.65 : 1 }}
              >
                {caseAction === "preview-batch" ? <RefreshCw size={11} /> : <Play size={11} />}
                {copy.previewRun}
              </button>
              <button
                type="button"
                onClick={() => void handleRunCases(true)}
                disabled={Boolean(caseAction)}
                className="inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[10px]"
                style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.28)", opacity: caseAction ? 0.65 : 1 }}
              >
                {caseAction === "confirm-batch" ? <RefreshCw size={11} /> : <ShieldCheck size={11} />}
                {copy.confirmRun}
              </button>
            </div>
          </div>
          {(caseActionResult || caseRunPreview) && (
            <div className="mt-3 grid grid-cols-2 md:grid-cols-5 gap-2">
              {caseRunPreview && [
                [copy.selected, caseRunPreview.summary.selected ?? caseRunPreview.summary.total ?? 0],
                [copy.planned, caseRunPreview.summary.planned ?? caseRunPreview.summary.returned ?? 0],
                [copy.created, caseRunPreview.summary.created ?? 0],
                [copy.skipped, caseRunPreview.summary.skipped ?? 0],
                [
                  (caseRunPreview.summary.failed || 0) > 0 ? copy.failed : copy.passed,
                  (caseRunPreview.summary.failed || 0) > 0 ? caseRunPreview.summary.failed : caseRunPreview.summary.passed ?? 0,
                ],
              ].map(([label, value]) => (
                <div key={String(label)} className="rounded px-2 py-1.5" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,0.14)" }}>
                  <div className="text-[9px] uppercase" style={{ color: "var(--mis-muted)" }}>{label}</div>
                  <div className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{value}</div>
                </div>
              ))}
              {caseActionResult && !caseRunPreview && (
                <div className="col-span-2 md:col-span-5 rounded px-2 py-1.5 text-[10px]" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)", border: "1px solid rgba(148,163,184,0.14)" }}>
                  {caseActionResult}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-3 divide-y xl:divide-y-0 xl:divide-x" style={{ borderColor: "var(--mis-border)" }}>
          <div className="min-w-0">
            <div className="px-4 py-3 text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)", borderBottom: "1px solid var(--mis-border)" }}>{copy.caseCandidates}</div>
            {(candidateCases?.cases || []).length === 0 && (
              <div className="p-4 text-[11px]" style={{ color: "var(--mis-muted)" }}>{copy.noCases}</div>
            )}
            {(candidateCases?.cases || []).map((item) => (
              <div key={item.case_id} className="p-4 border-b last:border-b-0" style={{ borderColor: "var(--mis-border)" }}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px]" style={{ color: "var(--mis-cyan)" }}>{item.case_id}</span>
                  <StatusBadge status={item.case_type} />
                </div>
                <div className="mt-1 text-sm font-medium truncate" style={{ color: "var(--mis-text)" }}>{item.title}</div>
                <p className="mt-1 text-[11px] leading-relaxed line-clamp-2" style={{ color: "var(--mis-dim)" }}>
                  {item.expected_output_summary || item.input_summary || item.failure_mode || item.source_type}
                </p>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={() => void handleCaseDecision(item.case_id, "approve")}
                    disabled={Boolean(caseAction)}
                    className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px]"
                    style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.24)", opacity: caseAction ? 0.65 : 1 }}
                  >
                    {caseAction === `approve-${item.case_id}` ? <RefreshCw size={10} /> : <CheckCircle2 size={10} />}
                    {copy.approve}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleCaseDecision(item.case_id, "reject")}
                    disabled={Boolean(caseAction)}
                    className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px]"
                    style={{ background: "rgba(248,113,113,0.10)", color: "#F87171", border: "1px solid rgba(248,113,113,0.22)", opacity: caseAction ? 0.65 : 1 }}
                  >
                    {caseAction === `reject-${item.case_id}` ? <RefreshCw size={10} /> : <XCircle size={10} />}
                    {copy.reject}
                  </button>
                  {item.run_id && (
                    <Link to={`/admin/runs/${item.run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>Run</Link>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="min-w-0">
            <div className="px-4 py-3 text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)", borderBottom: "1px solid var(--mis-border)" }}>{copy.approvedCases}</div>
            {(approvedCases?.cases || []).length === 0 && (
              <div className="p-4 text-[11px]" style={{ color: "var(--mis-muted)" }}>{copy.noApprovedCases}</div>
            )}
            {(approvedCases?.cases || []).map((item) => (
              <div key={item.case_id} className="p-4 border-b last:border-b-0" style={{ borderColor: "var(--mis-border)" }}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px]" style={{ color: "var(--mis-cyan)" }}>{item.case_id}</span>
                  <StatusBadge status={item.case_type} />
                </div>
                <div className="mt-1 text-sm font-medium truncate" style={{ color: "var(--mis-text)" }}>{item.title}</div>
                <div className="mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>
                  {item.source_type} · {item.agent_id || "agent: —"} · {item.updated_at ? new Date(item.updated_at).toLocaleString() : "—"}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  <button
                    type="button"
                    onClick={() => void handleRunCases(false, [item.case_id])}
                    disabled={Boolean(caseAction)}
                    className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px]"
                    style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)", opacity: caseAction ? 0.65 : 1 }}
                  >
                    {caseAction === `preview-${item.case_id}` ? <RefreshCw size={10} /> : <Play size={10} />}
                    {copy.previewRun}
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleRunCases(true, [item.case_id])}
                    disabled={Boolean(caseAction)}
                    className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px]"
                    style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.24)", opacity: caseAction ? 0.65 : 1 }}
                  >
                    {caseAction === `confirm-${item.case_id}` ? <RefreshCw size={10} /> : <ShieldCheck size={10} />}
                    {copy.confirmRun}
                  </button>
                  {item.task_id && (
                    <Link to={`/admin/tasks/${item.task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>Task</Link>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="min-w-0">
            <div className="px-4 py-3 text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)", borderBottom: "1px solid var(--mis-border)" }}>{copy.recentCaseRuns}</div>
            {(caseRuns?.case_runs || []).length === 0 && (
              <div className="p-4 text-[11px]" style={{ color: "var(--mis-muted)" }}>{copy.noCaseRuns}</div>
            )}
            {(caseRuns?.case_runs || []).map((item) => (
              <div key={item.case_run_id || `${item.case_id}-${item.run_id}`} className="p-4 border-b last:border-b-0" style={{ borderColor: "var(--mis-border)" }}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px]" style={{ color: "var(--mis-cyan)" }}>{item.case_id}</span>
                  <StatusBadge status={item.pass_fail} />
                  <StatusBadge status={item.runner_type} />
                </div>
                <div className="mt-1 text-sm font-medium truncate" style={{ color: "var(--mis-text)" }}>{item.case_title || item.case_id}</div>
                <div className="mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>
                  {item.score} · {item.created_at ? new Date(item.created_at).toLocaleString() : "—"}
                </div>
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {item.run_id && (
                    <Link to={`/admin/runs/${item.run_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(45,212,191,0.10)", color: "var(--mis-success)", border: "1px solid rgba(45,212,191,0.18)" }}>Run</Link>
                  )}
                  {item.task_id && (
                    <Link to={`/admin/tasks/${item.task_id}`} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}>Task</Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}
