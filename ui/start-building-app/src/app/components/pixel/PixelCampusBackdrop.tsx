import type { CSSProperties } from "react";

interface PathProps {
  x: number;
  y: number;
  w: number;
  h: number;
  vertical?: boolean;
}

function Path({ x, y, w, h, vertical = false }: PathProps) {
  const style: CSSProperties = {
    left: `${x}%`,
    top: `${y}%`,
    width: `${w}%`,
    height: `${h}%`,
    backgroundColor: "#394554",
    backgroundImage: vertical
      ? "linear-gradient(90deg,rgba(255,255,255,.05) 1px,transparent 1px)"
      : "linear-gradient(rgba(255,255,255,.05) 1px,transparent 1px)",
    backgroundSize: "12px 12px",
    border: "2px solid rgba(2,6,23,.68)",
    boxShadow: "inset 0 0 0 2px rgba(148,163,184,.05),0 3px 0 rgba(2,6,23,.24)",
    imageRendering: "pixelated",
  };
  return <span className="absolute" style={style} />;
}

function Lamp({ x, y, color }: { x: number; y: number; color: string }) {
  return (
    <span className="absolute" style={{ left: `${x}%`, top: `${y}%`, width: 12, height: 20 }}>
      <span className="absolute left-[5px] top-[6px] h-[14px] w-[2px] bg-slate-700" />
      <span className="absolute left-[2px] top-0 h-[7px] w-[8px] border border-slate-950" style={{ background: color, boxShadow: `0 0 10px ${color}` }} />
    </span>
  );
}

export function PixelCampusBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div className="absolute inset-0" style={{ backgroundColor: "#17212b", backgroundImage: "linear-gradient(90deg,rgba(148,163,184,.035) 1px,transparent 1px),linear-gradient(rgba(2,6,23,.22) 1px,transparent 1px)", backgroundSize: "16px 16px", imageRendering: "pixelated" }} />
      <div className="absolute left-[1.5%] top-[2%] h-[94%] w-[97%] border-4 border-slate-950/80" />
      <div className="absolute left-[2.2%] top-[2.8%] h-[92.4%] w-[95.6%] border border-slate-500/10" />
      <Path x={2} y={20} w={96} h={5} />
      <Path x={2} y={47} w={96} h={5} />
      <Path x={2} y={74} w={96} h={5} />
      <Path x={29} y={20} w={4} h={59} vertical />
      <Path x={54.8} y={20} w={4} h={59} vertical />
      <Path x={76.8} y={20} w={4} h={59} vertical />
      <div className="absolute left-[2.5%] top-[80.5%] h-[12%] w-[31%] border-2 border-emerald-950" style={{ backgroundColor: "#193229", backgroundImage: "radial-gradient(circle,rgba(74,222,128,.18) 1px,transparent 2px)", backgroundSize: "12px 12px" }} />
      <div className="absolute left-[66%] top-[80.5%] h-[12%] w-[31%] border-2 border-amber-950/50" style={{ background: "repeating-linear-gradient(135deg,rgba(251,191,36,.13) 0 6px,rgba(15,23,42,.32) 6px 12px)" }} />
      <Lamp x={23} y={21.4} color="#22d3ee" />
      <Lamp x={51} y={48.4} color="#a78bfa" />
      <Lamp x={73} y={75.2} color="#fbbf24" />
      <Lamp x={91} y={48.4} color="#22d3ee" />
    </div>
  );
}
