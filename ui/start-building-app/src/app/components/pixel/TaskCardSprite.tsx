import type { PixelTaskCard } from "./pixelModel";
import { PIXEL_ZONE_BY_ID } from "./pixelModel";

interface TaskCardSpriteProps {
  task: PixelTaskCard;
  index: number;
  onOpen: (route: string) => void;
}

const riskStyle: Record<PixelTaskCard["risk"], { color: string; bg: string }> = {
  low: { color: "var(--mis-success)", bg: "rgba(42,157,143,0.18)" },
  medium: { color: "#FBBF24", bg: "rgba(251,191,36,0.16)" },
  high: { color: "var(--mis-warning)", bg: "rgba(231,111,81,0.18)" },
  critical: { color: "#F87171", bg: "rgba(248,113,113,0.2)" },
};

export function TaskCardSprite({ task, index, onOpen }: TaskCardSpriteProps) {
  const hall = PIXEL_ZONE_BY_ID.task_hall;
  const col = index % 3;
  const row = Math.floor(index / 3) % 3;
  const style = riskStyle[task.risk] || riskStyle.low;
  const left = hall.x + 2 + col * 7;
  const top = hall.y + 7 + row * 4.6;

  return (
    <button
      type="button"
      className="absolute z-10 text-left transition-transform hover:-translate-y-0.5"
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: "6.3%",
        minWidth: 58,
      }}
      onClick={(event) => {
        event.stopPropagation();
        onOpen(task.route);
      }}
      title={`${task.title} · ${task.status}`}
      aria-label={`Open task ${task.title}`}
    >
      <div
        className="rounded-sm p-1"
        style={{
          background: "rgba(2,6,23,0.72)",
          border: `1px solid ${style.color}`,
          boxShadow: `0 0 10px ${style.bg}`,
          imageRendering: "pixelated",
        }}
      >
        <div className="flex items-center justify-between gap-1">
          <span className="h-1.5 w-1.5 shrink-0" style={{ background: style.color }} />
          <span className="truncate text-[8px] font-mono uppercase" style={{ color: style.color }}>
            {task.status.replace("_", " ")}
          </span>
        </div>
        <div className="mt-1 truncate text-[9px] font-medium leading-tight" style={{ color: "var(--mis-text)" }}>
          {task.title}
        </div>
        <div className="mt-0.5 truncate text-[8px]" style={{ color: "var(--mis-muted)" }}>
          {task.assignedAgent}
        </div>
      </div>
    </button>
  );
}
