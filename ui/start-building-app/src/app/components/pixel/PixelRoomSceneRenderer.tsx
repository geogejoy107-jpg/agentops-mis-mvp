import type { CSSProperties, ReactNode } from "react";
import type { PixelZoneDefinition } from "./pixelModel";
import type { PixelRoomProp } from "./pixelRoomScene";
import { PIXEL_ROOM_SCENES } from "./pixelRoomScene";

interface PixelRoomSceneRendererProps {
  zone: PixelZoneDefinition;
}

interface BlockProps {
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  border?: string;
  shadow?: string;
  rotate?: number;
  opacity?: number;
  radius?: number;
}

function Block({ x, y, w, h, color, border = "rgba(2,6,23,.72)", shadow, rotate = 0, opacity = 1, radius = 0 }: BlockProps) {
  const style: CSSProperties = {
    left: `${x}%`,
    top: `${y}%`,
    width: `${w}%`,
    height: `${h}%`,
    background: color,
    border: `1px solid ${border}`,
    boxShadow: shadow,
    transform: `rotate(${rotate}deg)`,
    opacity,
    borderRadius: radius,
    imageRendering: "pixelated",
  };

  return <span className="pointer-events-none absolute" style={style} />;
}

function Monitor({ x, y, active = true }: { x: number; y: number; active?: boolean }) {
  return (
    <>
      <Block x={x} y={y} w={12} h={13} color="#0b1020" border="#020617" shadow="0 2px 0 rgba(2,6,23,.55)" />
      <Block x={x + 2} y={y + 2} w={8} h={7} color={active ? "#22d3ee" : "#334155"} border="rgba(255,255,255,.08)" shadow={active ? "0 0 8px rgba(34,211,238,.55)" : undefined} />
      <Block x={x + 5} y={y + 13} w={2} h={4} color="#475569" />
    </>
  );
}

function Desk({ x, y, w = 28 }: { x: number; y: number; w?: number }) {
  return (
    <>
      <Block x={x} y={y} w={w} h={10} color="#8b5e3c" border="#3f2a1d" shadow="0 3px 0 rgba(2,6,23,.34)" />
      <Block x={x + 3} y={y + 10} w={4} h={10} color="#4b3427" />
      <Block x={x + w - 7} y={y + 10} w={4} h={10} color="#4b3427" />
    </>
  );
}

function ServerRack({ x, y, warning = false }: { x: number; y: number; warning?: boolean }) {
  return (
    <>
      <Block x={x} y={y} w={12} h={34} color="#111827" border="#020617" shadow="3px 3px 0 rgba(2,6,23,.36)" />
      {[0, 1, 2, 3].map((row) => (
        <span key={row}>
          <Block x={x + 2} y={y + 4 + row * 7} w={8} h={4} color="#1e293b" border="#334155" />
          <Block x={x + 3} y={y + 5 + row * 7} w={1.5} h={1.7} color={warning && row === 1 ? "#f87171" : "#34d399"} border="transparent" shadow={warning && row === 1 ? "0 0 6px #f87171" : "0 0 5px #34d399"} />
        </span>
      ))}
    </>
  );
}

function Shelf({ x, y, w = 17 }: { x: number; y: number; w?: number }) {
  return (
    <>
      <Block x={x} y={y} w={w} h={38} color="#5f4634" border="#2d2018" shadow="3px 3px 0 rgba(2,6,23,.28)" />
      {[0, 1, 2].map((row) => (
        <span key={row}>
          <Block x={x + 2} y={y + 4 + row * 11} w={w - 4} h={7} color="#281d18" border="#3f2a1d" />
          <Block x={x + 3} y={y + 5 + row * 11} w={2} h={5} color={row === 1 ? "#22d3ee" : "#f59e0b"} border="transparent" />
          <Block x={x + 6} y={y + 5 + row * 11} w={2} h={5} color={row === 2 ? "#a855f7" : "#60a5fa"} border="transparent" />
          <Block x={x + 9} y={y + 5 + row * 11} w={3} h={5} color="#94a3b8" border="transparent" />
        </span>
      ))}
    </>
  );
}

function Plant({ x, y }: { x: number; y: number }) {
  return (
    <>
      <Block x={x + 3} y={y + 12} w={7} h={8} color="#9a5a38" border="#4c2f20" />
      <Block x={x + 5} y={y + 5} w={3} h={9} color="#166534" border="transparent" />
      <Block x={x} y={y + 2} w={7} h={7} color="#22c55e" border="#14532d" rotate={-12} />
      <Block x={x + 7} y={y} w={7} h={7} color="#4ade80" border="#14532d" rotate={12} />
    </>
  );
}

function renderProp(prop: PixelRoomProp, key: number): ReactNode {
  if (prop.kind === "block") return <Block key={key} {...prop} />;
  if (prop.kind === "desk") return <Desk key={key} x={prop.x} y={prop.y} w={prop.w} />;
  if (prop.kind === "monitor") return <Monitor key={key} x={prop.x} y={prop.y} active={prop.active} />;
  if (prop.kind === "serverRack") return <ServerRack key={key} x={prop.x} y={prop.y} warning={prop.warning} />;
  if (prop.kind === "shelf") return <Shelf key={key} x={prop.x} y={prop.y} w={prop.w} />;
  if (prop.kind === "plant") return <Plant key={key} x={prop.x} y={prop.y} />;
  return null;
}

function defaultFloor(zone: PixelZoneDefinition) {
  if (zone.tone === "danger") return "#3b2026";
  if (zone.tone === "warning") return "#45351f";
  if (zone.tone === "purple") return "#2c2742";
  if (zone.tone === "dock") return "#173947";
  return "#263341";
}

export function PixelRoomSceneRenderer({ zone }: PixelRoomSceneRendererProps) {
  const scene = PIXEL_ROOM_SCENES[zone.id];
  const floor = scene.floor || defaultFloor(zone);

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: floor,
          backgroundImage: "linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px), linear-gradient(rgba(2,6,23,.18) 1px, transparent 1px)",
          backgroundSize: "16px 16px",
          imageRendering: "pixelated",
        }}
      />
      <Block x={0} y={0} w={100} h={8} color="#111827" border="#020617" shadow="0 4px 0 rgba(2,6,23,.3)" />
      <Block x={0} y={8} w={4} h={92} color="#1e293b" border="#020617" />
      {scene.props.map(renderProp)}
    </div>
  );
}
