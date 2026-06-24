import type { RiskLevel } from "../../data/mockData";
import { pick, usePreferences } from "../../context/PreferencesContext";

interface RiskBadgeProps {
  risk: RiskLevel;
  label?: string;
}

const riskConfig: Record<RiskLevel, { label: { en: string; zh: string }; color: string; bg: string }> = {
  low:      { label: { en: "Low", zh: "低风险" },       color: "var(--mis-success)", bg: "rgba(42,157,143,0.15)" },
  medium:   { label: { en: "Medium", zh: "中风险" },    color: "#FBBF24",            bg: "rgba(251,191,36,0.12)" },
  high:     { label: { en: "High", zh: "高风险" },      color: "var(--mis-warning)", bg: "rgba(231,111,81,0.15)" },
  critical: { label: { en: "Critical", zh: "严重风险" }, color: "#F87171",            bg: "rgba(248,113,113,0.18)" },
};

export function RiskBadge({ risk, label }: RiskBadgeProps) {
  const { locale } = usePreferences();
  const cfg = riskConfig[risk];
  return (
    <span
      className="inline-flex items-center rounded px-2 py-0.5 text-[11px] font-medium"
      style={{ color: cfg.color, background: cfg.bg }}
    >
      {label || pick(locale, cfg.label)}
    </span>
  );
}
