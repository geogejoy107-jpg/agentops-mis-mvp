import type { PixelZoneId } from "./pixelModel";

export type PixelRoomProp =
  | { kind: "block"; x: number; y: number; w: number; h: number; color: string; border?: string; shadow?: string; rotate?: number; opacity?: number; radius?: number }
  | { kind: "desk"; x: number; y: number; w?: number }
  | { kind: "monitor"; x: number; y: number; active?: boolean }
  | { kind: "serverRack"; x: number; y: number; warning?: boolean }
  | { kind: "shelf"; x: number; y: number; w?: number }
  | { kind: "plant"; x: number; y: number };

export interface PixelRoomScene {
  floor?: string;
  props: PixelRoomProp[];
}

const block = (
  x: number,
  y: number,
  w: number,
  h: number,
  color: string,
  options: Omit<Extract<PixelRoomProp, { kind: "block" }>, "kind" | "x" | "y" | "w" | "h" | "color"> = {},
): PixelRoomProp => ({ kind: "block", x, y, w, h, color, ...options });

const desk = (x: number, y: number, w?: number): PixelRoomProp => ({ kind: "desk", x, y, w });
const monitor = (x: number, y: number, active = true): PixelRoomProp => ({ kind: "monitor", x, y, active });
const rack = (x: number, y: number, warning = false): PixelRoomProp => ({ kind: "serverRack", x, y, warning });
const shelf = (x: number, y: number, w?: number): PixelRoomProp => ({ kind: "shelf", x, y, w });
const plant = (x: number, y: number): PixelRoomProp => ({ kind: "plant", x, y });

export const PIXEL_ROOM_SCENES: Record<PixelZoneId, PixelRoomScene> = {
  control_tower: {
    props: [
      desk(34, 51, 38),
      monitor(30, 31),
      monitor(45, 27),
      monitor(60, 31),
      block(15, 20, 10, 10, "#a855f7", { border: "#312e81", shadow: "0 0 10px rgba(168,85,247,.55)" }),
      plant(76, 54),
    ],
  },
  agent_lobby: {
    props: [
      desk(25, 48, 48),
      block(34, 39, 30, 8, "#d8b384", { border: "#5f4634" }),
      plant(6, 55),
      plant(81, 55),
      block(9, 20, 21, 12, "#475569"),
      block(70, 20, 21, 12, "#475569"),
    ],
  },
  task_hall: {
    props: [
      block(10, 16, 80, 24, "#0f172a", { border: "#64748b", shadow: "0 0 10px rgba(34,211,238,.14)" }),
      block(15, 21, 13, 13, "#38bdf8", { opacity: 0.78 }),
      block(34, 21, 13, 13, "#fbbf24", { opacity: 0.78 }),
      block(53, 21, 13, 13, "#a78bfa", { opacity: 0.78 }),
      block(72, 21, 13, 13, "#34d399", { opacity: 0.78 }),
      desk(12, 60, 30),
      desk(58, 60, 30),
    ],
  },
  run_stream: {
    props: [
      rack(8, 25),
      rack(27, 25),
      rack(80, 25),
      block(45, 18, 24, 45, "rgba(34,211,238,.08)", { border: "rgba(34,211,238,.38)", shadow: "0 0 12px rgba(34,211,238,.2)" }),
      block(49, 26, 16, 4, "#22d3ee", { border: "transparent", opacity: 0.65 }),
      block(49, 37, 16, 4, "#22d3ee", { border: "transparent", opacity: 0.55 }),
      block(49, 48, 16, 4, "#22d3ee", { border: "transparent", opacity: 0.45 }),
    ],
  },
  runtime_lab: {
    props: [rack(8, 25), rack(24, 25), desk(50, 58, 38), monitor(57, 38), monitor(73, 38)],
  },
  tool_workshop: {
    props: [
      desk(13, 55, 72),
      block(18, 43, 7, 7, "#60a5fa", { shadow: "0 0 6px rgba(255,255,255,.12)" }),
      block(35, 39, 7, 7, "#f59e0b", { shadow: "0 0 6px rgba(255,255,255,.12)" }),
      block(52, 43, 7, 7, "#a78bfa", { shadow: "0 0 6px rgba(255,255,255,.12)" }),
      block(69, 39, 7, 7, "#34d399", { shadow: "0 0 6px rgba(255,255,255,.12)" }),
      block(8, 17, 84, 8, "#334155", { border: "#0f172a" }),
    ],
  },
  approval_gate: {
    props: [
      block(46, 15, 8, 64, "#111827"),
      block(19, 43, 62, 8, "#fbbf24", { border: "#78350f", rotate: -2, shadow: "0 0 10px rgba(251,191,36,.35)" }),
      block(12, 63, 18, 15, "#7c2d12", { border: "#431407" }),
      block(70, 63, 18, 15, "#7c2d12", { border: "#431407" }),
      block(8, 20, 12, 12, "#fbbf24", { border: "#78350f", shadow: "0 0 12px rgba(251,191,36,.55)" }),
    ],
  },
  evaluation_room: {
    props: [
      block(12, 18, 76, 20, "#0f172a", { border: "#64748b" }),
      block(18, 24, 42, 5, "#34d399", { border: "transparent" }),
      block(18, 31, 58, 3, "#fbbf24", { border: "transparent", opacity: 0.75 }),
      desk(25, 58, 50),
      block(14, 52, 8, 20, "#475569"),
      block(78, 52, 8, 20, "#475569"),
    ],
  },
  memory_archive: {
    props: [shelf(7, 22), shelf(27, 22), shelf(76, 22), desk(48, 59, 23), plant(50, 24)],
  },
  external_base_dock: {
    props: [
      block(8, 55, 84, 12, "#0f172a", { border: "#0891b2" }),
      block(16, 34, 18, 18, "#8b5e3c", { border: "#3f2a1d", shadow: "3px 3px 0 rgba(2,6,23,.32)" }),
      block(43, 31, 18, 18, "#8b5e3c", { border: "#3f2a1d", shadow: "3px 3px 0 rgba(2,6,23,.32)" }),
      block(70, 28, 18, 18, "#8b5e3c", { border: "#3f2a1d", shadow: "3px 3px 0 rgba(2,6,23,.32)" }),
      block(82, 20, 7, 30, "#22d3ee", { border: "#164e63", shadow: "0 0 10px rgba(34,211,238,.45)" }),
    ],
  },
  audit_vault: {
    props: [
      block(27, 17, 46, 57, "#1e293b", { border: "#94a3b8", shadow: "0 0 12px rgba(148,163,184,.2)" }),
      block(34, 25, 32, 40, "#0f172a", { border: "#64748b", radius: 50 }),
      block(47, 38, 7, 14, "#94a3b8", { border: "#334155" }),
      block(40, 44, 21, 4, "#94a3b8", { border: "#334155" }),
    ],
  },
  incident_corner: {
    props: [
      rack(11, 25, true),
      block(38, 18, 48, 8, "#f87171", { border: "#7f1d1d", shadow: "0 0 10px rgba(248,113,113,.55)" }),
      block(40, 50, 10, 10, "#7f1d1d", { border: "#450a0a", rotate: 45 }),
      block(56, 58, 10, 10, "#fbbf24", { border: "#450a0a", rotate: 45 }),
      block(72, 50, 10, 10, "#7f1d1d", { border: "#450a0a", rotate: 45 }),
    ],
  },
  template_market: {
    props: [
      block(10, 28, 22, 34, "#164e63", { shadow: "3px 3px 0 rgba(2,6,23,.3)" }),
      block(14, 35, 14, 7, "#22d3ee", { border: "transparent" }),
      block(17, 48, 8, 8, "#e2e8f0", { border: "#334155" }),
      block(40, 28, 22, 34, "#4c1d95", { shadow: "3px 3px 0 rgba(2,6,23,.3)" }),
      block(44, 35, 14, 7, "#a78bfa", { border: "transparent" }),
      block(47, 48, 8, 8, "#e2e8f0", { border: "#334155" }),
      block(70, 28, 22, 34, "#14532d", { shadow: "3px 3px 0 rgba(2,6,23,.3)" }),
      block(74, 35, 14, 7, "#34d399", { border: "transparent" }),
      block(77, 48, 8, 8, "#e2e8f0", { border: "#334155" }),
    ],
  },
};
