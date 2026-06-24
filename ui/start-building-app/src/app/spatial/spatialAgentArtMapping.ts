import type { PixelAgent } from "../components/pixel/pixelModel";

export const SPATIAL_AGENT_ART_ROLES = [
  "research",
  "coder",
  "browser",
  "memory",
  "approval",
  "runtime",
] as const;

export type SpatialAgentArtRole = (typeof SPATIAL_AGENT_ART_ROLES)[number];

export const SPATIAL_AGENT_ROLE_ACCENTS: Readonly<Record<SpatialAgentArtRole, string>> = {
  research: "#55D6FF",
  coder: "#FFB347",
  browser: "#8BE38B",
  memory: "#B493FF",
  approval: "#FF6F7F",
  runtime: "#FFD84D",
};

export function spatialAgentArtRole(agent: Pick<PixelAgent, "role" | "runtime" | "name">): SpatialAgentArtRole {
  const value = `${agent.role} ${agent.runtime} ${agent.name}`.toLowerCase();
  if (/(review|approval|security|quality|gate)/.test(value)) return "approval";
  if (/(memory|archive|curator|knowledge)/.test(value)) return "memory";
  if (/(browser|search|crawl|web)/.test(value)) return "browser";
  if (/(code|build|engineer|codex|developer)/.test(value)) return "coder";
  if (/(runtime|connector|sync|openclaw|hermes)/.test(value)) return "runtime";
  return "research";
}

export function spatialAgentArtRoleIndex(agent: Pick<PixelAgent, "role" | "runtime" | "name">): number {
  return SPATIAL_AGENT_ART_ROLES.indexOf(spatialAgentArtRole(agent));
}
