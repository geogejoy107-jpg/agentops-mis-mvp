import type {
  SpatialAgentGlyphArchetype,
  SpatialAgentPaletteSlot,
  SpatialAgentVisualIdentity,
} from "./contracts";

export const SPATIAL_AGENT_GLYPH_ARCHETYPES: readonly SpatialAgentGlyphArchetype[] = [
  "bridge",
  "spark",
  "forge",
  "fork",
  "lattice",
  "orbit",
  "archive",
  "shield",
  "pulse",
  "prism",
  "portal",
  "stack",
] as const;

export const SPATIAL_AGENT_PALETTE_SLOTS: readonly SpatialAgentPaletteSlot[] = [
  "azure",
  "violet",
  "amber",
  "coral",
  "mint",
  "rose",
  "indigo",
  "lime",
  "sky",
  "orange",
  "slate",
  "gold",
] as const;

export interface AgentIdentityInput {
  id: string;
  name?: string;
  role?: string;
  runtime?: string;
}

const ROLE_ARCHETYPES: readonly [RegExp, SpatialAgentGlyphArchetype][] = [
  [/(commander|orchestrat|manager|lead|planner|coordinat|supervisor|调度|统筹|主管)/i, "bridge"],
  [/(research|paper|scholar|discover|search|论文|研究|检索)/i, "spark"],
  [/(code|developer|engineer|builder|codex|program|软件|开发|工程)/i, "forge"],
  [/(worker|runtime|shell|tool|hermes|openclaw|执行|运行时|工具)/i, "fork"],
  [/(data|analyst|evaluation|metric|benchmark|score|数据|分析|评估|指标)/i, "lattice"],
  [/(browser|web|external|crawl|internet|浏览|网页|外部)/i, "orbit"],
  [/(memory|knowledge|archive|library|document|记忆|知识|档案|文档)/i, "archive"],
  [/(review|approval|security|safety|audit|compliance|审查|审批|安全|审计|合规)/i, "shield"],
  [/(ops|monitor|incident|health|observability|运维|监控|故障|健康)/i, "pulse"],
  [/(synthesis|writer|report|design|creative|summary|综合|写作|报告|设计|总结)/i, "prism"],
  [/(gateway|connector|integration|api|network|接入|连接器|集成|网关)/i, "portal"],
  [/(database|storage|index|cache|sql|数据库|存储|索引)/i, "stack"],
];

const RUNTIME_PALETTES: readonly [RegExp, SpatialAgentPaletteSlot][] = [
  [/(codex|openai)/i, "azure"],
  [/(claude|anthropic)/i, "violet"],
  [/(hermes)/i, "sky"],
  [/(openclaw)/i, "mint"],
  [/(openhands)/i, "orange"],
  [/(crewai)/i, "gold"],
  [/(langgraph)/i, "coral"],
  [/(mock)/i, "slate"],
  [/(dify)/i, "lime"],
];

export function stableAgentIdentityHash(value: string): number {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

function chooseArchetype(searchable: string, hash: number): SpatialAgentGlyphArchetype {
  const matched = ROLE_ARCHETYPES.find(([pattern]) => pattern.test(searchable));
  if (matched) return matched[1];
  return SPATIAL_AGENT_GLYPH_ARCHETYPES[hash % SPATIAL_AGENT_GLYPH_ARCHETYPES.length];
}

function choosePalette(runtime: string, hash: number): SpatialAgentPaletteSlot {
  const matched = RUNTIME_PALETTES.find(([pattern]) => pattern.test(runtime));
  if (matched) return matched[1];
  return SPATIAL_AGENT_PALETTE_SLOTS[(hash >>> 8) % SPATIAL_AGENT_PALETTE_SLOTS.length];
}

export function deriveSpatialAgentIdentity(input: AgentIdentityInput): SpatialAgentVisualIdentity {
  const stableKey = [input.id, input.name || "", input.role || "", input.runtime || ""].join("|");
  const hash = stableAgentIdentityHash(stableKey);
  const searchable = `${input.name || ""} ${input.role || ""} ${input.runtime || ""}`;

  return {
    schemaVersion: "spatial-agent-identity/v0",
    archetype: chooseArchetype(searchable, hash),
    palette: choosePalette(input.runtime || searchable, hash),
    seed: hash,
    variant: (hash % 3) as 0 | 1 | 2,
  };
}

export function spatialAgentIdentityKey(identity: SpatialAgentVisualIdentity): string {
  return `${identity.schemaVersion}:${identity.archetype}:${identity.palette}:${identity.variant}:${identity.seed}`;
}
