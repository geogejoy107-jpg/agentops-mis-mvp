import type { CSSProperties } from "react";
import type { PixelOfficeTheme } from "./pixelOfficeTheme";

interface PathProps {
  x: number;
  y: number;
  w: number;
  h: number;
  theme: PixelOfficeTheme;
  vertical?: boolean;
}

function Path({ x, y, w, h, theme, vertical = false }: PathProps) {
  const style: CSSProperties = {
    left: `${x}%`,
    top: `${y}%`,
    width: `${w}%`,
    height: `${h}%`,
    backgroundColor: theme.frame.path,
    backgroundImage: vertical
      ? `linear-gradient(90deg, ${theme.frame.pathGrid} 1px, transparent 1px)`
      : `linear-gradient(${theme.frame.pathGrid} 1px, transparent 1px)`,
    backgroundSize: "12px 12px",
    border: `2px solid ${theme.frame.pathBorder}`,
    boxShadow: `inset 0 0 0 2px ${theme.frame.grid}, 0 3px 0 ${theme.frame.insetBorder}`,
    imageRendering: "pixelated",
  };

  return <span className="absolute" style={style} />;
}

function Lamp({ x, y, color, theme }: { x: number; y: number; color: string; theme: PixelOfficeTheme }) {
  return (
    <span className="absolute" style={{ left: `${x}%`, top: `${y}%`, width: 12, height: 20 }}>
      <span className="absolute left-[5px] top-[6px] h-[14px] w-[2px]" style={{ background: theme.materials.wallHighlight }} />
      <span
        className="absolute left-[2px] top-0 h-[7px] w-[8px]"
        style={{ background: color, border: `1px solid ${theme.materials.outline}`, boxShadow: `0 0 10px ${color}` }}
      />
    </span>
  );
}

export function PixelCampusBackdrop({ theme }: { theme: PixelOfficeTheme }) {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: theme.frame.canvas,
          backgroundImage: `linear-gradient(90deg, ${theme.frame.grid} 1px, transparent 1px), linear-gradient(${theme.frame.insetBorder} 1px, transparent 1px)`,
          backgroundSize: "16px 16px",
          imageRendering: "pixelated",
        }}
      />
      <div className="absolute left-[1.5%] top-[2%] h-[94%] w-[97%]" style={{ border: `4px solid ${theme.materials.outline}` }} />
      <div className="absolute left-[2.2%] top-[2.8%] h-[92.4%] w-[95.6%]" style={{ border: `1px solid ${theme.frame.insetBorder}` }} />

      <Path x={2} y={20} w={96} h={5} theme={theme} />
      <Path x={2} y={47} w={96} h={5} theme={theme} />
      <Path x={2} y={74} w={96} h={5} theme={theme} />
      <Path x={29} y={20} w={4} h={59} theme={theme} vertical />
      <Path x={54.8} y={20} w={4} h={59} theme={theme} vertical />
      <Path x={76.8} y={20} w={4} h={59} theme={theme} vertical />

      <div
        className="absolute left-[2.5%] top-[80.5%] h-[12%] w-[31%]"
        style={{
          backgroundColor: theme.frame.garden,
          backgroundImage: `radial-gradient(circle, ${theme.frame.gardenPattern} 1px, transparent 2px)`,
          backgroundSize: "12px 12px",
          border: `2px solid ${theme.materials.outline}`,
        }}
      />
      <div
        className="absolute left-[66%] top-[80.5%] h-[12%] w-[31%]"
        style={{ background: theme.frame.loading, border: `2px solid ${theme.materials.outline}` }}
      />

      <Lamp x={23} y={21.4} color={theme.frame.glowA} theme={theme} />
      <Lamp x={51} y={48.4} color={theme.frame.glowB} theme={theme} />
      <Lamp x={73} y={75.2} color={theme.materials.warning} theme={theme} />
      <Lamp x={91} y={48.4} color={theme.frame.glowA} theme={theme} />
    </div>
  );
}