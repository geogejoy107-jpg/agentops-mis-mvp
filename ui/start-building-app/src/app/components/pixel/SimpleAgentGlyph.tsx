import type { CSSProperties } from "react";
import type { SpatialAgentVisualIdentity, SpatialRisk } from "../../spatial/contracts";
import { deriveSpatialAgentIdentity, type AgentIdentityInput } from "../../spatial/agentIdentity";
import {
  agentGlyphPalette,
  agentGlyphRects,
  type AgentGlyphPalette,
} from "../../spatial/agentGlyphGeometry";

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

function statusColor(status?: string): string {
  const normalized = String(status || "unknown").toLowerCase();
  const matched = Object.entries(STATUS_COLORS).find(([key]) => normalized.includes(key));
  return matched?.[1] || STATUS_COLORS.unknown;
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
  const palette = agentGlyphPalette(identity);
  const rects = agentGlyphRects(identity);
  const style: CSSProperties = {
    width: size,
    height: size,
    background: palette.surface,
    border: `1px solid ${selected ? palette.secondary : palette.outline}`,
    boxShadow: selected
      ? `0 0 0 2px ${palette.glow}, 0 0 12px ${palette.glow}`
      : "0 2px 5px rgba(0,0,0,.3)",
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
          style={{
            background: statusColor(status),
            border: `1px solid ${palette.outline}`,
            boxShadow: `0 0 5px ${statusColor(status)}`,
          }}
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

export function sharedAgentGlyphPalette(identity: SpatialAgentVisualIdentity): AgentGlyphPalette {
  return agentGlyphPalette(identity);
}

export { agentGlyphPalette } from "../../spatial/agentGlyphGeometry";
