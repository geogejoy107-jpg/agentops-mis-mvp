import type { CSSProperties } from "react";
import type { PixelTone, PixelZoneDefinition } from "./pixelModel";
import type { PixelMaterialRef, PixelRoomProp } from "./pixelOfficeScene";
import { PIXEL_ROOM_SCENES } from "./pixelOfficeScene";
import type { PixelOfficeTheme } from "./pixelOfficeTheme";

interface RectProps {
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  border: string;
  shadow?: string;
  rotate?: number;
  opacity?: number;
  radius?: string;
}

function resolveMaterial(reference: PixelMaterialRef, theme: PixelOfficeTheme): string {
  if (reference.startsWith("tone:")) {
    const tone = reference.slice(5) as PixelTone;
    return theme.tones[tone].light;
  }
  return theme.materials[reference];
}

function Rect({ x, y, w, h, color, border, shadow, rotate = 0, opacity = 1, radius = "0" }: RectProps) {
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

function Primitive({ prop, theme }: { prop: PixelRoomProp; theme: PixelOfficeTheme }) {
  const outline = theme.materials.outline;

  if (prop.kind === "block") {
    const color = resolveMaterial(prop.material, theme);
    const border = resolveMaterial(prop.borderMaterial || "outline", theme);
    return <Rect {...prop} color={color} border={border} shadow={prop.glow ? `0 0 10px ${color}` : undefined} />;
  }

  if (prop.kind === "desk") {
    const w = prop.w || 28;
    return (
      <>
        <Rect x={prop.x} y={prop.y} w={w} h={10} color={theme.materials.wood} border={theme.materials.woodDark} shadow={`0 3px 0 ${theme.frame.insetBorder}`} />
        <Rect x={prop.x + 3} y={prop.y + 10} w={4} h={10} color={theme.materials.woodDark} border={outline} />
        <Rect x={prop.x + w - 7} y={prop.y + 10} w={4} h={10} color={theme.materials.woodDark} border={outline} />
      </>
    );
  }

  if (prop.kind === "monitor") {
    const screen = prop.active === false ? theme.materials.monitorIdle : theme.materials.monitorActive;
    return (
      <>
        <Rect x={prop.x} y={prop.y} w={12} h={13} color={theme.materials.monitorFrame} border={outline} />
        <Rect
          x={prop.x + 2}
          y={prop.y + 2}
          w={8}
          h={7}
          color={screen}
          border={theme.frame.insetBorder}
          shadow={prop.active === false ? undefined : `0 0 8px ${screen}`}
        />
        <Rect x={prop.x + 5} y={prop.y + 13} w={2} h={4} color={theme.materials.wallHighlight} border={outline} />
      </>
    );
  }

  if (prop.kind === "serverRack") {
    return (
      <>
        <Rect x={prop.x} y={prop.y} w={12} h={34} color={theme.materials.rack} border={outline} shadow={`3px 3px 0 ${theme.frame.insetBorder}`} />
        {[0, 1, 2, 3].map((row) => {
          const light = prop.warning && row === 1 ? theme.materials.danger : theme.materials.healthy;
          return (
            <span key={row}>
              <Rect x={prop.x + 2} y={prop.y + 4 + row * 7} w={8} h={4} color={theme.materials.rackPanel} border={theme.materials.wallHighlight} />
              <Rect x={prop.x + 3} y={prop.y + 5 + row * 7} w={1.5} h={1.7} color={light} border="transparent" />
            </span>
          );
        })}
      </>
    );
  }

  if (prop.kind === "shelf") {
    const w = prop.w || 17;
    return (
      <>
        <Rect x={prop.x} y={prop.y} w={w} h={38} color={theme.materials.shelf} border={theme.materials.woodDark} />
        {[0, 1, 2].map((row) => (
          <Rect
            key={row}
            x={prop.x + 2}
            y={prop.y + 4 + row * 11}
            w={w - 4}
            h={7}
            color={row === 1 ? theme.tones.dock.floor : theme.materials.shelfInset}
            border={theme.materials.woodDark}
          />
        ))}
      </>
    );
  }

  return (
    <>
      <Rect x={prop.x + 3} y={prop.y + 12} w={7} h={8} color={theme.materials.plantPot} border={theme.materials.woodDark} />
      <Rect x={prop.x} y={prop.y + 2} w={7} h={7} color={theme.materials.plantLeaf} border={outline} rotate={-12} />
      <Rect x={prop.x + 7} y={prop.y} w={7} h={7} color={theme.materials.plantLeafAlt} border={outline} rotate={12} />
    </>
  );
}

export function PixelRoomSceneRenderer({ zone, theme }: { zone: PixelZoneDefinition; theme: PixelOfficeTheme }) {
  const scene = PIXEL_ROOM_SCENES[zone.id];
  const floor = scene.floorMaterial ? resolveMaterial(scene.floorMaterial, theme) : theme.tones[zone.tone].floor;

  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden="true">
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: floor,
          backgroundImage: `linear-gradient(90deg, ${theme.frame.grid} 1px, transparent 1px), linear-gradient(${theme.frame.insetBorder} 1px, transparent 1px)`,
          backgroundSize: "16px 16px",
          imageRendering: "pixelated",
        }}
      />
      <Rect x={0} y={0} w={100} h={8} color={theme.materials.wall} border={theme.materials.outline} shadow={`0 4px 0 ${theme.frame.insetBorder}`} />
      {scene.props.map((prop, index) => (
        <Primitive key={`${zone.id}-${index}`} prop={prop} theme={theme} />
      ))}
    </div>
  );
}