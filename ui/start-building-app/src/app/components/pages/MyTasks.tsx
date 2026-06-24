import { useState } from "react";
import { Link } from "react-router";
import { Plus, Filter } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { RiskBadge } from "../shared/RiskBadge";
import { loadTasks, useLiveData } from "../../data/liveApi";
import { pick, usePreferences } from "../../context/PreferencesContext";

type FilterStatus = "all" | "running" | "waiting_approval" | "planned" | "completed" | "failed" | "blocked";

const STATUS_TABS: { label: { en: string; zh: string }; value: FilterStatus }[] = [
  { label: { en: "All", zh: "全部" }, value: "all" },
  { label: { en: "Running", zh: "运行中" }, value: "running" },
  { label: { en: "Awaiting Approval", zh: "等待审批" }, value: "waiting_approval" },
  { label: { en: "Planned", zh: "已计划" }, value: "planned" },
  { label: { en: "Completed", zh: "已完成" }, value: "completed" },
  { label: { en: "Failed", zh: "失败" }, value: "failed" },
  { label: { en: "Blocked", zh: "阻塞" }, value: "blocked" },
];

const PRIORITY_COLOR: Record<string, string> = {
  low: "var(--mis-success)", medium: "var(--mis-primary)", high: "var(--mis-warning)", critical: "#F87171",
};

export function MyTasks() {
  const { locale } = usePreferences();
  const [filter, setFilter] = useState<FilterStatus>("all");
  const { data, loading, error, refresh } = useLiveData(() => loadTasks(), []);
  const tasks = data || [];

  const filtered = filter === "all" ? tasks : tasks.filter(t => t.status === filter);
  const copy = pick(locale, {
    en: {
      title: "My Tasks",
      summary: `${tasks.length} tasks · ${tasks.filter(t => t.status === "running").length} active`,
      refresh: "Refresh Live",
      loading: "Loading live tasks...",
      backendUnavailable: "Live backend unavailable",
      empty: "No tasks in this status",
      agent: "Agent",
      due: "Due",
      budget: "Budget",
      priority: {
        low: "low",
        medium: "medium",
        high: "high",
        critical: "critical",
      },
    },
    zh: {
      title: "我的任务",
      summary: `${tasks.length} 个任务 · ${tasks.filter(t => t.status === "running").length} 个运行中`,
      refresh: "刷新实时任务",
      loading: "正在加载实时任务...",
      backendUnavailable: "本地后端不可用",
      empty: "当前状态下暂无任务",
      agent: "负责代理",
      due: "截止",
      budget: "预算",
      priority: {
        low: "低优先级",
        medium: "中优先级",
        high: "高优先级",
        critical: "严重优先级",
      },
    },
  });

  return (
    <div className="space-y-5 w-full">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
            {copy.summary}
          </p>
        </div>
        <button
          onClick={refresh}
          className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded"
          style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.2)" }}
        >
          <Plus size={13} /> {copy.refresh}
        </button>
      </div>
      {loading && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
      {error && <p className="text-xs" style={{ color: "#F87171" }}>{copy.backendUnavailable}: {error}</p>}

      {/* Status filter tabs */}
      <div className="flex gap-1 flex-wrap">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.value}
            onClick={() => setFilter(tab.value)}
            className="text-[11px] px-3 py-1.5 rounded-lg transition-all"
            style={{
              background: filter === tab.value ? "rgba(34,211,238,0.12)" : "var(--mis-surface)",
              color: filter === tab.value ? "var(--mis-cyan)" : "var(--mis-dim)",
              border: `1px solid ${filter === tab.value ? "rgba(34,211,238,0.25)" : "var(--mis-border)"}`,
            }}
          >
            {pick(locale, tab.label)}
            <span className="ml-1.5 opacity-60">
              {tab.value === "all" ? tasks.length : tasks.filter(t => t.status === tab.value).length}
            </span>
          </button>
        ))}
      </div>

      {/* Task list */}
      <div className="space-y-2">
        {filtered.length === 0 && (
          <div className="py-12 text-center" style={{ color: "var(--mis-muted)" }}>
            <Filter size={24} className="mx-auto mb-2 opacity-40" />
            <p className="text-sm">{copy.empty}</p>
          </div>
        )}
        {filtered.map(task => (
          <Link
            key={task.task_id}
            to={`/workspace/tasks/${task.task_id}`}
            className="block rounded-xl p-4 hover:opacity-90 transition-opacity"
            style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <span className="text-sm font-medium" style={{ color: "var(--mis-text)" }}>{task.title}</span>
                  <StatusBadge status={task.status} />
                  <RiskBadge risk={task.risk_level} />
                </div>
                <p className="text-[11px] line-clamp-1" style={{ color: "var(--mis-dim)" }}>{task.description}</p>
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                    {copy.agent}: <span style={{ color: "var(--mis-dim)" }}>{task.owner_agent_id}</span>
                  </span>
                  {task.due_date && (
                    <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                      {copy.due}: <span style={{ color: "var(--mis-dim)" }}>{new Date(task.due_date).toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US")}</span>
                    </span>
                  )}
                  <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
                    {copy.budget}: <span style={{ color: "var(--mis-dim)" }}>${task.budget_limit_usd}</span>
                  </span>
                </div>
              </div>
              <div className="shrink-0 text-right">
                <span
                  className="text-[11px] px-2 py-0.5 rounded font-medium"
                  style={{ color: PRIORITY_COLOR[task.priority], background: `${PRIORITY_COLOR[task.priority]}18` }}
                >
                  {copy.priority[task.priority]}
                </span>
                {task.acceptance_criteria && (
                  <div className="text-[10px] mt-1.5 max-w-48 text-right line-clamp-1" style={{ color: "var(--mis-muted)" }}>
                    {task.acceptance_criteria.slice(0, 40)}…
                  </div>
                )}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
