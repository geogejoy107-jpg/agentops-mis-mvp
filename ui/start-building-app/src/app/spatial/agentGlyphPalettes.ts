import type { SpatialAgentPaletteSlot } from "./contracts";

export interface AgentGlyphPalette {
  primary: string;
  secondary: string;
  surface: string;
  outline: string;
  glow: string;
  cloth: string;
  clothShadow: string;
}

const p = (
  primary: string,
  secondary: string,
  surface: string,
  outline: string,
  glow: string,
  cloth: string,
  clothShadow: string,
): AgentGlyphPalette => ({ primary, secondary, surface, outline, glow, cloth, clothShadow });

export const AGENT_GLYPH_PALETTES: Readonly<Record<SpatialAgentPaletteSlot, AgentGlyphPalette>> = {
  azure: p("#38BDF8", "#BAE6FD", "#0C4A6E", "#082F49", "rgba(56,189,248,.55)", "#3B82A0", "#245069"),
  violet: p("#A78BFA", "#DDD6FE", "#4C1D95", "#2E1065", "rgba(167,139,250,.55)", "#7357A4", "#49366F"),
  amber: p("#FBBF24", "#FDE68A", "#78350F", "#451A03", "rgba(251,191,36,.52)", "#B87927", "#754A1C"),
  coral: p("#FB7185", "#FECDD3", "#881337", "#4C0519", "rgba(251,113,133,.52)", "#B95363", "#7B3440"),
  mint: p("#34D399", "#A7F3D0", "#065F46", "#022C22", "rgba(52,211,153,.52)", "#3F9273", "#285E4A"),
  rose: p("#F472B6", "#FBCFE8", "#9D174D", "#500724", "rgba(244,114,182,.52)", "#B64C86", "#773056"),
  indigo: p("#818CF8", "#C7D2FE", "#3730A3", "#1E1B4B", "rgba(129,140,248,.52)", "#5867B0", "#374273"),
  lime: p("#A3E635", "#D9F99D", "#3F6212", "#1A2E05", "rgba(163,230,53,.5)", "#6F9330", "#445C1F"),
  sky: p("#22D3EE", "#A5F3FC", "#155E75", "#083344", "rgba(34,211,238,.55)", "#338CA0", "#245D69"),
  orange: p("#FB923C", "#FED7AA", "#9A3412", "#431407", "rgba(251,146,60,.52)", "#B66A35", "#754425"),
  slate: p("#94A3B8", "#E2E8F0", "#334155", "#0F172A", "rgba(148,163,184,.42)", "#657387", "#404B5C"),
  gold: p("#FACC15", "#FEF08A", "#854D0E", "#422006", "rgba(250,204,21,.52)", "#B88C20", "#735814"),
};
