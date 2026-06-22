import type { ReactNode } from "react";
import type { PillTone } from "./Pills";

const COLORS: Record<PillTone, string> = {
  neutral: "var(--ui-text-muted)",
  info: "var(--ui-info)",
  success: "var(--ui-success)",
  warning: "var(--ui-warning)",
  danger: "var(--ui-danger)",
  purple: "var(--ui-purple)",
};

export function MetricCard({
  label,
  value,
  detail,
  tone = "neutral",
  icon,
}: {
  label: string;
  value: ReactNode;
  detail?: string;
  tone?: PillTone;
  icon?: ReactNode;
}) {
  const color = COLORS[tone];
  return (
    <div className="ui-v2-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs font-medium" style={{ color: "var(--ui-text-muted)" }}>{label}</div>
          <div className="mt-2 text-2xl font-semibold tabular-nums" style={{ color: "var(--ui-text)" }}>{value}</div>
          {detail && <div className="mt-1 text-[11px]" style={{ color: "var(--ui-text-subtle)" }}>{detail}</div>}
        </div>
        {icon && (
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border" style={{ color, background: "var(--ui-surface-2)", borderColor: "var(--ui-border)" }}>
            {icon}
          </div>
        )}
      </div>
    </div>
  );
}
