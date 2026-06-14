import type { RiskLevel } from "../../data/mockData";

interface RiskBadgeProps {
  risk: RiskLevel;
}

const riskConfig: Record<RiskLevel, { color: string; bg: string }> = {
  low:      { color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  medium:   { color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  high:     { color: "var(--mis-warning)", bg: "rgba(231,111,81,0.15)" },
  critical: { color: "#F87171",            bg: "rgba(248,113,113,0.18)" },
};

export function RiskBadge({ risk }: RiskBadgeProps) {
  const cfg = riskConfig[risk];
  return (
    <span
      className="inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium capitalize"
      style={{ color: cfg.color, background: cfg.bg }}
    >
      {risk}
    </span>
  );
}
