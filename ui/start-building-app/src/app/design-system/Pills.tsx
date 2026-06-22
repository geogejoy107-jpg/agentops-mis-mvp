export type PillTone = "neutral" | "info" | "success" | "warning" | "danger" | "purple";

const STYLES: Record<PillTone, { color: string; background: string; border: string }> = {
  neutral: { color: "var(--ui-text-muted)", background: "var(--ui-surface-2)", border: "var(--ui-border)" },
  info: { color: "var(--ui-info)", background: "rgba(59,130,246,.10)", border: "rgba(59,130,246,.28)" },
  success: { color: "var(--ui-success)", background: "rgba(42,157,143,.10)", border: "rgba(42,157,143,.28)" },
  warning: { color: "var(--ui-warning)", background: "rgba(245,158,11,.10)", border: "rgba(245,158,11,.30)" },
  danger: { color: "var(--ui-danger)", background: "rgba(239,68,68,.10)", border: "rgba(239,68,68,.30)" },
  purple: { color: "var(--ui-purple)", background: "rgba(122,90,248,.10)", border: "rgba(122,90,248,.28)" },
};

export function statusTone(status: string): PillTone {
  const value = status.toLowerCase();
  if (["failed", "blocked", "critical", "error", "unavailable", "rejected", "timeout"].some((token) => value.includes(token))) return "danger";
  if (["waiting", "pending", "attention", "review", "required", "stale", "degraded", "paused"].some((token) => value.includes(token))) return "warning";
  if (["ready", "healthy", "completed", "approved", "pass", "active", "fresh", "running", "verified"].some((token) => value.includes(token))) return "success";
  if (["queued", "planned", "submitted", "draft", "checking"].some((token) => value.includes(token))) return "info";
  if (["memory", "audit", "knowledge", "promotion"].some((token) => value.includes(token))) return "purple";
  return "neutral";
}

function display(value: string) {
  return value.split("_").join(" ");
}

export function StatusPill({ status, label, tone }: { status: string; label?: string; tone?: PillTone }) {
  const style = STYLES[tone || statusTone(status)];
  return <span className="inline-flex min-h-6 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium" style={{ color: style.color, background: style.background, borderColor: style.border }}><span className="h-1.5 w-1.5 rounded-full" style={{ background: style.color }} aria-hidden="true" />{label || display(status)}</span>;
}

export function RiskPill({ risk, label }: { risk: string; label?: string }) {
  const value = risk.toLowerCase();
  const tone: PillTone = value === "critical" || value === "high" ? "danger" : value === "medium" ? "warning" : "success";
  const style = STYLES[tone];
  return <span className="inline-flex min-h-6 items-center rounded-full border px-2 py-0.5 text-[11px] font-medium" style={{ color: style.color, background: style.background, borderColor: style.border }}>{label || display(risk)}</span>;
}
