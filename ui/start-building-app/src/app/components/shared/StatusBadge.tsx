import { pick, usePreferences } from "../../context/PreferencesContext";

interface StatusBadgeProps {
  status: string;
  size?: "sm" | "md";
  label?: string;
}

const statusConfig: Record<string, { label: { en: string; zh: string }; color: string; bg: string }> = {
  // agent status
  idle:              { label: { en: "Idle", zh: "空闲" },                         color: "var(--mis-dim)",     bg: "rgba(107,114,128,0.15)" },
  running:           { label: { en: "Running", zh: "运行中" },                     color: "var(--mis-cyan)",    bg: "rgba(34,211,238,0.12)" },
  paused:            { label: { en: "Paused", zh: "已暂停" },                      color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  error:             { label: { en: "Error", zh: "错误" },                         color: "var(--mis-warning)", bg: "rgba(231,111,81,0.15)" },
  disabled:          { label: { en: "Disabled", zh: "已禁用" },                    color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // task status
  backlog:           { label: { en: "Backlog", zh: "待排期" },                    color: "var(--mis-dim)",     bg: "rgba(107,114,128,0.1)" },
  planned:           { label: { en: "Planned", zh: "已计划" },                    color: "var(--mis-primary)", bg: "rgba(46,134,171,0.15)" },
  waiting_approval:  { label: { en: "Awaiting Approval", zh: "等待审批" },        color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  blocked:           { label: { en: "Blocked", zh: "已阻塞" },                    color: "var(--mis-warning)", bg: "rgba(231,111,81,0.15)" },
  completed:         { label: { en: "Completed", zh: "已完成" },                  color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  failed:            { label: { en: "Failed", zh: "失败" },                       color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
  canceled:          { label: { en: "Canceled", zh: "已取消" },                   color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // approval
  pending:           { label: { en: "Pending", zh: "待处理" },                    color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  approved:          { label: { en: "Approved", zh: "已批准" },                   color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  rejected:          { label: { en: "Rejected", zh: "已拒绝" },                   color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
  expired:           { label: { en: "Expired", zh: "已过期" },                    color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // memory
  candidate:         { label: { en: "Candidate", zh: "候选" },                    color: "var(--mis-cyan)",    bg: "rgba(34,211,238,0.1)" },
  stale:             { label: { en: "Stale", zh: "已陈旧" },                      color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  superseded:        { label: { en: "Superseded", zh: "已替代" },                 color: "var(--mis-muted)",   bg: "rgba(107,114,128,0.1)" },
  // connector
  ready:             { label: { en: "Ready", zh: "就绪" },                        color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  unavailable:       { label: { en: "Unavailable", zh: "不可用" },                color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
  live:              { label: { en: "Live", zh: "实时" },                         color: "var(--mis-cyan)",    bg: "rgba(34,211,238,0.12)" },
  dry_run:           { label: { en: "Dry-run", zh: "安全预演" },                  color: "var(--mis-primary)", bg: "rgba(46,134,171,0.15)" },
  pending_approval:  { label: { en: "Pending Approval", zh: "等待审批" },         color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  // pass/fail
  pass:              { label: { en: "Pass", zh: "通过" },                         color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  fail:              { label: { en: "Fail", zh: "未通过" },                       color: "#F87171",            bg: "rgba(248,113,113,0.15)" },
};

export function StatusBadge({ status, size = "sm", label }: StatusBadgeProps) {
  const { locale } = usePreferences();
  const cfg = statusConfig[status] ?? { label: { en: status, zh: status }, color: "var(--mis-dim)", bg: "rgba(107,114,128,0.1)" };
  const px = size === "md" ? "px-2.5 py-1" : "px-2 py-0.5";
  const fs = size === "md" ? "text-xs" : "text-[11px]";

  return (
    <span
      className={`inline-flex items-center rounded font-medium ${px} ${fs}`}
      style={{ color: cfg.color, background: cfg.bg }}
    >
      {label || pick(locale, cfg.label)}
    </span>
  );
}
