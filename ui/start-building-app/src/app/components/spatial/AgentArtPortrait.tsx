import type { PixelAgent } from "../pixel/pixelModel";
import {
  SPATIAL_AGENT_ROLE_ACCENTS,
  spatialAgentArtRole,
  spatialAgentArtRoleIndex,
} from "../../spatial/spatialAgentArtMapping";
import type { SpatialAgentArtMode } from "./AdvancedSpatialSurface";

const COZY_SHEET_URL = new URL(
  "../../../assets/spatial/agent-art/v0/cozy-research-agent-v0.png",
  import.meta.url,
).href;
const INDUSTRIAL_ATLAS_URL = new URL(
  "../../../assets/spatial/agent-art/v0/industrial-agent-units-v0.png",
  import.meta.url,
).href;

function statusColor(status: string): string {
  const normalized = status.toLowerCase();
  if (/(failed|blocked|error|unavailable)/.test(normalized)) return "#E76F51";
  if (/(waiting|pending|approval)/.test(normalized)) return "#E9B44C";
  if (/(completed|success|pass)/.test(normalized)) return "#72C49A";
  if (/(running|active|executing|syncing|auditing)/.test(normalized)) return "#56C7B5";
  return "#9CA3AF";
}

export function AgentArtPortrait({
  agent,
  artMode,
}: {
  agent: PixelAgent;
  artMode: SpatialAgentArtMode;
}) {
  const role = spatialAgentArtRole(agent);
  const roleIndex = spatialAgentArtRoleIndex(agent);
  const accent = SPATIAL_AGENT_ROLE_ACCENTS[role];

  return (
    <span
      className="relative inline-flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded"
      style={{
        background: artMode === "cozy" ? "#5D4938" : "#171D23",
        border: `1px solid ${accent}66`,
        imageRendering: "pixelated",
      }}
      data-agent-art-role={role}
      data-agent-art-mode={artMode}
    >
      {artMode === "cozy" ? (
        <span
          aria-hidden="true"
          style={{
            width: 32,
            height: 48,
            backgroundImage: `url(${COZY_SHEET_URL})`,
            backgroundRepeat: "no-repeat",
            backgroundPosition: "0 0",
            backgroundSize: "128px 192px",
            imageRendering: "pixelated",
            transform: "translateY(4px) scale(.82)",
          }}
        />
      ) : (
        <span
          aria-hidden="true"
          style={{
            width: 32,
            height: 32,
            backgroundImage: `url(${INDUSTRIAL_ATLAS_URL})`,
            backgroundRepeat: "no-repeat",
            backgroundPosition: `${-(roleIndex % 3) * 32}px ${-Math.floor(roleIndex / 3) * 32}px`,
            backgroundSize: "96px 64px",
            imageRendering: "pixelated",
            transform: "scale(1.08)",
          }}
        />
      )}
      <span
        className="absolute bottom-0.5 right-0.5 h-2 w-2"
        style={{ background: statusColor(agent.status), border: "1px solid #17120F" }}
        aria-hidden="true"
      />
    </span>
  );
}

export { statusColor as spatialAgentStatusColor };
