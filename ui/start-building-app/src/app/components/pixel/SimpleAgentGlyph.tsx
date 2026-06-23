import type { CSSProperties } from "react";
import type {
  SpatialAgentGlyphArchetype,
  SpatialAgentPaletteSlot,
  SpatialAgentVisualIdentity,
  SpatialRisk,
} from "../../spatial/contracts";
import { deriveSpatialAgentIdentity, type AgentIdentityInput } from "../../spatial/agentIdentity";

interface GlyphRect {
  x: number;
  y: number;
  width: number;
  height: number;
  layer?: "primary" | "secondary";
}

interface GlyphPalette {
  primary: string;
  secondary: string;
  surface: string;
  outline: string;
  glow: string;
}

const GLYPH_PALETTES: Record<SpatialAgentPaletteSlot, GlyphPalette> = {
  azure: { primary: "#38BDF8", secondary: "#7DD3FC", surface: "#0C4A6E", outline: "#082F49", glow: "rgba(56,189,248,.55)" },
  violet: { primary: "#A78BFA", secondary: "#C4B5FD", surface: "#4C1D95", outline: "#2E1065", glow: "rgba(167,139,250,.55)" },
  amber: { primary: "#FBBF24", secondary: "#FDE68A", surface: "#78350F", outline: "#451A03", glow: "rgba(251,191,36,.52)" },
  coral: { primary: "#FB7185", secondary: "#FDA4AF", surface: "#881337", outline: "#4C0519", glow: "rgba(251,113,133,.52)" },
  mint: { primary: "#34D399", secondary: "#A7F3D0", surface: "#065F46", outline: "#022C22", glow: "rgba(52,211,153,.52)" },
  rose: { primary: "#F472B6", secondary: "#FBCFE8", surface: "#9D174D", outline: "#500724", glow: "rgba(244,114,182,.52)" },
  indigo: { primary: "#818CF8", secondary: "#C7D2FE", surface: "#3730A3", outline: "#1E1B4B", glow: "rgba(129,140,248,.52)" },
  lime: { primary: "#A3E635", secondary: "#D9F99D", surface: "#3F6212", outline: "#1A2E05", glow: "rgba(163,230,53,.5)" },
  sky: { primary: "#22D3EE", secondary: "#A5F3FC", surface: "#155E75", outline: "#083344", glow: "rgba(34,211,238,.55)" },
  orange: { primary: "#FB923C", secondary: "#FED7AA", surface: "#9A3412", outline: "#431407", glow: "rgba(251,146,60,.52)" },
  slate: { primary: "#94A3B8", secondary: "#CBD5E1", surface: "#334155", outline: "#0F172A", glow: "rgba(148,163,184,.42)" },
  gold: { primary: "#FACC15", secondary: "#FEF08A", surface: "#854D0E", outline: "#422006", glow: "rgba(250,204,21,.52)" },
};

const GLYPHS: Record<SpatialAgentGlyphArchetype, readonly GlyphRect[]> = {
  bridge: [
    { x: 1, y: 1, width: 2, height: 5 },
    { x: 9, y: 1, width: 2, height: 5 },
    { x: 1, y: 4, width: 10, height: 2 },
    { x: 3, y: 6, width: 2, height: 5 },
    { x: 7, y: 6, width: 2, height: 5 },
    { x: 5, y: 1, width: 2, height: 3, layer: "secondary" },
  ],
  spark: [
    { x: 5, y: 0, width: 2, height: 4 },
    { x: 5, y: 8, width: 2, height: 4 },
    { x: 0, y: 5, width: 4, height: 2 },
    { x: 8, y: 5, width: 4, height: 2 },
    { x: 4, y: 4, width: 4, height: 4 },
    { x: 2, y: 2, width: 2, height: 2, layer: "secondary" },
    { x: 8, y: 2, width: 2, height: 2, layer: "secondary" },
    { x: 2, y: 8, width: 2, height: 2, layer: "secondary" },
    { x: 8, y: 8, width: 2, height: 2, layer: "secondary" },
  ],
  forge: [
    { x: 2, y: 1, width: 8, height: 2 },
    { x: 5, y: 3, width: 2, height: 6 },
    { x: 3, y: 9, width: 6, height: 2 },
    { x: 1, y: 3, width: 3, height: 2, layer: "secondary" },
    { x: 8, y: 3, width: 3, height: 2, layer: "secondary" },
  ],
  fork: [
    { x: 5, y: 4, width: 2, height: 7 },
    { x: 1, y: 1, width: 2, height: 4 },
    { x: 9, y: 1, width: 2, height: 4 },
    { x: 2, y: 3, width: 8, height: 2 },
    { x: 5, y: 0, width: 2, height: 4, layer: "secondary" },
  ],
  lattice: [
    { x: 1, y: 1, width: 2, height: 2 },
    { x: 5, y: 1, width: 2, height: 2, layer: "secondary" },
    { x: 9, y: 1, width: 2, height: 2 },
    { x: 1, y: 5, width: 2, height: 2, layer: "secondary" },
    { x: 5, y: 5, width: 2, height: 2 },
    { x: 9, y: 5, width: 2, height: 2, layer: "secondary" },
    { x: 1, y: 9, width: 2, height: 2 },
    { x: 5, y: 9, width: 2, height: 2, layer: "secondary" },
    { x: 9, y: 9, width: 2, height: 2 },
  ],
  orbit: [
    { x: 3, y: 1, width: 6, height: 2 },
    { x: 1, y: 3, width: 2, height: 6 },
    { x: 9, y: 3, width: 2, height: 6 },
    { x: 3, y: 9, width: 6, height: 2 },
    { x: 5, y: 5, width: 2, height: 2, layer: "secondary" },
    { x: 0, y: 5, width: 2, height: 2, layer: "secondary" },
    { x: 10, y: 5, width: 2, height: 2, layer: "secondary" },
  ],
  archive: [
    { x: 2, y: 1, width: 8, height: 2 },
    { x: 2, y: 3, width: 2, height: 8 },
    { x: 8, y: 3, width: 2, height: 8 },
    { x: 2, y: 6, width: 8, height: 2 },
    { x: 2, y: 10, width: 8, height: 1 },
    { x: 5, y: 4, width: 2, height: 1, layer: "secondary" },
    { x: 5, y: 8, width: 2, height: 1, layer: "secondary" },
  ],
  shield: [
    { x: 3, y: 1, width: 6, height: 2 },
    { x: 2, y: 3, width: 8, height: 4 },
    { x: 3, y: 7, width: 6, height: 2 },
    { x: 4, y: 9, width: 4, height: 2 },
    { x: 5, y: 4, width: 2, height: 4, layer: "secondary" },
    { x: 4, y: 5, width: 4, height: 2, layer: "secondary" },
  ],
  pulse: [
    { x: 0, y: 6, width: 3, height: 2 },
    { x: 2, y: 4, width: 2, height: 4 },
    { x: 4, y: 2, width: 2, height: 8 },
    { x: 6, y: 5, width: 2, height: 3, layer: "secondary" },
    { x: 8, y: 3, width: 2, height: 6 },
    { x: 10, y: 6, width: 2, height: 2 },
  ],
  prism: [
    { x: 5, y: 0, width: 2, height: 2 },
    { x: 3, y: 2, width: 6, height: 2 },
    { x: 2, y: 4, width: 8, height: 4 },
    { x: 3, y: 8, width: 6, height: 2 },
    { x: 5, y: 10, width: 2, height: 2 },
    { x: 5, y: 4, width: 2, height: 4, layer: "secondary" },
  ],
  portal: [
    { x: 1, y: 1, width: 10, height: 2 },
    { x: 1, y: 9, width: 10, height: 2 },
    { x: 1, y: 3, width: 2, height: 6 },
    { x: 9, y: 3, width: 2, height: 6 },
    { x: 4, y: 4, width: 4, height: 4, layer: "secondary" },
    { x: 6, y: 5, width: 3, height: 2, layer: "secondary" },
  ],
  stack: [
    { x: 1, y: 1, width: 8, height: 2 },
    { x: 3, y: 4, width: 8, height: 2, layer: "secondary" },
    { x: 1, y: 7, width: 8, height: 2 },
    { x: 3, y: 10, width: 8, height: 1, layer: "secondary" },
    { x: 9, y: 1, width: 2, height: 2 },
    { x: 1, y: 4, width: 2, height: 2, layer: "secondary" },
    { x: 9, y: 7, width: 2, height: 2 },
  ],
};

const STATUS_COLORS: Record<string, string> = {
  active: "#34D399",
  running: "#34D399",
  executing: "#34D399",
  waiting: "#FBBF24",
  pending: "#FBBF24",
  approval: "#FBBF24",
  blocked: "#FB923C",
  failed: "#F87171",
  error: "#F87171",
  completed: "#86EFAC",
  success: "#86EFAC",
  idle: "#94A3B8",
  ready: "#94A3B8",
  unknown: "#64748B",
};

const RISK_COLORS: Record<SpatialRisk, string> = {
  low: "transparent",
  medium: "#FBBF24",
  high: "#FB923C",
  critical: "#F87171",
};

function statusColor(status?: string) {
  const normalized = String(status || "unknown").toLowerCase();
  const matched = Object.entries(STATUS_COLORS).find(([key]) => normalized.includes(key));
  return matched?.[1] || STATUS_COLORS.unknown;
}

function variantRect(identity: SpatialAgentVisualIdentity): GlyphRect {
  if (identity.variant === 1) return { x: 10, y: 0, width: 2, height: 2, layer: "secondary" };
  if (identity.variant === 2) return { x: 0, y: 10, width: 2, height: 2, layer: "secondary" };
  return { x: 0, y: 0, width: 2, height: 2, layer: "secondary" };
}

export interface SimpleAgentGlyphProps extends AgentIdentityInput {
  identity?: SpatialAgentVisualIdentity;
  size?: number;
  status?: string;
  risk?: SpatialRisk;
  selected?: boolean;
  showStatus?: boolean;
  showRisk?: boolean;
  label?: string;
  className?: string;
}

export function SimpleAgentGlyph({
  identity: providedIdentity,
  size = 18,
  status,
  risk = "low",
  selected = false,
  showStatus = true,
  showRisk = true,
  label,
  className,
  ...identityInput
}: SimpleAgentGlyphProps) {
  const identity = providedIdentity || deriveSpatialAgentIdentity(identityInput);
  const palette = GLYPH_PALETTES[identity.palette];
  const rects = [...GLYPHS[identity.archetype], variantRect(identity)];
  const style: CSSProperties = {
    width: size,
    height: size,
    background: palette.surface,
    border: `1px solid ${selected ? palette.secondary : palette.outline}`,
    boxShadow: selected ? `0 0 0 2px ${palette.glow}, 0 0 12px ${palette.glow}` : `0 2px 5px rgba(0,0,0,.3)`,
    imageRendering: "pixelated",
  };

  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center ${className || ""}`}
      style={style}
      role="img"
      aria-label={label || `${identityInput.name || identityInput.id || "Agent"} · ${identity.archetype}`}
      data-agent-identity-version={identity.schemaVersion}
      data-agent-archetype={identity.archetype}
      data-agent-palette={identity.palette}
      data-agent-variant={identity.variant}
    >
      <svg
        viewBox="0 0 12 12"
        width={Math.max(12, size - 4)}
        height={Math.max(12, size - 4)}
        aria-hidden="true"
        shapeRendering="crispEdges"
        style={{ imageRendering: "pixelated" }}
      >
        {rects.map((rect, index) => (
          <rect
            key={`${identity.archetype}-${index}`}
            x={rect.x}
            y={rect.y}
            width={rect.width}
            height={rect.height}
            fill={rect.layer === "secondary" ? palette.secondary : palette.primary}
          />
        ))}
      </svg>
      {showStatus && (
        <span
          className="absolute -bottom-0.5 -right-0.5 h-2 w-2"
          style={{ background: statusColor(status), border: `1px solid ${palette.outline}`, boxShadow: `0 0 5px ${statusColor(status)}` }}
          aria-hidden="true"
          data-agent-status-channel={String(status || "unknown").toLowerCase()}
        />
      )}
      {showRisk && risk !== "low" && (
        <span
          className="absolute -top-0.5 -right-0.5 h-1.5 w-1.5"
          style={{ background: RISK_COLORS[risk], border: `1px solid ${palette.outline}` }}
          aria-hidden="true"
          data-agent-risk-channel={risk}
        />
      )}
    </span>
  );
}

export function agentGlyphPalette(identity: SpatialAgentVisualIdentity): GlyphPalette {
  return GLYPH_PALETTES[identity.palette];
}
