import topDownRpgCampus from "./manifests/top-down-rpg-campus.v0.json";
import warmResearchArtKit from "./manifests/warm-research-art-kit.v0.json";
import researchDistrict from "./manifests/research-district.v0.json";
import { validateSpatialCatalog } from "./manifestValidation";
import { validateAgentIdentityGrammar } from "./agentIdentityValidation";

const foundation = validateSpatialCatalog(
  topDownRpgCampus,
  warmResearchArtKit,
  researchDistrict,
);

validateAgentIdentityGrammar(foundation.artKit);

export const SPATIAL_OS_FOUNDATION = foundation;

export const SPATIAL_NODE_BY_ID = new Map(
  SPATIAL_OS_FOUNDATION.world.nodes.map((node) => [node.id, node] as const),
);

export const SPATIAL_PORTAL_BY_ID = new Map(
  SPATIAL_OS_FOUNDATION.world.portals.map((portal) => [portal.id, portal] as const),
);

export function spatialNodePath(nodeId: string): string[] {
  const path: string[] = [];
  const seen = new Set<string>();
  let currentId: string | null = nodeId;

  while (currentId) {
    if (seen.has(currentId)) throw new Error(`[Spatial OS catalog] cycle detected at ${currentId}`);
    seen.add(currentId);
    const node = SPATIAL_NODE_BY_ID.get(currentId);
    if (!node) throw new Error(`[Spatial OS catalog] unknown node ${currentId}`);
    path.unshift(node.id);
    currentId = node.parentId;
  }

  return path;
}

export function spatialPortalRoute(portalId: string): string {
  const portal = SPATIAL_PORTAL_BY_ID.get(portalId);
  if (!portal) throw new Error(`[Spatial OS catalog] unknown portal ${portalId}`);
  return portal.authorityRef.route;
}
