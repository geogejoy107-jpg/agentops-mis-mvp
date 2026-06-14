import type { ReactNode } from "react";

interface MetricCardProps {
  icon: ReactNode;
  iconColor?: string;
  label: string;
  value: string | number;
  sub?: string;
  trend?: "up" | "down" | "neutral";
}

export function MetricCard({ icon, iconColor = "var(--mis-cyan)", label, value, sub, trend }: MetricCardProps) {
  const trendColor = trend === "up" ? "var(--mis-success)" : trend === "down" ? "#F87171" : "var(--mis-dim)";
  const trendSymbol = trend === "up" ? "↑" : trend === "down" ? "↓" : "";

  return (
    <div
      className="rounded-xl p-4 flex flex-col gap-2"
      style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
    >
      <div className="flex items-center justify-between">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ background: `${iconColor}18`, color: iconColor }}
        >
          {icon}
        </div>
        {trend && (
          <span className="text-xs font-medium" style={{ color: trendColor }}>
            {trendSymbol}
          </span>
        )}
      </div>
      <div>
        <div className="text-2xl font-semibold" style={{ color: "var(--mis-text)" }}>
          {value}
        </div>
        <div className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
          {label}
        </div>
        {sub && (
          <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  );
}
