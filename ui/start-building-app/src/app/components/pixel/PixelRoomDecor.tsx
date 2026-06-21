import type { CSSProperties } from "react";
import type { PixelZoneDefinition } from "./pixelModel";

interface PixelRoomDecorProps {
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

function CommonRoomFrame({ zone }: PixelRoomDecorProps) {
  const floor = zone.tone === "danger" ? "#3b2026" : zone.tone === "warning" ? "#45351f" : zone.tone === "purple" ? "#2c2742" : zone.tone === "dock" ? "#173947" : "#263341";

  return (
    <>
      <div
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundColor: floor,
          backgroundImage:
            "linear-gradient(90deg, rgba(255,255,255,.045) 1px, transparent 1px), linear-gradient(rgba(2,6,23,.18) 1px, transparent 1px)",
          backgroundSize: "16px 16px",
          imageRendering: "pixelated",
        }}
      />
      <Block x={0} y={0} w={100} h={8} color="#111827" border="#020617" shadow="0 4px 0 rgba(2,6,23,.3)" />
      <Block x={0} y={8} w={4} h={92} color="#1e293b" border="#020617" />
    </>
  );
}

export function PixelRoomDecor({ zone }: PixelRoomDecorProps) {
  let decor: JSX.Element | null = null;

  switch (zone.id) {
    case "control_tower":
      decor = (
        <>
          <Desk x={34} y={51} w={38} />
          <Monitor x={30} y={31} />
          <Monitor x={45} y={27} />
          <Monitor x={60} y={31} />
          <Block x={15} y={20} w={10} h={10} color="#a855f7" border="#312e81" shadow="0 0 10px rgba(168,85,247,.55)" />
          <Plant x={76} y={54} />
        </>
      );
      break;
    case "agent_lobby":
      decor = (
        <>
          <Desk x={25} y={48} w={48} />
          <Block x={34} y={39} w={30} h={8} color="#d8b384" border="#5f4634" />
          <Plant x={6} y={55} />
          <Plant x={81} y={55} />
          <Block x={9} y={20} w={21} h={12} color="#475569" />
          <Block x={70} y={20} w={21} h={12} color="#475569" />
        </>
      );
      break;
    case "task_hall":
      decor = (
        <>
          <Block x={10} y={16} w={80} h={24} color="#0f172a" border="#64748b" shadow="0 0 10px rgba(34,211,238,.14)" />
          {[0, 1, 2, 3].map((column) => (
            <Block key={column} x={15 + column * 19} y={21} w={13} h={13} color={["#38bdf8", "#fbbf24", "#a78bfa", "#34d399"][column]} border="#020617" opacity={0.78} />
          ))}
          <Desk x={12} y={60} w={30} />
          <Desk x={58} y={60} w={30} />
        </>
      );
      break;
    case "run_stream":
      decor = (
        <>
          <ServerRack x={8} y={25} />
          <ServerRack x={27} y={25} />
          <ServerRack x={80} y={25} />
          <Block x={45} y={18} w={24} h={45} color="rgba(34,211,238,.08)" border="rgba(34,211,238,.38)" shadow="0 0 12px rgba(34,211,238,.2)" />
          {[0, 1, 2].map((row) => (
            <Block key={row} x={49} y={26 + row * 11} w={16} h={4} color="#22d3ee" border="transparent" opacity={0.65 - row * 0.1} />
          ))}
        </>
      );
      break;
    case "runtime_lab":
      decor = (
        <>
          <ServerRack x={8} y={25} />
          <ServerRack x={24} y={25} />
          <Desk x={50} y={58} w={38} />
          <Monitor x={57} y={38} />
          <Monitor x={73} y={38} />
        </>
      );
      break;
    case "tool_workshop":
      decor = (
        <>
          <Desk x={13} y={55} w={72} />
          {[0, 1, 2, 3].map((index) => (
            <Block key={index} x={18 + index * 17} y={43 - (index % 2) * 4} w={7} h={7} color={["#60a5fa", "#f59e0b", "#a78bfa", "#34d399"][index]} border="#020617" shadow="0 0 6px rgba(255,255,255,.12)" />
          ))}
          <Block x={8} y={17} w={84} h={8} color="#334155" border="#0f172a" />
        </>
      );
      break;
    case "approval_gate":
      decor = (
        <>
          <Block x={46} y={15} w={8} h={64} color="#111827" border="#020617" />
          <Block x={19} y={43} w={62} h={8} color="#fbbf24" border="#78350f" rotate={-2} shadow="0 0 10px rgba(251,191,36,.35)" />
          <Block x={12} y={63} w={18} h={15} color="#7c2d12" border="#431407" />
          <Block x={70} y={63} w={18} h={15} color="#7c2d12" border="#431407" />
          <Block x={8} y={20} w={12} h={12} color="#fbbf24" border="#78350f" shadow="0 0 12px rgba(251,191,36,.55)" />
        </>
      );
      break;
    case "evaluation_room":
      decor = (
        <>
          <Block x={12} y={18} w={76} h={20} color="#0f172a" border="#64748b" />
          <Block x={18} y={24} w={42} h={5} color="#34d399" border="transparent" />
          <Block x={18} y={31} w={58} h={3} color="#fbbf24" border="transparent" opacity={0.75} />
          <Desk x={25} y={58} w={50} />
          <Block x={14} y={52} w={8} h={20} color="#475569" />
          <Block x={78} y={52} w={8} h={20} color="#475569" />
        </>
      );
      break;
    case "memory_archive":
      decor = (
        <>
          <Shelf x={7} y={22} />
          <Shelf x={27} y={22} />
          <Shelf x={76} y={22} />
          <Desk x={48} y={59} w={23} />
          <Plant x={50} y={24} />
        </>
      );
      break;
    case "external_base_dock":
      decor = (
        <>
          <Block x={8} y={55} w={84} h={12} color="#0f172a" border="#0891b2" />
          {[0, 1, 2].map((index) => (
            <Block key={index} x={16 + index * 27} y={34 - index * 3} w={18} h={18} color="#8b5e3c" border="#3f2a1d" shadow="3px 3px 0 rgba(2,6,23,.32)" />
          ))}
          <Block x={82} y={20} w={7} h={30} color="#22d3ee" border="#164e63" shadow="0 0 10px rgba(34,211,238,.45)" />
        </>
      );
      break;
    case "audit_vault":
      decor = (
        <>
          <Block x={27} y={17} w={46} h={57} color="#1e293b" border="#94a3b8" shadow="0 0 12px rgba(148,163,184,.2)" />
          <Block x={34} y={25} w={32} h={40} color="#0f172a" border="#64748b" radius={50} />
          <Block x={47} y={38} w={7} h={14} color="#94a3b8" border="#334155" />
          <Block x={40} y={44} w={21} h={4} color="#94a3b8" border="#334155" />
        </>
      );
      break;
    case "incident_corner":
      decor = (
        <>
          <ServerRack x={11} y={25} warning />
          <Block x={38} y={18} w={48} h={8} color="#f87171" border="#7f1d1d" shadow="0 0 10px rgba(248,113,113,.55)" />
          {[0, 1, 2].map((index) => (
            <Block key={index} x={40 + index * 16} y={50 + (index % 2) * 8} w={10} h={10} color={index === 1 ? "#fbbf24" : "#7f1d1d"} border="#450a0a" rotate={45} />
          ))}
        </>
      );
      break;
    case "template_market":
      decor = (
        <>
          {[0, 1, 2].map((index) => (
            <span key={index}>
              <Block x={10 + index * 30} y={28} w={22} h={34} color={["#164e63", "#4c1d95", "#14532d"][index]} border="#020617" shadow="3px 3px 0 rgba(2,6,23,.3)" />
              <Block x={14 + index * 30} y={35} w={14} h={7} color={["#22d3ee", "#a78bfa", "#34d399"][index]} border="transparent" />
              <Block x={17 + index * 30} y={48} w={8} h={8} color="#e2e8f0" border="#334155" />
            </span>
          ))}
        </>
      );
      break;
    default:
      decor = null;
  }

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <CommonRoomFrame zone={zone} />
      {decor}
    </div>
  );
}
