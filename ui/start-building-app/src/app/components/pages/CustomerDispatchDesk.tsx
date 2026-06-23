import { ArrowRight, ClipboardCheck, Map, ShieldCheck, Users } from "lucide-react";
import { Link } from "react-router";
import { pick, usePreferences } from "../../context/PreferencesContext";
import { loadAgents, loadDashboard, useLiveData } from "../../data/liveApi";
import { CustomerDispatchPanel } from "../pixel/CustomerDispatchPanel";

export function CustomerDispatchDesk() {
  const { locale } = usePreferences();
  const copy = pick(locale, {
    en: {
      title: "Dispatch Desk",
      eyebrow: "Customer task intake",
      summary: "A direct customer-facing path for submitting useful work to the AI team. It reuses the live MIS workflow APIs, writes ledger evidence, and keeps Hermes/OpenClaw behind explicit confirmation.",
      openPixel: "Open Pixel Office map",
      openWorkers: "Check worker console",
      loading: "Loading live agents...",
      error: "Live backend unavailable",
      evidenceTitle: "What this page proves",
      evidenceBody: "Tasks, worker runs, async jobs, approvals, evaluations, audit logs and customer delivery reports are created through AgentOps MIS, not a standalone demo form.",
      safetyTitle: "Safety boundary",
      safetyBody: "Mock worker writes real ledger evidence; Hermes/OpenClaw live calls require confirm_run and prepared-action approval for external writes.",
      operatorTitle: "Operator handoff",
      operatorBody: "Agents keep using CLI/API/MCP. This browser page is for customers and admins to submit, watch, approve and inspect the work.",
    },
    zh: {
      title: "派活台",
      eyebrow: "客户任务入口",
      summary: "面向客户/管理员的正式派活路径：提交一个有用任务给 AI 团队，复用 MIS 真实 workflow API，写入账本证据，并把 Hermes/OpenClaw 放在显式确认墙之后。",
      openPixel: "打开像素办公室地图",
      openWorkers: "检查 Worker 控制台",
      loading: "正在读取真实代理...",
      error: "本地后端不可用",
      evidenceTitle: "这个页面证明什么",
      evidenceBody: "任务、worker 运行、异步 Job、审批、评估、审计日志和客户交付报告都进入 AgentOps MIS，而不是独立的假表单。",
      safetyTitle: "安全边界",
      safetyBody: "Mock worker 会真实写账本；Hermes/OpenClaw 真实调用必须 confirm_run，外部写入还要 prepared-action 审批。",
      operatorTitle: "执行交接",
      operatorBody: "Agent 仍然走 CLI/API/MCP；浏览器页面服务客户和管理员，用来提交、观察、审批和追溯工作。",
    },
  });

  const { data, loading, error, refresh } = useLiveData(async () => {
    const metrics = await loadDashboard();
    const agents = await loadAgents(metrics);
    return { agents };
  }, []);

  return (
    <div className="space-y-4 max-w-none">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-4xl">
          <div className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}>
            <ClipboardCheck size={12} />
            {copy.eyebrow}
          </div>
          <h1 className="mt-2 text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
          <p className="mt-1 text-xs leading-relaxed" style={{ color: "var(--mis-dim)" }}>{copy.summary}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link
            to="/workspace/pixel-office"
            className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
            style={{ background: "rgba(34,211,238,0.12)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
          >
            <Map size={13} />
            {copy.openPixel}
          </Link>
          <Link
            to="/workspace/workers"
            className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
          >
            <Users size={13} />
            {copy.openWorkers}
            <ArrowRight size={13} />
          </Link>
        </div>
      </div>

      <section className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {[
          { icon: <ClipboardCheck size={14} />, title: copy.evidenceTitle, body: copy.evidenceBody, color: "var(--mis-cyan)" },
          { icon: <ShieldCheck size={14} />, title: copy.safetyTitle, body: copy.safetyBody, color: "var(--mis-success)" },
          { icon: <Users size={14} />, title: copy.operatorTitle, body: copy.operatorBody, color: "var(--mis-purple)" },
        ].map((item) => (
          <div key={item.title} className="rounded-lg p-3" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
              <span style={{ color: item.color }}>{item.icon}</span>
              {item.title}
            </div>
            <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{item.body}</p>
          </div>
        ))}
      </section>

      {loading && <p className="text-xs" style={{ color: "var(--mis-muted)" }}>{copy.loading}</p>}
      {error && <p className="text-xs" style={{ color: "#F87171" }}>{copy.error}: {error}</p>}

      <CustomerDispatchPanel agents={data?.agents || []} locale={locale} onRefresh={refresh} />
    </div>
  );
}
