import type { CSSProperties } from "react";
import type { PixelZoneDefinition } from "./pixelModel";
import type { PixelRoomProp } from "./pixelRoomScene";
import { PIXEL_ROOM_SCENES } from "./pixelRoomScene";

interface Props {
  zone: PixelZoneDefinition;
}

interface RectProps {
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  border?: string;
  shadow?: string;
  rotate?: number;
  opacity?: number;
  radius?: string;
}

function Rect({ x, y, w, h, color, border = "rgba(2,6,23,.72)", shadow, rotate = 0, opacity = 1, radius = "0" }: RectProps) {
  const style: CSSProperties = {
    left: `${x}%`, top: `${y}%`, width: `${w}%`, height: `${h}%`,
    background: color, border: `1px solid ${border}`, boxShadow: shadow,
    transform: `rotate(${rotate}deg)`, opacity, borderRadius: radius,
    imageRendering: "pixelated",
  };
  return <span className="pointer-events-none absolute" style={style} />;
}

function Primitive({ prop }: { prop: PixelRoomProp }) {
  if (prop.kind === "block") return <Rect {...prop} />;
  if (prop.kind === "desk") {
    const w = prop.w || 28;
    return <><Rect x={prop.x} y={prop.y} w={w} h={10} color="#8b5e3c" border="#3f2a1d" shadow="0 3px 0 rgba(2,6,23,.34)" /><Rect x={prop.x + 3} y={prop.y + 10} w={4} h={10} color="#4b3427" /><Rect x={prop.x + w - 7} y={prop.y + 10} w={4} h={10} color="#4b3427" /></>;
  }
  if (prop.kind === "monitor") {
    return <><Rect x={prop.x} y={prop.y} w={12} h={13} color="#0b1020" border="#020617" /><Rect x={prop.x + 2} y={prop.y + 2} w={8} h={7} color={prop.active === false ? "#334155" : "#22d3ee"} border="rgba(255,255,255,.08)" shadow={prop.active === false ? undefined : "0 0 8px rgba(34,211,238,.55)"} /><Rect x={prop.x + 5} y={prop.y + 13} w={2} h={4} color="#475569" /></>;
  }
  if (prop.kind === "serverRack") {
    return <><Rect x={prop.x} y={prop.y} w={12} h={34} color="#111827" border="#020617" shadow="3px 3px 0 rgba(2,6,23,.36)" />{[0,1,2,3].map((row) => <span key={row}><Rect x={prop.x + 2} y={prop.y + 4 + row * 7} w={8} h={4} color="#1e293b" border="#334155" /><Rect x={prop.x + 3} y={prop.y + 5 + row * 7} w={1.5} h={1.7} color={prop.warning && row === 1 ? "#f87171" : "#34d399"} border="transparent" /></span>)}</>;
  }
  if (prop.kind === "shelf") {
    const w = prop.w || 17;
    return <><Rect x={prop.x} y={prop.y} w={w} h={38} color="#5f4634" border="#2d2018" />{[0,1,2].map((row) => <Rect key={row} x={prop.x + 2} y={prop.y + 4 + row * 11} w={w - 4} h={7} color={row === 1 ? "#164e63" : "#281d18"} border="#3f2a1d" />)}</>;
  }
  return <><Rect x={prop.x + 3} y={prop.y + 12} w={7} h={8} color="#9a5a38" border="#4c2f20" /><Rect x={prop.x} y={prop.y + 2} w={7} h={7} color="#22c55e" border="#14532d" rotate={-12} /><Rect x={prop.x + 7} y={prop.y} w={7} h={7} color="#4ade80" border="#14532d" rotate={12} /></>;
}

function floorFor(zone: PixelZoneDefinition) {
  if (zone.tone === "danger") return "#3b2026";
  if (zone.tone === "warning") return "#45351f";
  if (zone.tone === "purple") return "#2c2742";
  if (zone.tone === "dock") return "#173947";
  return "#263341";
}

export function PixelRoomSceneRenderer({ zone }: Props) {
  const scene = PIXEL_ROOM_SCENES[zone.id];
  return <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true"><div className="absolute inset-0" style={{ backgroundColor: scene.floor || floorFor(zone), backgroundImage: "linear-gradient(90deg,rgba(255,255,255,.045) 1px,transparent 1px),linear-gradient(rgba(2,6,23,.18) 1px,transparent 1px)", backgroundSize: "16px 16px", imageRendering: "pixelated" }} /><Rect x={0} y={0} w={100} h={8} color="#111827" border="#020617" shadow="0 4px 0 rgba(2,6,23,.3)" />{scene.props.map((prop, index) => <Primitive key={`${zone.id}-${index}`} prop={prop} />)}</div>;
}
