import type { PixelLocale, PixelTone, PixelZoneId } from "./pixelModel";
import type { PixelMaterial } from "./pixelOfficeTheme";

export type PixelOfficeLayerId = "overview" | "command" | "operations" | "knowledge" | "templates";
export type PixelMaterialRef = PixelMaterial | `tone:${PixelTone}`;

export interface PixelOfficeLayer {
  id: PixelOfficeLayerId;
  label: Record<PixelLocale, string>;
  description: Record<PixelLocale, string>;
  zoneIds: readonly PixelZoneId[];
  camera: {
    scale: number;
    origin: string;
  };
}

export type PixelRoomProp =
  | {
      kind: "block";
      x: number;
      y: number;
      w: number;
      h: number;
      material: PixelMaterialRef;
      borderMaterial?: PixelMaterialRef;
      glow?: boolean;
      rotate?: number;
      opacity?: number;
      radius?: string;
    }
  | { kind: "desk"; x: number; y: number; w?: number }
  | { kind: "monitor"; x: number; y: number; active?: boolean }
  | { kind: "serverRack"; x: number; y: number; warning?: boolean }
  | { kind: "shelf"; x: number; y: number; w?: number }
  | { kind: "plant"; x: number; y: number };

export interface PixelRoomScene {
  floorMaterial?: PixelMaterialRef;
  props: PixelRoomProp[];
}

const block = (
  x: number,
  y: number,
  w: number,
  h: number,
  material: PixelMaterialRef,
  options: Omit<Extract<PixelRoomProp, { kind: "block" }>, "kind" | "x" | "y" | "w" | "h" | "material"> = {},
): PixelRoomProp => ({ kind: "block", x, y, w, h, material, ...options });

const desk = (x: number, y: number, w?: number): PixelRoomProp => ({ kind: "desk", x, y, w });
const monitor = (x: number, y: number, active = true): PixelRoomProp => ({ kind: "monitor", x, y, active });
const rack = (x: number, y: number, warning = false): PixelRoomProp => ({ kind: "serverRack", x, y, warning });
const shelf = (x: number, y: number, w?: number): PixelRoomProp => ({ kind: "shelf", x, y, w });
const plant = (x: number, y: number): PixelRoomProp => ({ kind: "plant", x, y });

export const PIXEL_OFFICE_LAYERS: readonly PixelOfficeLayer[] = [
  {
    id: "overview",
    label: { en: "Whole office", zh: "整栋办公室" },
    description: { en: "See every room and operational signal.", zh: "查看所有房间与运行信号。" },
    zoneIds: [],
    camera: { scale: 1, origin: "50% 50%" },
  },
  {
    id: "command",
    label: { en: "Command floor", zh: "指挥层" },
    description: { en: "Control, people, tasks and run flow.", zh: "控制、人员、任务与运行流水。" },
    zoneIds: ["control_tower", "agent_lobby", "task_hall", "run_stream"],
    camera: { scale: 1.28, origin: "50% 8%" },
  },
  {
    id: "operations",
    label: { en: "Operations floor", zh: "执行层" },
    description: { en: "Runtimes, tools, approvals and evaluation.", zh: "运行时、工具、审批与质量评估。" },
    zoneIds: ["runtime_lab", "tool_workshop", "approval_gate", "evaluation_room"],
    camera: { scale: 1.28, origin: "50% 40%" },
  },
  {
    id: "knowledge",
    label: { en: "Knowledge floor", zh: "知识治理层" },
    description: { en: "Memory, external bases, audit and incidents.", zh: "记忆、外部库、审计与故障处置。" },
    zoneIds: ["memory_archive", "external_base_dock", "audit_vault", "incident_corner"],
    camera: { scale: 1.28, origin: "50% 68%" },
  },
  {
    id: "templates",
    label: { en: "Template floor", zh: "模板层" },
    description: { en: "Reusable office and workflow packages.", zh: "可复用的办公室与工作流模板。" },
    zoneIds: ["template_market"],
    camera: { scale: 1.52, origin: "50% 92%" },
  },
];

export const PIXEL_OFFICE_LAYER_BY_ID = PIXEL_OFFICE_LAYERS.reduce<Record<PixelOfficeLayerId, PixelOfficeLayer>>(
  (acc, layer) => {
    acc[layer.id] = layer;
    return acc;
  },
  {} as Record<PixelOfficeLayerId, PixelOfficeLayer>,
);

export const PIXEL_LAYER_BY_ZONE = PIXEL_OFFICE_LAYERS.reduce<Partial<Record<PixelZoneId, PixelOfficeLayerId>>>(
  (acc, layer) => {
    layer.zoneIds.forEach((zoneId) => {
      acc[zoneId] = layer.id;
    });
    return acc;
  },
  {},
);

export function layerDisplay(layer: PixelOfficeLayer, locale: PixelLocale) {
  return {
    label: layer.label[locale],
    description: layer.description[locale],
  };
}

export const PIXEL_ROOM_SCENES: Record<PixelZoneId, PixelRoomScene> = {
  control_tower: {
    props: [
      desk(34, 51, 38),
      monitor(30, 31),
      monitor(45, 27),
      monitor(60, 31),
      block(15, 20, 10, 10, "tone:purple", { glow: true }),
      plant(76, 54),
    ],
  },
  agent_lobby: {
    props: [
      desk(25, 48, 48),
      block(34, 39, 30, 8, "paper", { borderMaterial: "woodDark" }),
      plant(6, 55),
      plant(81, 55),
      block(9, 20, 21, 12, "wallHighlight"),
      block(70, 20, 21, 12, "wallHighlight"),
    ],
  },
  task_hall: {
    props: [
      block(10, 16, 80, 24, "wall", { borderMaterial: "wallHighlight" }),
      block(15, 21, 13, 13, "tone:active", { opacity: 0.78 }),
      block(34, 21, 13, 13, "tone:warning", { opacity: 0.78 }),
      block(53, 21, 13, 13, "tone:purple", { opacity: 0.78 }),
      block(72, 21, 13, 13, "tone:ready", { opacity: 0.78 }),
      desk(12, 60, 30),
      desk(58, 60, 30),
    ],
  },
  run_stream: {
    props: [
      rack(8, 25),
      rack(27, 25),
      rack(80, 25),
      block(45, 18, 24, 45, "glass", { borderMaterial: "tone:active", glow: true }),
      block(49, 26, 16, 4, "tone:active", { opacity: 0.65 }),
      block(49, 37, 16, 4, "tone:active", { opacity: 0.55 }),
      block(49, 48, 16, 4, "tone:active", { opacity: 0.45 }),
    ],
  },
  runtime_lab: {
    props: [rack(8, 25), rack(24, 25), desk(50, 58, 38), monitor(57, 38), monitor(73, 38)],
  },
  tool_workshop: {
    props: [
      desk(13, 55, 72),
      block(18, 43, 7, 7, "tone:active", { glow: true }),
      block(35, 39, 7, 7, "tone:warning", { glow: true }),
      block(52, 43, 7, 7, "tone:purple", { glow: true }),
      block(69, 39, 7, 7, "tone:ready", { glow: true }),
      block(8, 17, 84, 8, "wallHighlight", { borderMaterial: "wall" }),
    ],
  },
  approval_gate: {
    props: [
      block(46, 15, 8, 64, "wall"),
      block(19, 43, 62, 8, "tone:warning", { borderMaterial: "woodDark", rotate: -2, glow: true }),
      block(12, 63, 18, 15, "woodDark", { borderMaterial: "outline" }),
      block(70, 63, 18, 15, "woodDark", { borderMaterial: "outline" }),
      block(8, 20, 12, 12, "tone:warning", { borderMaterial: "woodDark", glow: true }),
    ],
  },
  evaluation_room: {
    props: [
      block(12, 18, 76, 20, "wall", { borderMaterial: "wallHighlight" }),
      block(18, 24, 42, 5, "tone:ready"),
      block(18, 31, 58, 3, "tone:warning", { opacity: 0.75 }),
      desk(25, 58, 50),
      block(14, 52, 8, 20, "wallHighlight"),
      block(78, 52, 8, 20, "wallHighlight"),
    ],
  },
  memory_archive: {
    props: [shelf(7, 22), shelf(27, 22), shelf(76, 22), desk(48, 59, 23), plant(50, 24)],
  },
  external_base_dock: {
    props: [
      block(8, 55, 84, 12, "wall", { borderMaterial: "tone:dock" }),
      block(16, 34, 18, 18, "crate", { borderMaterial: "woodDark" }),
      block(43, 31, 18, 18, "crate", { borderMaterial: "woodDark" }),
      block(70, 28, 18, 18, "crate", { borderMaterial: "woodDark" }),
      block(82, 20, 7, 30, "tone:dock", { borderMaterial: "wall", glow: true }),
    ],
  },
  audit_vault: {
    props: [
      block(27, 17, 46, 57, "rackPanel", { borderMaterial: "paper", glow: true }),
      block(34, 25, 32, 40, "wall", { borderMaterial: "wallHighlight", radius: "50%" }),
      block(47, 38, 7, 14, "paper", { borderMaterial: "wallHighlight" }),
      block(40, 44, 21, 4, "paper", { borderMaterial: "wallHighlight" }),
    ],
  },
  incident_corner: {
    props: [
      rack(11, 25, true),
      block(38, 18, 48, 8, "tone:danger", { borderMaterial: "woodDark", glow: true }),
      block(40, 50, 10, 10, "danger", { borderMaterial: "outline", rotate: 45 }),
      block(56, 58, 10, 10, "warning", { borderMaterial: "outline", rotate: 45 }),
      block(72, 50, 10, 10, "danger", { borderMaterial: "outline", rotate: 45 }),
    ],
  },
  template_market: {
    props: [
      block(10, 28, 22, 34, "tone:dock", { glow: true }),
      block(14, 35, 14, 7, "tone:active"),
      block(17, 48, 8, 8, "paper", { borderMaterial: "wallHighlight" }),
      block(40, 28, 22, 34, "tone:purple", { glow: true }),
      block(44, 35, 14, 7, "tone:purple"),
      block(47, 48, 8, 8, "paper", { borderMaterial: "wallHighlight" }),
      block(70, 28, 22, 34, "tone:ready", { glow: true }),
      block(74, 35, 14, 7, "tone:ready"),
      block(77, 48, 8, 8, "paper", { borderMaterial: "wallHighlight" }),
    ],
  },
};