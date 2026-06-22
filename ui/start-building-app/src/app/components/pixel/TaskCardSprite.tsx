import type { PixelLocale, PixelTaskCard } from "./pixelModel";
import { PIXEL_ZONE_BY_ID, statusDisplay } from "./pixelModel";
import type { PixelOfficeTheme } from "./pixelOfficeTheme";

interface TaskCardSpriteProps {
  task: PixelTaskCard;
  index: number;
  onOpen: (route: string) => void;
  theme: PixelOfficeTheme;
  dimmed?: boolean;
  locale?: PixelLocale;
}

const riskTone: Record<PixelTaskCard["risk"], "ready" | "warning" | "danger"> = {
  low: "ready",
  medium: "warning",
  high: "warning",
  critical: "danger",
};

export function TaskCardSprite({ task, index, onOpen, theme, dimmed = false, locale = "en" }: TaskCardSpriteProps) {
  const hall = PIXEL_ZONE_BY_ID.task_hall;
  const col = index % 3;
  const row = Math.floor(index / 3) % 3;
  const tone = theme.tones[riskTone[task.risk] || "ready"];
  const left = hall.x + 2 + col * 7;
  const top = hall.y + 7 + row * 4.6;

  return (
    <button
      type="button"
      className="absolute z-10 text-left transition-all duration-300 hover:-translate-y-0.5"
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: "6.3%",
        minWidth: 58,
        opacity: dimmed ? 0.16 : 1,
        pointerEvents: dimmed ? "none" : "auto",
      }}
      onClick={(event) => {
        event.stopPropagation();
        onOpen(task.route);
      }}
      title={`${task.title} · ${task.status}`}
      aria-label={locale === "zh" ? `打开任务 ${task.title}` : `Open task ${task.title}`}
    >
      <div
        className="rounded-sm p-1"
        style={{
          background: theme.frame.controlBar,
          border: `1px solid ${tone.light}`,
          boxShadow: `0 0 10px ${tone.glow}`,
          imageRendering: "pixelated",
          borderRadius: theme.shape.controlRadius,
        }}
      >
        <div className="flex items-center justify-between gap-1">
          <span className="h-1.5 w-1.5 shrink-0" style={{ background: tone.light }} />
          <span className="truncate text-[8px] font-mono uppercase" style={{ color: tone.light }}>
            {statusDisplay(task.status, locale)}
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