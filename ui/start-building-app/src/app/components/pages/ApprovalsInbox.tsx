import { useState } from "react";
import { Link } from "react-router";
import { CheckCircle, Clock, RefreshCw, ShieldAlert, XCircle } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { decideApproval, loadAgents, loadApprovals, loadDashboard, loadTasks, loadToolCalls, useLiveData } from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

export function ApprovalsInbox() {
  const { locale } = usePreferences();
  const [busyId, setBusyId] = useState<string | null>(null);
  const { data, loading, error, refresh } = useLiveData(async () => {
    const metrics = await loadDashboard();
    const [approvals, tasks, agents, toolCalls] = await Promise.all([
      loadApprovals(),
      loadTasks(),
      loadAgents(metrics),
      loadToolCalls(),
    ]);
    return { approvals, tasks, agents, toolCalls };
  }, []);

  const approvals = data?.approvals || [];
  const pending = approvals.filter(a => a.decision === "pending");
  const decided = approvals.filter(a => a.decision !== "pending");
  const zh = locale === "zh";
  const copy = pick(locale, {
    en: {
      title: "Approvals Inbox",
      summary: `${pending.length} pending · ${decided.length} decided from live MIS ledger`,
      loading: "Loading live approvals...",
      backendUnavailable: "Live backend unavailable",
      pending: "Pending Approval",
      history: "Decision History",
      empty: "No approvals recorded.",
      approve: "Approve",
      reject: "Reject",
      agent: "Agent",
      task: "Task",
      risk: "Risk",
      expires: "Expires",
      decided: "Decided",
      refresh: "Refresh",
      unknownTool: "Approval-gated action",
    },
    zh: {
      title: "审批收件箱",
      summary: `${pending.length} 个待审批 · ${decided.length} 个已决策，来自实时 MIS 账本`,
      loading: "正在加载实时审批...",
      backendUnavailable: "本地后端不可用",
      pending: "待审批",
      history: "决策历史",
      empty: "暂无审批记录。",
      approve: "批准",
      reject: "拒绝",
      agent: "代理",
      task: "任务",
      risk: "风险",
      expires: "过期",
      decided: "决策时间",
      refresh: "刷新",
      unknownTool: "需审批动作",
    },
  });

  const handleDecision = async (approvalId: string, decision: "approve" | "reject") => {
    setBusyId(approvalId);
    try {
      await decideApproval(approvalId, decision);
      await refresh();
    } finally {
      setBusyId(null);
    }
  };

  const renderCard = (ap: typeof approvals[number]) => {
    const agent = data?.agents.find(a => a.agent_id === ap.requested_by_agent_id);
    const task = data?.tasks.find(t => t.task_id === ap.task_id);
    const tool = data?.toolCalls.find(tc => tc.tool_call_id === ap.tool_call_id);
    const isPending = ap.decision === "pending";

    return (
      <div
        key={ap.approval_id}
        className="rounded-xl p-4"
        style={{
          background: "var(--mis-surface)",
          border: `1px solid ${isPending ? "rgba(251,191,36,0.25)" : "var(--mis-border)"}`,
        }}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1.5 flex-wrap">
              <ShieldAlert size={13} style={{ color: isPending ? "#FBBF24" : "var(--mis-muted)" }} />
              <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
                {tool?.tool_name ?? copy.unknownTool}
              </span>
              <StatusBadge status={ap.decision} />
              {tool && <RiskBadge risk={tool.risk_level} />}
            </div>
            <p className="text-[11px] mb-2 leading-relaxed" style={{ color: "var(--mis-dim)" }}>{ap.reason}</p>

            <div className="flex flex-wrap gap-3 text-[10px]" style={{ color: "var(--mis-muted)" }}>
              <span>{copy.agent}: <span style={{ color: "var(--mis-dim)" }}>{agent?.name ?? ap.requested_by_agent_id}</span></span>
              <span>{copy.task}: <Link to={`/admin/tasks/${ap.task_id}`} style={{ color: "var(--mis-cyan)" }}>{task?.title?.slice(0, 34) ?? ap.task_id}</Link></span>
              {tool && <span>{copy.risk}: <span style={{ color: tool.risk_level === "high" ? "var(--mis-warning)" : "var(--mis-dim)" }}>{tool.risk_level}</span></span>}
              {isPending && (
                <span>{copy.expires}: <span style={{ color: "#FBBF24" }}>{new Date(ap.expires_at).toLocaleString(zh ? "zh-CN" : "en-US")}</span></span>
              )}
              {!isPending && ap.decided_at && (
                <span>{copy.decided}: <span style={{ color: "var(--mis-dim)" }}>{new Date(ap.decided_at).toLocaleString(zh ? "zh-CN" : "en-US")}</span></span>
              )}
            </div>
          </div>

          {isPending && (
            <div className="flex gap-2 shrink-0">
              <button
                onClick={() => void handleDecision(ap.approval_id, "approve")}
                disabled={busyId === ap.approval_id}
                className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
                style={{ background: "rgba(42,157,143,0.15)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.2)" }}
              >
                <CheckCircle size={11} /> {copy.approve}
              </button>
              <button
                onClick={() => void handleDecision(ap.approval_id, "reject")}
                disabled={busyId === ap.approval_id}
                className="flex items-center gap-1 text-[11px] px-3 py-1.5 rounded disabled:opacity-50"
                style={{ background: "rgba(248,113,113,0.12)", color: "#F87171", border: "1px solid rgba(248,113,113,0.2)" }}
              >
                <XCircle size={11} /> {copy.reject}
              </button>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 w-full">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>{copy.summary}</p>
          {loading && <p className="text-xs mt-2" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
          {error && <p className="text-xs mt-2" style={{ color: "#F87171" }}>{copy.backendUnavailable}: {error}</p>}
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
          style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
        >
          <RefreshCw size={13} />
          {copy.refresh}
        </button>
      </div>

      {approvals.length === 0 && !loading && (
        <div className="rounded-xl p-6 text-sm text-center" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)", color: "var(--mis-muted)" }}>
          {copy.empty}
        </div>
      )}

      {pending.length > 0 && (
        <div>
          <div className="flex items-center gap-2 mb-3">
            <Clock size={13} style={{ color: "#FBBF24" }} />
            <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{copy.pending}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded font-semibold" style={{ background: "rgba(251,191,36,0.15)", color: "#FBBF24" }}>
              {pending.length}
            </span>
          </div>
          <div className="space-y-2">{pending.map(renderCard)}</div>
        </div>
      )}

      {decided.length > 0 && (
        <div>
          <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-muted)" }}>{copy.history}</div>
          <div className="space-y-2">{decided.slice(0, 80).map(renderCard)}</div>
        </div>
      )}
    </div>
  );
}
