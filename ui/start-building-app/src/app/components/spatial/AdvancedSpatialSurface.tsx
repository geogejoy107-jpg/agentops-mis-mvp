import { useEffect, useMemo, useRef, useState } from "react";
import type { PixelAgent, PixelLocale, PixelMetrics } from "../pixel/pixelModel";
import {
  AGENT_TARGET_OBJECT_BY_ZONE,
  localizedSpatialText,
  RESEARCH_DISTRICT_LEVEL_COPY,
  RESEARCH_DISTRICT_OBJECTS_BY_LEVEL,
  spatialMetricValue,
  type ResearchDistrictSemanticObject,
  type SpatialAuthorityKind,
  type SpatialSemanticLevel,
  type SpatialVisualType,
} from "../../spatial/researchDistrictSemanticMap";
import {
  findSpatialPath,
  gridPointToNormalized,
  interpolateSpatialPath,
  normalizedPointToGrid,
  spatialBlockedKey,
  type SpatialNormalizedPoint,
} from "../../spatial/spatialPathfinding";

export type SpatialAgentArtMode = "cozy" | "industrial";

interface AdvancedSpatialSurfaceProps {
  agents: PixelAgent[];
  metrics: PixelMetrics;
  level: SpatialSemanticLevel;
  artMode: SpatialAgentArtMode;
  locale: PixelLocale;
  selectedObjectId?: string | null;
  onSelectObject: (object: ResearchDistrictSemanticObject) => void;
  onOpenRoute: (route: string) => void;
}

interface LoadedImages {
  cozy: HTMLImageElement | null;
  industrial: HTMLImageElement | null;
}

interface AgentPathProjection {
  agent: PixelAgent;
  path: SpatialNormalizedPoint[];
  roleIndex: number;
}

const LOGICAL_WIDTH = 960;
const LOGICAL_HEIGHT = 600;
const GRID_WIDTH = 30;
const GRID_HEIGHT = 18;
const COZY_SHEET_URL = new URL(
  "../../../assets/spatial/agent-art/v0/cozy-research-agent-v0.png",
  import.meta.url,
).href;
const INDUSTRIAL_ATLAS_URL = new URL(
  "../../../assets/spatial/agent-art/v0/industrial-agent-units-v0.png",
  import.meta.url,
).href;

const AUTHORITY_COLORS: Readonly<Record<SpatialAuthorityKind, string>> = {
  agent: "#5BB8D1",
  task: "#E7B04B",
  plan: "#C59A65",
  run: "#E2764C",
  tool_call: "#7CA7C9",
  approval: "#E49455",
  artifact: "#9E83C8",
  memory: "#6FA56F",
  evaluation: "#63AFA2",
  runtime: "#6E8FC0",
  audit: "#8B819B",
  delivery: "#C27D7D",
  template: "#AE9A55",
  control: "#6D78A7",
};

const ROLE_ORDER = ["research", "coder", "browser", "memory", "approval", "runtime"] as const;
type IndustrialRole = (typeof ROLE_ORDER)[number];

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function hashText(value: string): number {
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function roleForAgent(agent: PixelAgent): IndustrialRole {
  const value = `${agent.role} ${agent.runtime} ${agent.name}`.toLowerCase();
  if (/(review|approval|security|quality|gate)/.test(value)) return "approval";
  if (/(memory|archive|curator|knowledge)/.test(value)) return "memory";
  if (/(browser|search|crawl|web)/.test(value)) return "browser";
  if (/(code|build|engineer|codex|developer)/.test(value)) return "coder";
  if (/(runtime|connector|sync|openclaw|hermes)/.test(value)) return "runtime";
  return "research";
}

function statusTone(status: string): string {
  const normalized = status.toLowerCase();
  if (/(failed|error|blocked|unavailable)/.test(normalized)) return "#E76F51";
  if (/(waiting|pending|approval|paused)/.test(normalized)) return "#E9B44C";
  if (/(completed|success|pass)/.test(normalized)) return "#72C49A";
  if (/(running|active|executing|syncing|auditing)/.test(normalized)) return "#56C7B5";
  return "#A7B0BC";
}

function riskTone(risk: PixelAgent["risk"]): string | null {
  if (risk === "medium") return "#E9B44C";
  if (risk === "high") return "#E7814C";
  if (risk === "critical") return "#E04F5F";
  return null;
}

function useSpatialImages(): LoadedImages {
  const [images, setImages] = useState<LoadedImages>({ cozy: null, industrial: null });

  useEffect(() => {
    let active = true;
    const cozy = new Image();
    const industrial = new Image();
    cozy.onload = () => active && setImages((current) => ({ ...current, cozy }));
    industrial.onload = () => active && setImages((current) => ({ ...current, industrial }));
    cozy.src = COZY_SHEET_URL;
    industrial.src = INDUSTRIAL_ATLAS_URL;
    return () => {
      active = false;
    };
  }, []);

  return images;
}

function toCanvasBounds(object: ResearchDistrictSemanticObject) {
  return {
    x: (object.bounds.x / 100) * LOGICAL_WIDTH,
    y: (object.bounds.y / 100) * LOGICAL_HEIGHT,
    w: (object.bounds.w / 100) * LOGICAL_WIDTH,
    h: (object.bounds.h / 100) * LOGICAL_HEIGHT,
  };
}

function pixelRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  fill: string,
  outline = "#2A201B",
  outlineWidth = 2,
): void {
  context.fillStyle = outline;
  context.fillRect(Math.round(x - outlineWidth), Math.round(y - outlineWidth), Math.round(width + outlineWidth * 2), Math.round(height + outlineWidth * 2));
  context.fillStyle = fill;
  context.fillRect(Math.round(x), Math.round(y), Math.round(width), Math.round(height));
}

function drawPixelText(
  context: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  options: { size?: number; color?: string; align?: CanvasTextAlign; background?: string } = {},
): void {
  const size = options.size || 11;
  context.font = `600 ${size}px ui-monospace, SFMono-Regular, Menlo, monospace`;
  context.textAlign = options.align || "left";
  context.textBaseline = "middle";
  const metrics = context.measureText(text);
  if (options.background) {
    const offset = options.align === "center" ? metrics.width / 2 : options.align === "right" ? metrics.width : 0;
    context.fillStyle = options.background;
    context.fillRect(Math.round(x - offset - 5), Math.round(y - size / 2 - 4), Math.ceil(metrics.width + 10), size + 8);
  }
  context.fillStyle = options.color || "#F5EBD7";
  context.fillText(text, x, y);
}

function drawGrassTexture(context: CanvasRenderingContext2D, seed: number, industrial: boolean): void {
  const background = industrial ? "#202932" : "#7F9C67";
  context.fillStyle = background;
  context.fillRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);
  let value = seed || 1;
  for (let index = 0; index < 480; index += 1) {
    value = Math.imul(value ^ (value >>> 15), 2246822519) >>> 0;
    const x = value % LOGICAL_WIDTH;
    value = Math.imul(value ^ (value >>> 13), 3266489917) >>> 0;
    const y = value % LOGICAL_HEIGHT;
    context.fillStyle = industrial
      ? index % 3 === 0 ? "#2C3843" : "#25313B"
      : index % 4 === 0 ? "#9AAF76" : index % 3 === 0 ? "#6F8D5C" : "#88A56D";
    context.fillRect(x, y, industrial ? 2 : 3, industrial ? 2 : 1);
  }
}

function drawOutdoorGround(context: CanvasRenderingContext2D, level: SpatialSemanticLevel, industrial: boolean): void {
  drawGrassTexture(context, 0x51a7 + level * 101, industrial);

  if (industrial) {
    context.strokeStyle = "rgba(151,170,184,.14)";
    context.lineWidth = 1;
    for (let x = 0; x <= LOGICAL_WIDTH; x += 32) {
      context.beginPath();
      context.moveTo(x + 0.5, 0);
      context.lineTo(x + 0.5, LOGICAL_HEIGHT);
      context.stroke();
    }
    for (let y = 0; y <= LOGICAL_HEIGHT; y += 32) {
      context.beginPath();
      context.moveTo(0, y + 0.5);
      context.lineTo(LOGICAL_WIDTH, y + 0.5);
      context.stroke();
    }
  }

  // River and stepping bridge provide a stable map landmark without claiming MIS authority.
  context.fillStyle = industrial ? "#243F4B" : "#4D8DA0";
  context.fillRect(0, 305, LOGICAL_WIDTH, 78);
  for (let x = 0; x < LOGICAL_WIDTH; x += 36) {
    context.fillStyle = industrial ? "#345763" : x % 72 === 0 ? "#77B9C0" : "#65A7B0";
    context.fillRect(x, 320 + (x % 72 === 0 ? 2 : 0), 22, 3);
    context.fillRect(x + 10, 356, 24, 2);
  }

  const pathColor = industrial ? "#5A6065" : "#C7AD78";
  const pathHighlight = industrial ? "#737A7D" : "#D9C18D";
  context.fillStyle = pathColor;
  context.fillRect(0, 276, LOGICAL_WIDTH, 24);
  context.fillRect(450, 0, 36, LOGICAL_HEIGHT);
  context.fillRect(0, 392, LOGICAL_WIDTH, 24);
  context.fillStyle = pathHighlight;
  context.fillRect(0, 280, LOGICAL_WIDTH, 4);
  context.fillRect(454, 0, 4, LOGICAL_HEIGHT);
  context.fillRect(0, 396, LOGICAL_WIDTH, 4);

  // Wooden / steel bridge.
  pixelRect(context, 420, 294, 96, 104, industrial ? "#69747A" : "#9B6745", industrial ? "#30383E" : "#4B3225", 3);
  for (let y = 302; y < 392; y += 12) {
    context.fillStyle = industrial ? "#899297" : "#C18A5B";
    context.fillRect(427, y, 82, 7);
  }

  // Decorative trees / pylons are deliberately non-semantic.
  for (const [x, y] of [[35, 55], [115, 500], [868, 62], [910, 470], [365, 70], [665, 505]]) {
    if (industrial) {
      context.fillStyle = "#171D23";
      context.fillRect(x - 5, y + 8, 10, 22);
      context.fillStyle = "#53616A";
      context.fillRect(x - 11, y, 22, 12);
      context.fillStyle = "#83A2AC";
      context.fillRect(x - 6, y + 3, 12, 4);
    } else {
      context.fillStyle = "#4C3425";
      context.fillRect(x - 4, y + 13, 8, 22);
      context.fillStyle = "#426B43";
      context.fillRect(x - 15, y, 30, 24);
      context.fillStyle = "#5E8955";
      context.fillRect(x - 10, y - 7, 20, 20);
      context.fillStyle = "#8AAF66";
      context.fillRect(x - 5, y - 4, 10, 6);
    }
  }
}

function drawInteriorGround(context: CanvasRenderingContext2D, level: SpatialSemanticLevel, industrial: boolean): void {
  context.fillStyle = industrial ? "#1C232B" : level === 2 ? "#D7BD87" : "#B88458";
  context.fillRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);
  const tile = level === 2 ? 32 : 24;
  for (let y = 0; y < LOGICAL_HEIGHT; y += tile) {
    for (let x = 0; x < LOGICAL_WIDTH; x += tile) {
      const alternate = ((x / tile) + (y / tile)) % 2 === 0;
      context.fillStyle = industrial
        ? alternate ? "#222C35" : "#202831"
        : level === 2
          ? alternate ? "#DFC895" : "#D3B67D"
          : alternate ? "#C19164" : "#B78459";
      context.fillRect(x, y, tile - 1, tile - 1);
    }
  }
  context.fillStyle = industrial ? "#36434D" : "#60412E";
  context.fillRect(0, 0, LOGICAL_WIDTH, 22);
  context.fillRect(0, LOGICAL_HEIGHT - 18, LOGICAL_WIDTH, 18);
  context.fillStyle = industrial ? "#51606A" : "#8F6547";
  context.fillRect(0, 22, LOGICAL_WIDTH, 5);
}

function drawMetricLight(
  context: CanvasRenderingContext2D,
  object: ResearchDistrictSemanticObject,
  metrics: PixelMetrics,
  x: number,
  y: number,
  time: number,
): void {
  const raw = metrics[object.metricKey];
  const numeric = typeof raw === "number" ? raw : raw === "ready" ? 0 : 1;
  const pulse = 0.62 + Math.sin(time / 380 + hashText(object.id) % 11) * 0.2;
  context.globalAlpha = numeric > 0 ? pulse : 0.45;
  context.fillStyle = numeric > 0 ? AUTHORITY_COLORS[object.authorityKind] : "#8A949B";
  context.fillRect(Math.round(x), Math.round(y), 7, 7);
  context.fillStyle = "rgba(255,255,255,.55)";
  context.fillRect(Math.round(x + 2), Math.round(y + 1), 2, 2);
  context.globalAlpha = 1;
}

function drawBuilding(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  accent: string,
  visual: SpatialVisualType,
  industrial: boolean,
): void {
  const outline = industrial ? "#11161B" : "#3A2A23";
  const wall = industrial ? "#59636A" : "#D5C198";
  const wallDark = industrial ? "#3A444B" : "#A78561";
  const roof = industrial ? "#343D44" : visual === "greenhouse" ? "#8FB5A7" : visual === "archive" ? "#6F6588" : "#8D4F43";
  const roofHighlight = industrial ? "#64727A" : visual === "greenhouse" ? "#B8D8C9" : "#B96D55";

  context.fillStyle = "rgba(20,15,12,.28)";
  context.fillRect(x + 7, y + 9, width, height);
  pixelRect(context, x + width * 0.1, y + height * 0.34, width * 0.8, height * 0.58, wall, outline, 3);
  context.fillStyle = wallDark;
  context.fillRect(x + width * 0.12, y + height * 0.78, width * 0.76, height * 0.1);

  context.fillStyle = outline;
  context.beginPath();
  context.moveTo(x + width * 0.03, y + height * 0.38);
  context.lineTo(x + width * 0.5, y);
  context.lineTo(x + width * 0.97, y + height * 0.38);
  context.closePath();
  context.fill();
  context.fillStyle = roof;
  context.beginPath();
  context.moveTo(x + width * 0.08, y + height * 0.36);
  context.lineTo(x + width * 0.5, y + 5);
  context.lineTo(x + width * 0.92, y + height * 0.36);
  context.closePath();
  context.fill();
  context.strokeStyle = roofHighlight;
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(x + width * 0.17, y + height * 0.29);
  context.lineTo(x + width * 0.5, y + height * 0.08);
  context.lineTo(x + width * 0.83, y + height * 0.29);
  context.stroke();

  const doorWidth = Math.max(12, width * 0.16);
  pixelRect(context, x + width / 2 - doorWidth / 2, y + height * 0.62, doorWidth, height * 0.28, industrial ? "#273139" : "#674733", outline, 2);
  context.fillStyle = accent;
  context.fillRect(x + width / 2 - 3, y + height * 0.72, 6, 6);

  for (const windowX of [x + width * 0.22, x + width * 0.67]) {
    pixelRect(context, windowX, y + height * 0.48, width * 0.12, height * 0.13, industrial ? "#7CA7B4" : "#8BC4C6", outline, 2);
    context.fillStyle = "rgba(245,247,210,.65)";
    context.fillRect(windowX + 3, y + height * 0.5, width * 0.04, height * 0.035);
  }

  if (visual === "forge" || visual === "workshop") {
    pixelRect(context, x + width * 0.73, y - height * 0.04, width * 0.12, height * 0.34, industrial ? "#59636A" : "#74594B", outline, 2);
    context.globalAlpha = 0.35;
    context.fillStyle = "#D8D1C6";
    context.fillRect(x + width * 0.75, y - height * 0.16, 9, 9);
    context.fillRect(x + width * 0.79, y - height * 0.24, 12, 10);
    context.globalAlpha = 1;
  }

  if (visual === "greenhouse") {
    context.strokeStyle = industrial ? "#A6C8D1" : "#D9EFE4";
    context.lineWidth = 2;
    for (let offset = 0.22; offset < 0.82; offset += 0.18) {
      context.beginPath();
      context.moveTo(x + width * offset, y + height * 0.18);
      context.lineTo(x + width * offset, y + height * 0.7);
      context.stroke();
    }
  }
}

function drawProp(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  accent: string,
  visual: SpatialVisualType,
  industrial: boolean,
  time: number,
): void {
  const outline = industrial ? "#10161C" : "#39291F";
  const wood = industrial ? "#4A5660" : "#875B3F";
  const paper = industrial ? "#B4C1C8" : "#EAD9B7";
  const screen = industrial ? "#6DB8C6" : "#74AEB0";

  context.fillStyle = "rgba(20,15,12,.22)";
  context.fillRect(x + 5, y + 6, width, height);

  switch (visual) {
    case "board":
      pixelRect(context, x, y + height * 0.12, width, height * 0.68, industrial ? "#35414A" : "#B78958", outline, 3);
      context.fillStyle = paper;
      for (let row = 0; row < 3; row += 1) {
        context.fillRect(x + width * 0.13, y + height * (0.23 + row * 0.16), width * (row === 1 ? 0.64 : 0.48), 4);
      }
      context.fillStyle = wood;
      context.fillRect(x + width * 0.18, y + height * 0.78, 5, height * 0.2);
      context.fillRect(x + width * 0.78, y + height * 0.78, 5, height * 0.2);
      break;
    case "gate":
      pixelRect(context, x, y + height * 0.14, width * 0.22, height * 0.78, wood, outline, 3);
      pixelRect(context, x + width * 0.78, y + height * 0.14, width * 0.22, height * 0.78, wood, outline, 3);
      pixelRect(context, x + width * 0.12, y, width * 0.76, height * 0.24, industrial ? "#58636B" : "#A36B4E", outline, 3);
      context.fillStyle = accent;
      context.fillRect(x + width * 0.45, y + height * 0.36, width * 0.1, height * 0.22);
      break;
    case "orchard":
      for (let row = 0; row < 2; row += 1) {
        for (let column = 0; column < 3; column += 1) {
          const treeX = x + width * (0.2 + column * 0.29);
          const treeY = y + height * (0.18 + row * 0.42);
          context.fillStyle = industrial ? "#596B64" : "#4A734A";
          context.fillRect(treeX - 9, treeY, 18, 15);
          context.fillStyle = industrial ? "#7D9285" : "#78A85B";
          context.fillRect(treeX - 5, treeY - 5, 10, 9);
          context.fillStyle = accent;
          context.fillRect(treeX - 2, treeY + 3, 4, 4);
          context.fillStyle = wood;
          context.fillRect(treeX - 2, treeY + 15, 4, 10);
        }
      }
      break;
    case "dock":
      pixelRect(context, x, y + height * 0.48, width, height * 0.32, industrial ? "#57636A" : "#9C6C48", outline, 3);
      context.fillStyle = industrial ? "#77858C" : "#C08B5F";
      for (let offset = 6; offset < width; offset += 12) context.fillRect(x + offset, y + height * 0.52, 6, height * 0.24);
      context.fillStyle = accent;
      context.fillRect(x + width * 0.14, y + height * 0.26, width * 0.18, height * 0.2);
      context.fillRect(x + width * 0.55, y + height * 0.18, width * 0.24, height * 0.28);
      break;
    case "bell":
    case "clock":
      pixelRect(context, x + width * 0.3, y + height * 0.22, width * 0.4, height * 0.7, wood, outline, 3);
      context.fillStyle = industrial ? "#B8C5CB" : "#D3A844";
      context.beginPath();
      context.arc(x + width / 2, y + height * 0.28, Math.max(6, width * 0.17), 0, Math.PI * 2);
      context.fill();
      context.strokeStyle = outline;
      context.lineWidth = 2;
      context.stroke();
      if (visual === "clock") {
        context.strokeStyle = "#3B2B24";
        context.beginPath();
        context.moveTo(x + width / 2, y + height * 0.28);
        context.lineTo(x + width / 2, y + height * 0.2);
        context.moveTo(x + width / 2, y + height * 0.28);
        context.lineTo(x + width * 0.58, y + height * 0.31);
        context.stroke();
      }
      break;
    case "post":
    case "envelope":
      pixelRect(context, x + width * 0.1, y + height * 0.22, width * 0.8, height * 0.58, industrial ? "#65717A" : "#B26C58", outline, 3);
      context.fillStyle = paper;
      context.beginPath();
      context.moveTo(x + width * 0.2, y + height * 0.34);
      context.lineTo(x + width * 0.5, y + height * 0.58);
      context.lineTo(x + width * 0.8, y + height * 0.34);
      context.strokeStyle = paper;
      context.lineWidth = 4;
      context.stroke();
      break;
    case "table":
    case "desk":
    case "bench":
      pixelRect(context, x, y + height * 0.2, width, height * 0.48, visual === "bench" ? (industrial ? "#69757D" : "#9D704F") : wood, outline, 3);
      context.fillStyle = industrial ? "#85939B" : "#B9865C";
      context.fillRect(x + 5, y + height * 0.25, width - 10, 5);
      context.fillStyle = outline;
      context.fillRect(x + width * 0.14, y + height * 0.67, 5, height * 0.27);
      context.fillRect(x + width * 0.8, y + height * 0.67, 5, height * 0.27);
      context.fillStyle = paper;
      context.fillRect(x + width * 0.18, y + height * 0.31, width * 0.28, height * 0.18);
      context.fillStyle = accent;
      context.fillRect(x + width * 0.58, y + height * 0.32, width * 0.18, height * 0.16);
      break;
    case "terminal":
      pixelRect(context, x + width * 0.13, y + height * 0.08, width * 0.74, height * 0.58, industrial ? "#37434C" : "#61584E", outline, 3);
      context.fillStyle = screen;
      context.fillRect(x + width * 0.2, y + height * 0.16, width * 0.6, height * 0.36);
      context.fillStyle = "rgba(225,255,246,.72)";
      context.fillRect(x + width * 0.26, y + height * 0.23, width * 0.34, 3);
      context.fillRect(x + width * 0.26, y + height * 0.32, width * 0.46, 3);
      context.fillStyle = accent;
      context.fillRect(x + width * 0.66, y + height * 0.43, 5, 5);
      pixelRect(context, x + width * 0.24, y + height * 0.7, width * 0.52, height * 0.13, industrial ? "#59636A" : "#805B42", outline, 2);
      break;
    case "archive":
    case "shelf":
    case "cabinet":
    case "drawer":
      pixelRect(context, x, y, width, height, industrial ? "#505C65" : "#7D5A43", outline, 3);
      for (let row = 0; row < 3; row += 1) {
        context.fillStyle = industrial ? "#78858C" : "#B4885F";
        context.fillRect(x + 5, y + height * (0.16 + row * 0.28), width - 10, 4);
        context.fillStyle = row === 1 ? accent : paper;
        context.fillRect(x + width * 0.18, y + height * (0.21 + row * 0.28), width * 0.22, height * 0.12);
        context.fillRect(x + width * 0.52, y + height * (0.21 + row * 0.28), width * 0.28, height * 0.12);
      }
      break;
    case "lamp": {
      const pulse = 0.55 + Math.sin(time / 260) * 0.22;
      context.globalAlpha = pulse;
      context.fillStyle = accent;
      context.beginPath();
      context.arc(x + width / 2, y + height * 0.28, Math.max(9, width * 0.3), 0, Math.PI * 2);
      context.fill();
      context.globalAlpha = 1;
      context.fillStyle = outline;
      context.fillRect(x + width * 0.45, y + height * 0.42, width * 0.1, height * 0.42);
      pixelRect(context, x + width * 0.22, y + height * 0.82, width * 0.56, height * 0.1, wood, outline, 2);
      break;
    }
    case "tray":
    case "folio":
      pixelRect(context, x, y + height * 0.17, width, height * 0.62, visual === "folio" ? paper : wood, outline, 3);
      context.fillStyle = visual === "folio" ? accent : paper;
      context.fillRect(x + width * 0.18, y + height * 0.29, width * 0.62, 4);
      context.fillRect(x + width * 0.18, y + height * 0.46, width * 0.42, 4);
      context.fillRect(x + width * 0.18, y + height * 0.63, width * 0.54, 4);
      break;
    case "gauge":
      context.fillStyle = industrial ? "#59656D" : "#7B5A43";
      context.beginPath();
      context.arc(x + width / 2, y + height * 0.48, Math.min(width, height) * 0.38, Math.PI, Math.PI * 2);
      context.fill();
      context.strokeStyle = outline;
      context.lineWidth = 3;
      context.stroke();
      context.strokeStyle = accent;
      context.beginPath();
      context.moveTo(x + width / 2, y + height * 0.48);
      context.lineTo(x + width * 0.72, y + height * 0.32);
      context.stroke();
      break;
    case "nameplate":
      pixelRect(context, x, y + height * 0.18, width, height * 0.62, industrial ? "#5B6870" : "#9A6A49", outline, 3);
      context.fillStyle = accent;
      context.fillRect(x + width * 0.12, y + height * 0.35, width * 0.14, height * 0.26);
      context.fillStyle = paper;
      context.fillRect(x + width * 0.34, y + height * 0.38, width * 0.52, 4);
      context.fillRect(x + width * 0.34, y + height * 0.55, width * 0.34, 3);
      break;
    default:
      pixelRect(context, x, y, width, height, wood, outline, 3);
      break;
  }
}

function drawSemanticObject(
  context: CanvasRenderingContext2D,
  object: ResearchDistrictSemanticObject,
  metrics: PixelMetrics,
  selected: boolean,
  hovered: boolean,
  artMode: SpatialAgentArtMode,
  time: number,
): void {
  const bounds = toCanvasBounds(object);
  const accent = AUTHORITY_COLORS[object.authorityKind];
  const industrial = artMode === "industrial";

  if (["district", "hall", "forge", "workshop", "archive", "greenhouse"].includes(object.visual) && object.level <= 1) {
    drawBuilding(context, bounds.x, bounds.y, bounds.w, bounds.h, accent, object.visual, industrial);
  } else {
    drawProp(context, bounds.x, bounds.y, bounds.w, bounds.h, accent, object.visual, industrial, time);
  }

  drawMetricLight(context, object, metrics, bounds.x + bounds.w - 10, bounds.y + 8, time);

  if (selected || hovered) {
    context.save();
    context.strokeStyle = selected ? "#FFF1C7" : accent;
    context.lineWidth = selected ? 4 : 2;
    context.setLineDash(selected ? [] : [6, 4]);
    context.strokeRect(bounds.x - 7, bounds.y - 7, bounds.w + 14, bounds.h + 14);
    context.restore();
  }
}

function createBlockedGrid(objects: readonly ResearchDistrictSemanticObject[]): Set<string> {
  const blocked = new Set<string>();
  for (const object of objects) {
    const x0 = clamp(Math.floor((object.bounds.x / 100) * GRID_WIDTH), 0, GRID_WIDTH - 1);
    const x1 = clamp(Math.ceil(((object.bounds.x + object.bounds.w) / 100) * GRID_WIDTH), 0, GRID_WIDTH - 1);
    const y0 = clamp(Math.floor((object.bounds.y / 100) * GRID_HEIGHT), 0, GRID_HEIGHT - 1);
    const y1 = clamp(Math.ceil(((object.bounds.y + object.bounds.h) / 100) * GRID_HEIGHT), 0, GRID_HEIGHT - 1);
    for (let y = y0; y <= y1; y += 1) {
      for (let x = x0; x <= x1; x += 1) blocked.add(spatialBlockedKey({ x, y }));
    }
    const anchor = normalizedPointToGrid(object.walkAnchor, GRID_WIDTH, GRID_HEIGHT);
    blocked.delete(spatialBlockedKey(anchor));
  }
  return blocked;
}

function buildAgentPaths(
  agents: readonly PixelAgent[],
  objects: readonly ResearchDistrictSemanticObject[],
): AgentPathProjection[] {
  const blocked = createBlockedGrid(objects);
  return agents.slice(0, 8).map((agent, index) => {
    const preferredId = AGENT_TARGET_OBJECT_BY_ZONE[agent.targetZone];
    const target = objects.find((object) => object.id === preferredId)
      || objects.find((object) => object.targetZone === agent.targetZone)
      || objects[index % Math.max(1, objects.length)];
    const startNormalized = {
      x: 9 + ((index * 13 + hashText(agent.id) % 17) % 82),
      y: 92 - (index % 3) * 3,
    };
    const goalNormalized = target?.walkAnchor || { x: 50, y: 50 };
    const start = normalizedPointToGrid(startNormalized, GRID_WIDTH, GRID_HEIGHT);
    const goal = normalizedPointToGrid(goalNormalized, GRID_WIDTH, GRID_HEIGHT);
    const localBlocked = new Set(blocked);
    localBlocked.delete(spatialBlockedKey(start));
    localBlocked.delete(spatialBlockedKey(goal));
    const gridPath = findSpatialPath({ width: GRID_WIDTH, height: GRID_HEIGHT, start, goal, blocked: localBlocked });
    return {
      agent,
      path: gridPath.map((point) => gridPointToNormalized(point, GRID_WIDTH, GRID_HEIGHT)),
      roleIndex: ROLE_ORDER.indexOf(roleForAgent(agent)),
    };
  });
}

function drawAgentGroundState(
  context: CanvasRenderingContext2D,
  agent: PixelAgent,
  x: number,
  y: number,
  time: number,
): void {
  const tone = statusTone(agent.status);
  const normalized = agent.status.toLowerCase();
  const pulse = 0.55 + Math.sin(time / 230 + hashText(agent.id) % 7) * 0.18;
  context.save();
  context.globalAlpha = pulse;
  context.strokeStyle = tone;
  context.lineWidth = 2;
  context.beginPath();
  context.ellipse(x, y + 7, 15, 5, 0, 0, Math.PI * 2);
  context.stroke();
  if (/(failed|error|blocked)/.test(normalized)) {
    context.beginPath();
    context.moveTo(x - 6, y + 2);
    context.lineTo(x + 6, y + 12);
    context.moveTo(x + 6, y + 2);
    context.lineTo(x - 6, y + 12);
    context.stroke();
  } else if (/(waiting|pending|approval)/.test(normalized)) {
    context.fillStyle = tone;
    context.fillRect(x - 2, y - 4, 4, 8);
  } else if (/(completed|success|pass)/.test(normalized)) {
    context.fillStyle = tone;
    context.fillRect(x - 1, y - 8, 3, 16);
    context.fillRect(x - 7, y - 2, 15, 3);
  }
  context.restore();

  const risk = riskTone(agent.risk);
  if (risk) {
    context.fillStyle = risk;
    context.beginPath();
    context.moveTo(x + 12, y + 7);
    context.lineTo(x + 18, y + 13);
    context.lineTo(x + 6, y + 13);
    context.closePath();
    context.fill();
  }
}

function drawCozyAccessory(
  context: CanvasRenderingContext2D,
  role: IndustrialRole,
  x: number,
  y: number,
  direction: number,
): void {
  const accent = ["#55D6FF", "#FFB347", "#8BE38B", "#B493FF", "#FF6F7F", "#FFD84D"][ROLE_ORDER.indexOf(role)];
  context.fillStyle = accent;
  if (direction === 0) {
    context.fillRect(x - 6, y - 23, 12, 3); // scarf, part of clothing
    if (role === "coder") context.fillRect(x + 8, y - 15, 4, 10);
    if (role === "browser") context.fillRect(x - 12, y - 15, 4, 8);
    if (role === "approval") context.fillRect(x + 7, y - 18, 7, 9);
    if (role === "runtime") context.fillRect(x - 13, y - 9, 9, 4);
  } else if (direction === 3) {
    context.fillRect(x - 5, y - 21, 10, 3);
  } else {
    context.fillRect(x - 4, y - 22, 8, 3);
    const side = direction === 1 ? -1 : 1;
    context.fillRect(x + side * 8 - 2, y - 15, 4, 9);
  }
}

function drawCozyAgent(
  context: CanvasRenderingContext2D,
  image: HTMLImageElement | null,
  agent: PixelAgent,
  x: number,
  y: number,
  direction: number,
  phase: number,
): void {
  const role = roleForAgent(agent);
  if (image) {
    const column = phase % 4;
    const row = direction;
    const drawWidth = 38;
    const drawHeight = 57;
    context.drawImage(image, column * 32, row * 48, 32, 48, x - drawWidth / 2, y - drawHeight + 8, drawWidth, drawHeight);
    drawCozyAccessory(context, role, x, y, direction);
  } else {
    context.fillStyle = "#3A241F";
    context.fillRect(x - 8, y - 34, 16, 15);
    context.fillStyle = "#D99A75";
    context.fillRect(x - 6, y - 31, 12, 12);
    context.fillStyle = "#4F7A62";
    context.fillRect(x - 9, y - 19, 18, 20);
    drawCozyAccessory(context, role, x, y, direction);
  }
}

function drawIndustrialAgent(
  context: CanvasRenderingContext2D,
  image: HTMLImageElement | null,
  roleIndex: number,
  x: number,
  y: number,
  time: number,
): void {
  const index = clamp(roleIndex, 0, 5);
  const sourceX = (index % 3) * 32;
  const sourceY = Math.floor(index / 3) * 32;
  const bob = Math.round(Math.sin(time / 260 + index) * 2);
  if (image) {
    context.drawImage(image, sourceX, sourceY, 32, 32, x - 21, y - 30 + bob, 42, 42);
  } else {
    const accent = ["#55D6FF", "#FFB347", "#8BE38B", "#B493FF", "#FF6F7F", "#FFD84D"][index];
    context.fillStyle = "#151A20";
    context.fillRect(x - 17, y - 25 + bob, 34, 28);
    context.fillStyle = "#59636A";
    context.fillRect(x - 13, y - 22 + bob, 26, 22);
    context.fillStyle = accent;
    context.fillRect(x - 5, y - 17 + bob, 10, 10);
  }
}

function drawAgentLabel(context: CanvasRenderingContext2D, agent: PixelAgent, x: number, y: number): void {
  const compact = agent.name.length > 18 ? `${agent.name.slice(0, 17)}…` : agent.name;
  drawPixelText(context, compact, x, y + 23, {
    size: 9,
    align: "center",
    color: "#F7EDD9",
    background: "rgba(24,20,18,.82)",
  });
}

function drawCanvasHud(
  context: CanvasRenderingContext2D,
  level: SpatialSemanticLevel,
  artMode: SpatialAgentArtMode,
  locale: PixelLocale,
  selected: ResearchDistrictSemanticObject | undefined,
): void {
  const copy = RESEARCH_DISTRICT_LEVEL_COPY[level];
  context.fillStyle = "rgba(22,19,18,.82)";
  context.fillRect(16, 16, 330, 54);
  context.fillStyle = artMode === "cozy" ? "#D99A57" : "#63B9CF";
  context.fillRect(16, 16, 7, 54);
  drawPixelText(context, `L${level} · ${localizedSpatialText(copy.label, locale)}`, 34, 34, { size: 13 });
  drawPixelText(context, `${copy.queryScope} / ${copy.interactionDepth}`, 34, 56, { size: 9, color: "#C9BFAE" });

  if (selected) {
    const label = localizedSpatialText(selected.label, locale);
    context.font = "600 10px ui-monospace, SFMono-Regular, Menlo, monospace";
    const width = Math.min(340, context.measureText(label).width + 26);
    context.fillStyle = "rgba(22,19,18,.82)";
    context.fillRect(LOGICAL_WIDTH - width - 16, 16, width, 34);
    context.fillStyle = AUTHORITY_COLORS[selected.authorityKind];
    context.fillRect(LOGICAL_WIDTH - width - 16, 16, 7, 34);
    drawPixelText(context, label, LOGICAL_WIDTH - width, 33, { size: 10 });
  }
}

export function AdvancedSpatialSurface({
  agents,
  metrics,
  level,
  artMode,
  locale,
  selectedObjectId,
  onSelectObject,
  onOpenRoute,
}: AdvancedSpatialSurfaceProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const animationFrameRef = useRef<number | null>(null);
  const images = useSpatialImages();
  const [hoveredObjectId, setHoveredObjectId] = useState<string | null>(null);
  const objects = RESEARCH_DISTRICT_OBJECTS_BY_LEVEL[level];
  const selectedObject = objects.find((object) => object.id === selectedObjectId);
  const agentPaths = useMemo(() => buildAgentPaths(agents, objects), [agents, objects]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return undefined;
    const context = canvas.getContext("2d");
    if (!context) return undefined;

    const dpr = clamp(window.devicePixelRatio || 1, 1, 2);
    canvas.width = Math.round(LOGICAL_WIDTH * dpr);
    canvas.height = Math.round(LOGICAL_HEIGHT * dpr);
    context.imageSmoothingEnabled = false;

    const render = (time: number) => {
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT);
      if (level <= 1) drawOutdoorGround(context, level, artMode === "industrial");
      else drawInteriorGround(context, level, artMode === "industrial");

      for (const object of objects) {
        drawSemanticObject(
          context,
          object,
          metrics,
          object.id === selectedObjectId,
          object.id === hoveredObjectId,
          artMode,
          time,
        );
      }

      const sortedAgents = agentPaths
        .map((projection, index) => {
          const speed = 0.018 + (hashText(projection.agent.id) % 9) / 1000;
          const cycle = ((time / 1000) * speed + index * 0.13) % 2;
          const progress = cycle <= 1 ? cycle : 2 - cycle;
          const position = interpolateSpatialPath(projection.path, progress);
          const next = interpolateSpatialPath(projection.path, clamp(progress + 0.015, 0, 1));
          return { ...projection, position, next, progress, index };
        })
        .sort((a, b) => a.position.y - b.position.y);

      for (const projection of sortedAgents) {
        let x = (projection.position.x / 100) * LOGICAL_WIDTH;
        const y = (projection.position.y / 100) * LOGICAL_HEIGHT;
        const normalizedStatus = projection.agent.status.toLowerCase();
        if (/(failed|error|blocked)/.test(normalizedStatus)) {
          x += Math.sin(time / 45 + projection.index) * 1.5;
        }
        const dx = projection.next.x - projection.position.x;
        const dy = projection.next.y - projection.position.y;
        const direction = Math.abs(dx) > Math.abs(dy) ? (dx < 0 ? 1 : 2) : (dy < 0 ? 3 : 0);
        const phase = Math.floor((time / 180 + projection.index) % 4);

        drawAgentGroundState(context, projection.agent, x, y, time);
        if (artMode === "cozy") {
          drawCozyAgent(context, images.cozy, projection.agent, x, y, direction, phase);
        } else {
          drawIndustrialAgent(context, images.industrial, projection.roleIndex, x, y, time);
        }
        if (level >= 1) drawAgentLabel(context, projection.agent, x, y);
      }

      drawCanvasHud(context, level, artMode, locale, selectedObject);
      animationFrameRef.current = window.requestAnimationFrame(render);
    };

    animationFrameRef.current = window.requestAnimationFrame(render);
    return () => {
      if (animationFrameRef.current !== null) window.cancelAnimationFrame(animationFrameRef.current);
    };
  }, [agentPaths, artMode, hoveredObjectId, images.cozy, images.industrial, level, locale, metrics, objects, selectedObject, selectedObjectId]);

  const objectAtPointer = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    return [...objects].reverse().find((object) => (
      x >= object.bounds.x
      && x <= object.bounds.x + object.bounds.w
      && y >= object.bounds.y
      && y <= object.bounds.y + object.bounds.h
    ));
  };

  return (
    <div
      className="relative overflow-hidden rounded-lg"
      style={{
        background: artMode === "cozy" ? "#201A18" : "#11161B",
        border: "1px solid rgba(255,255,255,.13)",
        boxShadow: "0 18px 60px rgba(0,0,0,.28)",
      }}
      data-testid="advanced-spatial-surface"
      data-spatial-level={level}
      data-spatial-art-mode={artMode}
      data-spatial-ready={images.cozy && images.industrial ? "true" : "loading"}
    >
      <canvas
        ref={canvasRef}
        className="block h-auto w-full cursor-crosshair touch-none"
        style={{ aspectRatio: `${LOGICAL_WIDTH} / ${LOGICAL_HEIGHT}`, imageRendering: "pixelated" }}
        aria-label={locale === "zh" ? "可交互的研究城区语义地图" : "Interactive Research District semantic map"}
        onPointerMove={(event) => setHoveredObjectId(objectAtPointer(event)?.id || null)}
        onPointerLeave={() => setHoveredObjectId(null)}
        onClick={(event) => {
          const object = objectAtPointer(event);
          if (object) onSelectObject(object);
        }}
        onDoubleClick={(event) => {
          const object = objectAtPointer(event);
          if (object) onOpenRoute(object.formalRoute);
        }}
      />
      <div className="pointer-events-none absolute bottom-2 left-2 rounded px-2 py-1 text-[9px]" style={{ background: "rgba(20,17,16,.76)", color: "#D7CCBA" }}>
        {locale === "zh" ? "单击检查 · 双击打开正式 MIS 页面" : "Click to inspect · double-click to open the formal MIS page"}
      </div>
      <div className="sr-only" aria-live="polite">
        {selectedObject
          ? `${localizedSpatialText(selectedObject.label, locale)}: ${spatialMetricValue(selectedObject, metrics)} ${localizedSpatialText(selectedObject.metricLabel, locale)}`
          : localizedSpatialText(RESEARCH_DISTRICT_LEVEL_COPY[level].label, locale)}
      </div>
    </div>
  );
}
