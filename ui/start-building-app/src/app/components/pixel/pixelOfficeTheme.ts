import type { PixelLocale, PixelTone } from "./pixelModel";

export type PixelOfficeThemeId = "night-shift" | "cozy-studio" | "blueprint";

export type PixelMaterial =
  | "outline"
  | "wall"
  | "wallHighlight"
  | "wood"
  | "woodDark"
  | "monitorFrame"
  | "monitorActive"
  | "monitorIdle"
  | "rack"
  | "rackPanel"
  | "healthy"
  | "warning"
  | "danger"
  | "shelf"
  | "shelfInset"
  | "plantLeaf"
  | "plantLeafAlt"
  | "plantPot"
  | "paper"
  | "crate"
  | "glass";

export type PixelCharacterPalette = readonly [
  face: string,
  hair: string,
  coat: string,
  dark: string,
  accent: string,
];

export interface PixelOfficeTheme {
  id: PixelOfficeThemeId;
  label: Record<PixelLocale, string>;
  description: Record<PixelLocale, string>;
  swatches: readonly string[];
  frame: {
    canvas: string;
    grid: string;
    border: string;
    insetBorder: string;
    shadow: string;
    path: string;
    pathGrid: string;
    pathBorder: string;
    garden: string;
    gardenPattern: string;
    loading: string;
    controlBar: string;
    controlBorder: string;
    glowA: string;
    glowB: string;
  };
  tones: Record<PixelTone, {
    border: string;
    background: string;
    glow: string;
    light: string;
    floor: string;
  }>;
  materials: Record<PixelMaterial, string>;
  characterPalettes: readonly PixelCharacterPalette[];
  shape: {
    roomClipPath: string;
    roomRadius: string;
    controlRadius: string;
  };
  effects: {
    roomShadow: string;
    selectedShadow: string;
    agentShadow: string;
    selectedAgentShadow: string;
  };
}

const nightShift: PixelOfficeTheme = {
  id: "night-shift",
  label: { en: "Night Shift", zh: "夜班园区" },
  description: {
    en: "Dark management-sim campus with restrained operational signals.",
    zh: "深色管理模拟园区，以克制的运行信号突出风险与状态。",
  },
  swatches: ["#17212b", "#22d3ee", "#a78bfa", "#fbbf24"],
  frame: {
    canvas: "#17212b",
    grid: "rgba(148,163,184,.04)",
    border: "rgba(51,65,85,.94)",
    insetBorder: "rgba(2,6,23,.72)",
    shadow: "0 20px 60px rgba(0,0,0,.34), 6px 7px 0 rgba(2,6,23,.42)",
    path: "#394554",
    pathGrid: "rgba(255,255,255,.05)",
    pathBorder: "rgba(2,6,23,.68)",
    garden: "#193229",
    gardenPattern: "rgba(74,222,128,.18)",
    loading: "repeating-linear-gradient(135deg,rgba(251,191,36,.13) 0 6px,rgba(15,23,42,.32) 6px 12px)",
    controlBar: "rgba(2,6,23,.84)",
    controlBorder: "rgba(148,163,184,.22)",
    glowA: "#22d3ee",
    glowB: "#a78bfa",
  },
  tones: {
    neutral: { border: "rgba(148,163,184,.5)", background: "rgba(30,41,59,.82)", glow: "rgba(148,163,184,.16)", light: "#94a3b8", floor: "#263341" },
    ready: { border: "rgba(52,211,153,.62)", background: "rgba(20,83,69,.64)", glow: "rgba(52,211,153,.2)", light: "#34d399", floor: "#1f3a36" },
    active: { border: "rgba(34,211,238,.66)", background: "rgba(15,70,112,.68)", glow: "rgba(34,211,238,.22)", light: "#22d3ee", floor: "#1d3443" },
    warning: { border: "rgba(251,191,36,.76)", background: "rgba(120,70,15,.62)", glow: "rgba(251,191,36,.24)", light: "#fbbf24", floor: "#45351f" },
    danger: { border: "rgba(248,113,113,.76)", background: "rgba(127,29,29,.66)", glow: "rgba(248,113,113,.25)", light: "#f87171", floor: "#3b2026" },
    purple: { border: "rgba(167,139,250,.68)", background: "rgba(76,29,149,.58)", glow: "rgba(167,139,250,.24)", light: "#a78bfa", floor: "#2c2742" },
    dock: { border: "rgba(34,211,238,.56)", background: "rgba(8,80,100,.58)", glow: "rgba(34,211,238,.18)", light: "#67e8f9", floor: "#173947" },
  },
  materials: {
    outline: "#020617",
    wall: "#111827",
    wallHighlight: "#334155",
    wood: "#8b5e3c",
    woodDark: "#3f2a1d",
    monitorFrame: "#0b1020",
    monitorActive: "#22d3ee",
    monitorIdle: "#334155",
    rack: "#111827",
    rackPanel: "#1e293b",
    healthy: "#34d399",
    warning: "#fbbf24",
    danger: "#f87171",
    shelf: "#5f4634",
    shelfInset: "#281d18",
    plantLeaf: "#22c55e",
    plantLeafAlt: "#4ade80",
    plantPot: "#9a5a38",
    paper: "#e2e8f0",
    crate: "#8b5e3c",
    glass: "rgba(34,211,238,.12)",
  },
  characterPalettes: [
    ["#f1c6a8", "#30231f", "#2563eb", "#1e3a8a", "#67e8f9"],
    ["#dca77e", "#171717", "#7c3aed", "#4c1d95", "#c4b5fd"],
    ["#f0bd8e", "#7c2d12", "#0f766e", "#134e4a", "#5eead4"],
    ["#9f6849", "#111827", "#b45309", "#78350f", "#fde68a"],
    ["#e9b98f", "#4a2840", "#be185d", "#831843", "#f9a8d4"],
  ],
  shape: {
    roomClipPath: "polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px))",
    roomRadius: "0px",
    controlRadius: "0px",
  },
  effects: {
    roomShadow: "0 0 12px rgba(2,6,23,.48), inset 0 0 0 1px rgba(255,255,255,.03)",
    selectedShadow: "0 0 0 2px rgba(255,255,255,.05), 0 0 26px rgba(34,211,238,.2), inset 0 0 0 2px rgba(255,255,255,.04)",
    agentShadow: "drop-shadow(0 4px 3px rgba(2,6,23,.7))",
    selectedAgentShadow: "drop-shadow(0 0 11px rgba(34,211,238,.72))",
  },
};

const cozyStudio: PixelOfficeTheme = {
  ...nightShift,
  id: "cozy-studio",
  label: { en: "Cozy Studio", zh: "温暖工作室" },
  description: {
    en: "Warm wood, soft lamps and a calmer studio atmosphere for daily work.",
    zh: "以木质、柔和灯光和低压色调呈现日常办公氛围。",
  },
  swatches: ["#2c2925", "#d8a45f", "#7fb69b", "#d9826b"],
  frame: {
    ...nightShift.frame,
    canvas: "#2c2925",
    grid: "rgba(255,244,220,.035)",
    border: "#171411",
    insetBorder: "rgba(255,235,202,.08)",
    shadow: "0 20px 55px rgba(25,18,12,.36), 6px 7px 0 rgba(23,20,17,.5)",
    path: "#554d43",
    pathGrid: "rgba(255,244,220,.055)",
    pathBorder: "#211b17",
    garden: "#2f4a3b",
    gardenPattern: "rgba(127,182,155,.2)",
    loading: "repeating-linear-gradient(135deg,rgba(216,164,95,.16) 0 6px,rgba(44,41,37,.44) 6px 12px)",
    controlBar: "rgba(35,28,23,.9)",
    controlBorder: "rgba(239,213,174,.22)",
    glowA: "#7fb69b",
    glowB: "#d8a45f",
  },
  tones: {
    neutral: { border: "rgba(206,190,164,.58)", background: "rgba(74,65,55,.88)", glow: "rgba(206,190,164,.16)", light: "#cdbca4", floor: "#51483e" },
    ready: { border: "rgba(127,182,155,.72)", background: "rgba(53,95,74,.72)", glow: "rgba(127,182,155,.2)", light: "#8bc4a9", floor: "#385447" },
    active: { border: "rgba(111,169,181,.72)", background: "rgba(52,91,100,.72)", glow: "rgba(111,169,181,.22)", light: "#8bc5cf", floor: "#36545b" },
    warning: { border: "rgba(216,164,95,.8)", background: "rgba(113,76,35,.72)", glow: "rgba(216,164,95,.24)", light: "#e2ae69", floor: "#60492f" },
    danger: { border: "rgba(217,130,107,.82)", background: "rgba(111,58,49,.76)", glow: "rgba(217,130,107,.24)", light: "#df8b76", floor: "#5d3933" },
    purple: { border: "rgba(170,145,188,.74)", background: "rgba(82,62,96,.72)", glow: "rgba(170,145,188,.22)", light: "#b9a0c8", floor: "#493c50" },
    dock: { border: "rgba(111,169,181,.7)", background: "rgba(44,88,94,.72)", glow: "rgba(111,169,181,.2)", light: "#8bc5cf", floor: "#345158" },
  },
  materials: {
    ...nightShift.materials,
    outline: "#211b17",
    wall: "#40372f",
    wallHighlight: "#6d5f50",
    wood: "#a66f45",
    woodDark: "#553722",
    monitorFrame: "#282421",
    monitorActive: "#8bc5cf",
    monitorIdle: "#665e55",
    rack: "#39332e",
    rackPanel: "#5a5046",
    healthy: "#8bc4a9",
    warning: "#e2ae69",
    danger: "#df8b76",
    shelf: "#815a3d",
    shelfInset: "#3e2a20",
    plantLeaf: "#6f9f78",
    plantLeafAlt: "#91ba8f",
    plantPot: "#b46f4f",
    paper: "#f2dfc1",
    crate: "#9c6842",
    glass: "rgba(139,197,207,.14)",
  },
  characterPalettes: [
    ["#f0c6a2", "#4b342b", "#6f9f78", "#355445", "#f2dfc1"],
    ["#c9916a", "#2d2420", "#b46f4f", "#6b3d33", "#e2ae69"],
    ["#e0ad83", "#6e3f2e", "#6f899f", "#3e5368", "#8bc5cf"],
    ["#936044", "#251e1b", "#9a7bb0", "#5a4568", "#d9c4e5"],
  ],
  shape: {
    roomClipPath: "none",
    roomRadius: "8px",
    controlRadius: "8px",
  },
  effects: {
    ...nightShift.effects,
    roomShadow: "0 8px 18px rgba(24,16,10,.3), inset 0 0 0 1px rgba(255,244,220,.04)",
    selectedShadow: "0 0 0 2px rgba(255,244,220,.07), 0 0 24px rgba(216,164,95,.2)",
    agentShadow: "drop-shadow(0 4px 3px rgba(28,20,14,.58))",
    selectedAgentShadow: "drop-shadow(0 0 11px rgba(216,164,95,.66))",
  },
};

const blueprint: PixelOfficeTheme = {
  ...nightShift,
  id: "blueprint",
  label: { en: "Blueprint Lab", zh: "蓝图实验室" },
  description: {
    en: "High-contrast schematic mode for structure review and low-distraction navigation.",
    zh: "高对比结构审阅模式，适合低干扰导航和布局检查。",
  },
  swatches: ["#071b2f", "#62d4ff", "#d7f3ff", "#3b82f6"],
  frame: {
    ...nightShift.frame,
    canvas: "#071b2f",
    grid: "rgba(98,212,255,.11)",
    border: "#1d5d82",
    insetBorder: "rgba(215,243,255,.14)",
    shadow: "0 18px 52px rgba(0,8,18,.42), 5px 6px 0 rgba(1,15,30,.6)",
    path: "#0d304d",
    pathGrid: "rgba(98,212,255,.13)",
    pathBorder: "#1d5d82",
    garden: "#0b2943",
    gardenPattern: "rgba(98,212,255,.16)",
    loading: "repeating-linear-gradient(135deg,rgba(98,212,255,.12) 0 5px,rgba(7,27,47,.4) 5px 10px)",
    controlBar: "rgba(4,20,36,.92)",
    controlBorder: "rgba(98,212,255,.28)",
    glowA: "#62d4ff",
    glowB: "#3b82f6",
  },
  tones: {
    neutral: { border: "rgba(215,243,255,.6)", background: "rgba(11,41,67,.86)", glow: "rgba(98,212,255,.16)", light: "#d7f3ff", floor: "#0b2943" },
    ready: { border: "rgba(134,239,172,.72)", background: "rgba(16,74,63,.68)", glow: "rgba(134,239,172,.18)", light: "#86efac", floor: "#123e3b" },
    active: { border: "rgba(98,212,255,.82)", background: "rgba(13,64,96,.76)", glow: "rgba(98,212,255,.24)", light: "#62d4ff", floor: "#0d3655" },
    warning: { border: "rgba(253,224,71,.82)", background: "rgba(93,78,20,.7)", glow: "rgba(253,224,71,.22)", light: "#fde047", floor: "#4b431a" },
    danger: { border: "rgba(252,165,165,.84)", background: "rgba(103,38,49,.72)", glow: "rgba(252,165,165,.24)", light: "#fca5a5", floor: "#4b2530" },
    purple: { border: "rgba(196,181,253,.78)", background: "rgba(63,49,112,.72)", glow: "rgba(196,181,253,.2)", light: "#c4b5fd", floor: "#302a57" },
    dock: { border: "rgba(103,232,249,.8)", background: "rgba(8,75,89,.72)", glow: "rgba(103,232,249,.22)", light: "#67e8f9", floor: "#0b4551" },
  },
  materials: {
    ...nightShift.materials,
    outline: "#02111f",
    wall: "#0b2943",
    wallHighlight: "#1d5d82",
    wood: "#1d5d82",
    woodDark: "#09304c",
    monitorFrame: "#02111f",
    monitorActive: "#62d4ff",
    monitorIdle: "#1d5d82",
    rack: "#08233a",
    rackPanel: "#0f3a5c",
    healthy: "#86efac",
    warning: "#fde047",
    danger: "#fca5a5",
    shelf: "#0d3655",
    shelfInset: "#061c30",
    plantLeaf: "#67e8f9",
    plantLeafAlt: "#d7f3ff",
    plantPot: "#1d5d82",
    paper: "#d7f3ff",
    crate: "#0f3a5c",
    glass: "rgba(98,212,255,.16)",
  },
  characterPalettes: [
    ["#d7f3ff", "#02111f", "#1d5d82", "#09304c", "#62d4ff"],
    ["#c7e8f5", "#0b2943", "#3b82f6", "#1e3a8a", "#d7f3ff"],
    ["#b8dbe8", "#02111f", "#0f766e", "#134e4a", "#67e8f9"],
  ],
  shape: {
    roomClipPath: "none",
    roomRadius: "2px",
    controlRadius: "2px",
  },
  effects: {
    ...nightShift.effects,
    roomShadow: "0 0 0 1px rgba(98,212,255,.08), inset 0 0 0 1px rgba(215,243,255,.04)",
    selectedShadow: "0 0 0 2px rgba(215,243,255,.08), 0 0 24px rgba(98,212,255,.28)",
    agentShadow: "drop-shadow(0 4px 2px rgba(0,8,18,.72))",
    selectedAgentShadow: "drop-shadow(0 0 12px rgba(98,212,255,.8))",
  },
};

export const PIXEL_OFFICE_THEMES: Record<PixelOfficeThemeId, PixelOfficeTheme> = {
  "night-shift": nightShift,
  "cozy-studio": cozyStudio,
  blueprint,
};

export const PIXEL_OFFICE_THEME_LIST = Object.values(PIXEL_OFFICE_THEMES);
export const DEFAULT_PIXEL_OFFICE_THEME_ID: PixelOfficeThemeId = "night-shift";
export const PIXEL_OFFICE_THEME_STORAGE_KEY = "agentops.pixel-office.theme.v1";

export function isPixelOfficeThemeId(value: string | null | undefined): value is PixelOfficeThemeId {
  return Boolean(value && value in PIXEL_OFFICE_THEMES);
}

export function getPixelOfficeTheme(themeId?: PixelOfficeThemeId): PixelOfficeTheme {
  return PIXEL_OFFICE_THEMES[themeId || DEFAULT_PIXEL_OFFICE_THEME_ID];
}