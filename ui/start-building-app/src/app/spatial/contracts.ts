export type SpatialLocale = "en" | "zh";

export type SpatialProjection = "top-down" | "isometric" | "cutaway" | "graph-space";

export type SpatialNodeKind =
  | "world"
  | "district"
  | "facility"
  | "workspace"
  | "landmark"
  | "portal";

export type SpatialEntityKind =
  | "agent"
  | "activity"
  | "task"
  | "run"
  | "approval"
  | "memory"
  | "artifact"
  | "evaluation"
  | "incident"
  | "event";

export type SpatialAuthorityKind =
  | "workspace"
  | "agent"
  | "task"
  | "run"
  | "approval"
  | "memory"
  | "artifact"
  | "evaluation"
  | "audit"
  | "template"
  | "route";

export type SpatialEntityStatus =
  | "idle"
  | "active"
  | "waiting"
  | "blocked"
  | "failed"
  | "completed"
  | "unknown";

export type SpatialRisk = "low" | "medium" | "high" | "critical";

export type SpatialAssetProvenance =
  | "first_party"
  | "generated_first_party"
  | "planned_first_party";

export interface LocalizedText {
  en: string;
  zh: string;
}

export interface SpatialGridPoint {
  x: number;
  y: number;
}

export interface SpatialGridSize {
  width: number;
  height: number;
}

export interface SpatialAuthorityRef {
  authority: "agentops-mis";
  kind: SpatialAuthorityKind;
  id?: string;
  route: string;
  workspaceId?: string;
  provenance?: string;
}

export interface SpatialPortal {
  id: string;
  nodeId: string;
  label: LocalizedText;
  authorityRef: SpatialAuthorityRef;
  interaction: "open-route" | "open-detail" | "focus-node";
  confirmationRequired: boolean;
}

export interface SemanticWorldNode {
  id: string;
  kind: SpatialNodeKind;
  label: LocalizedText;
  description: LocalizedText;
  parentId: string | null;
  childIds: string[];
  zoomLevel: number;
  gridPosition?: SpatialGridPoint;
  gridSize?: SpatialGridSize;
  tags: string[];
  primaryPortalId?: string;
}

export interface SemanticZoomStage {
  level: number;
  id: string;
  nodeKinds: SpatialNodeKind[];
  cameraMode: "atlas" | "district" | "facility" | "workspace";
  queryScope: "global" | "district" | "facility" | "workspace";
  interactionDepth: "overview" | "navigate" | "inspect" | "operate";
}

export interface WorldTemplateManifest {
  schemaVersion: "spatial-world-template/v0";
  id: string;
  version: string;
  label: LocalizedText;
  description: LocalizedText;
  projection: SpatialProjection;
  tileSize: SpatialGridSize;
  defaultWorldId: string;
  defaultArtKitId: string;
  supportedArtKitIds: string[];
  semanticZoom: SemanticZoomStage[];
  capabilities: {
    tilemap: boolean;
    interiors: boolean;
    semanticZoom: boolean;
    agentPathfinding: boolean;
    animatedAvatars: boolean;
    lighting: boolean;
    weather: boolean;
    minimap: boolean;
    screenshotHooks: boolean;
  };
  rendererRequirements: {
    preferred: "game-canvas" | "dom";
    fallback: "basic-lite";
    minimumWebGLVersion?: 1 | 2;
  };
}

export interface ArtKitAssetSlot {
  id: string;
  kind:
    | "terrain-tileset"
    | "building-tileset"
    | "interior-tileset"
    | "prop-atlas"
    | "avatar-atlas"
    | "effect-atlas"
    | "hud-skin"
    | "font";
  status: "planned" | "prototype" | "ready";
  provenance: SpatialAssetProvenance;
  license: "PROJECT_OWNED" | "PROJECT_GENERATED";
  sourcePath?: string;
  notes?: LocalizedText;
}

export interface ArtKitManifest {
  schemaVersion: "spatial-art-kit/v0";
  id: string;
  version: string;
  label: LocalizedText;
  description: LocalizedText;
  compatibleWorldTemplateIds: string[];
  pixelDensity: {
    logicalTileSize: SpatialGridSize;
    characterFrame: SpatialGridSize;
    scalePolicy: "integer-only";
  };
  visualLanguage: {
    perspective: "top-down" | "isometric" | "cutaway" | "graph-space";
    silhouette: string;
    materialLanguage: string;
    lightingLanguage: string;
    animationLanguage: string;
  };
  requiredAgentAnimations: string[];
  assetSlots: ArtKitAssetSlot[];
}

export interface SpatialWorldManifest {
  schemaVersion: "spatial-world/v0";
  id: string;
  version: string;
  label: LocalizedText;
  templateId: string;
  artKitId: string;
  rootNodeId: string;
  nodes: SemanticWorldNode[];
  portals: SpatialPortal[];
}

export interface SpatialEntity {
  id: string;
  kind: SpatialEntityKind;
  label: string;
  status: SpatialEntityStatus;
  risk: SpatialRisk;
  nodeId: string;
  targetNodeId?: string;
  authorityRef: SpatialAuthorityRef;
  activity?: string;
  metadata?: Record<string, string | number | boolean | null>;
}

export interface SpatialWorldMetrics {
  activeAgents: number;
  activeRuns: number;
  pendingApprovals: number;
  blockedTasks: number;
  failedRuns: number;
  memoryCandidates: number;
  auditEvents: number;
}

export interface SpatialWorldSnapshot {
  schemaVersion: "spatial-snapshot/v0";
  worldId: string;
  generatedAt: string;
  source: "live" | "fallback" | "mixed";
  entities: SpatialEntity[];
  metrics: SpatialWorldMetrics;
}

export interface SpatialProjectionAdapter<Input> {
  readonly id: string;
  project(input: Input): SpatialWorldSnapshot;
}

export interface SpatialHitTarget {
  nodeId?: string;
  entityId?: string;
  portalId?: string;
}

export interface SpatialRendererMountOptions {
  locale: SpatialLocale;
  reducedMotion: boolean;
  onPortalNavigate: (portal: SpatialPortal) => void;
  onFocusChange?: (nodeId: string) => void;
  onEntitySelect?: (entityId: string) => void;
}

export interface SpatialRendererAdapter {
  readonly id: string;
  readonly mode: "basic-lite" | "advanced";
  mount(container: HTMLElement, options: SpatialRendererMountOptions): Promise<void> | void;
  unmount(): Promise<void> | void;
  loadWorld(
    template: WorldTemplateManifest,
    artKit: ArtKitManifest,
    world: SpatialWorldManifest,
  ): Promise<void> | void;
  projectSnapshot(snapshot: SpatialWorldSnapshot): Promise<void> | void;
  focusNode(nodeId: string): Promise<void> | void;
  resolveHitTarget(screenX: number, screenY: number): SpatialHitTarget | null;
  setReducedMotion(enabled: boolean): void;
  captureScreenshot?(): Promise<Blob>;
}
