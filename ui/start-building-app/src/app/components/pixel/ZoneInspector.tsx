import { ArrowRight, ExternalLink, MapPin } from "lucide-react";
import { RiskBadge } from "../shared/RiskBadge";
import { StatusBadge } from "../shared/StatusBadge";
import { AgentGlyphGrammarPreview } from "./AgentGlyphGrammarPreview";
import { AgentGlyphRoster } from "./AgentGlyphRoster";
import { SimpleAgentGlyph } from "./SimpleAgentGlyph";
import type { PixelAgent, PixelLocale, PixelMetrics, PixelTaskCard, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONE_BY_ID, statusDisplay, taskGroupDisplay, zoneDisplay } from "./pixelModel";

interface ZoneInspectorProps {
  selectedZone?: PixelZoneDefinition | null;
  hoveredZone?: PixelZoneDefinition | null;
  selectedAgent?: PixelAgent | null;
  metrics: PixelMetrics;
  agents: PixelAgent[];
  taskCards: PixelTaskCard[];
  onOpenRoute: (route: string) => void;
  locale?: PixelLocale;
}

export function ZoneInspector({
  selectedZone,
  hoveredZone,
  selectedAgent,
  metrics,
  agents,
  taskCards,
  onOpenRoute,
  locale = "en",
}: ZoneInspectorProps) {
  const zh = locale === "zh";
  const focusZone = selectedAgent ? PIXEL_ZONE_BY_ID[selectedAgent.targetZone] : selectedZone || hoveredZone || PIXEL_ZONE_BY_ID.control_tower;
  const focusCopy = zoneDisplay(focusZone, locale);
  const zoneAgents = agents.filter((agent) => agent.targetZone === focusZone.id);
  const zoneTasks = focusZone.id === "task_hall" ? taskCards.slice(0, 5) : [];

  return (
    <aside className="h-full rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
            <MapPin size={12} />
            {zh ? "区域检查器" : "Zone Inspector"}
          </div>
          <h2 className="mt-1 text-base font-semibold" style={{ color: "var(--mis-text)" }}>
            {selectedAgent ? selectedAgent.name : focusCopy.label}
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {selectedAgent ? selectedAgent.taskTitle || (zh ? "AI 数字员工的实时位置。" : "AI digital employee live position.") : focusCopy.description}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onOpenRoute(selectedAgent?.routeToDetail || focusZone.route)}
          className="inline-flex shrink-0 items-center gap-1.5 rounded px-2.5 py-1.5 text-[11px]"
          style={{ background: "rgba(34,211,238,.1)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,.25)" }}
        >
          {zh ? "打开" : "Open"}
          <ExternalLink size={12} />
        </button>
      </div>

      {selectedAgent && (
        <section className="mt-4 rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(34,211,238,.14)" }}>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--mis-text)" }}>
              <SimpleAgentGlyph
                id={selectedAgent.id}
                name={selectedAgent.name}
                role={selectedAgent.role}
                runtime={selectedAgent.runtime}
                size={24}
                status={selectedAgent.status}
                risk={selectedAgent.risk}
                selected
                label={`${selectedAgent.name} · ${selectedAgent.role}`}
              />
              {zh ? "Agent 状态" : "Agent state"}
            </div>
            <RiskBadge risk={selectedAgent.risk} label={zh ? ({ low: "低", medium: "中", high: "高", critical: "严重" }[selectedAgent.risk]) : undefined} />
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
            <div>
              <div style={{ color: "var(--mis-muted)" }}>{zh ? "运行时" : "Runtime"}</div>
              <div className="mt-0.5 truncate" style={{ color: "var(--mis-text)" }}>{selectedAgent.runtime}</div>
            </div>
            <div>
              <div style={{ color: "var(--mis-muted)" }}>{zh ? "状态" : "Status"}</div>
              <div className="mt-0.5"><StatusBadge status={selectedAgent.status} label={statusDisplay(selectedAgent.status, locale)} /></div>
            </div>
            <div>
              <div style={{ color: "var(--mis-muted)" }}>{zh ? "角色" : "Role"}</div>
              <div className="mt-0.5 truncate" style={{ color: "var(--mis-text)" }}>{selectedAgent.role}</div>
            </div>
            <div>
              <div style={{ color: "var(--mis-muted)" }}>{zh ? "目标区域" : "Target zone"}</div>
              <div className="mt-0.5 truncate" style={{ color: "var(--mis-text)" }}>{focusCopy.label}</div>
            </div>
          </div>
          {selectedAgent.latestRunId && (
            <button
              type="button"
              onClick={() => onOpenRoute(`/admin/runs/${selectedAgent.latestRunId}`)}
              className="mt-3 inline-flex w-full items-center justify-between rounded px-2.5 py-1.5 text-[11px]"
              style={{ background: "rgba(2,6,23,.45)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,.18)" }}
            >
              {zh ? "最新运行" : "Latest run"} {selectedAgent.latestRunId}
              <ArrowRight size={12} />
            </button>
          )}
        </section>
      )}

      <section className="mt-4 grid grid-cols-2 gap-2">
        {[
          { label: zh ? "Agent" : "Agents", value: metrics.totalAgents },
          { label: zh ? "运行" : "Runs", value: metrics.totalRuns },
          { label: zh ? "审批" : "Approvals", value: metrics.pendingApprovals },
          { label: zh ? "故障" : "Incidents", value: metrics.failedRuns + metrics.blockedTasks },
        ].map((item) => (
          <div key={item.label} className="rounded p-2" style={{ background: "var(--mis-surface2)" }}>
            <div className="text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
            <div className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{item.value}</div>
          </div>
        ))}
      </section>

      <section className="mt-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? "Agent 身份栏" : "Agent identity rail"}</h3>
          <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
            {zh ? `本区 ${zoneAgents.length} / 全部 ${agents.length}` : `${zoneAgents.length} here / ${agents.length} total`}
          </span>
        </div>
        <AgentGlyphRoster
          agents={agents}
          selectedAgentId={selectedAgent?.id}
          onOpenAgent={(agent) => onOpenRoute(agent.routeToDetail || "/workspace/agents")}
          locale={locale}
        />
        <div className="mt-2">
          <AgentGlyphGrammarPreview locale={locale} />
        </div>
      </section>

      {zoneTasks.length > 0 && (
        <section className="mt-4">
          <h3 className="mb-2 text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? "派活大厅任务卡" : "Task Hall cards"}</h3>
          <div className="space-y-2">
            {zoneTasks.map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => onOpenRoute(task.route)}
                className="w-full rounded p-2 text-left hover:opacity-80"
                style={{ background: "var(--mis-surface2)", border: "1px solid rgba(46,134,171,.16)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px]" style={{ color: "var(--mis-text)" }}>{task.title}</span>
                  <RiskBadge risk={task.risk} label={zh ? ({ low: "低", medium: "中", high: "高", critical: "严重" }[task.risk]) : undefined} />
                </div>
                <div className="mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>{taskGroupDisplay(task.group, locale)} · {task.assignedAgent}</div>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="mt-4 rounded p-3" style={{ background: "rgba(2,6,23,.36)", border: "1px solid rgba(148,163,184,.14)" }}>
        <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{zh ? "权威边界" : "Authority boundary"}</div>
        <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
          {zh ? "地图只负责可视化 MIS 状态。运行、工具、审批、记忆和审计仍以正式账本为准。" : "This map only visualizes MIS state. Formal ledgers remain the source of truth for runs, tools, approvals, memory and audit."}
        </p>
      </section>
    </aside>
  );
}
