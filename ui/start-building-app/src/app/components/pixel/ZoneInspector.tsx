import { ArrowRight, Bot, ExternalLink, MapPin } from "lucide-react";
import { RiskBadge } from "../shared/RiskBadge";
import { StatusBadge } from "../shared/StatusBadge";
import type { PixelAgent, PixelMetrics, PixelTaskCard, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONE_BY_ID } from "./pixelModel";

interface ZoneInspectorProps {
  selectedZone?: PixelZoneDefinition | null;
  hoveredZone?: PixelZoneDefinition | null;
  selectedAgent?: PixelAgent | null;
  metrics: PixelMetrics;
  agents: PixelAgent[];
  taskCards: PixelTaskCard[];
  onOpenRoute: (route: string) => void;
}

export function ZoneInspector({
  selectedZone,
  hoveredZone,
  selectedAgent,
  metrics,
  agents,
  taskCards,
  onOpenRoute,
}: ZoneInspectorProps) {
  const focusZone = selectedAgent ? PIXEL_ZONE_BY_ID[selectedAgent.targetZone] : selectedZone || hoveredZone || PIXEL_ZONE_BY_ID.control_tower;
  const zoneAgents = agents.filter((agent) => agent.targetZone === focusZone.id);
  const zoneTasks = focusZone.id === "task_hall" ? taskCards.slice(0, 5) : [];

  return (
    <aside className="rounded-lg p-4 h-full" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
            <MapPin size={12} />
            Zone Inspector
          </div>
          <h2 className="mt-1 text-base font-semibold" style={{ color: "var(--mis-text)" }}>
            {selectedAgent ? selectedAgent.name : focusZone.label}
          </h2>
          <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {selectedAgent ? selectedAgent.taskTitle || "AI digital employee live position." : focusZone.description}
          </p>
        </div>
        <button
          type="button"
          onClick={() => onOpenRoute(selectedAgent?.routeToDetail || focusZone.route)}
          className="shrink-0 rounded px-2.5 py-1.5 text-[11px] inline-flex items-center gap-1.5"
          style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.25)" }}
        >
          Open
          <ExternalLink size={12} />
        </button>
      </div>

      {selectedAgent && (
        <section className="mt-4 rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(34,211,238,0.14)" }}>
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--mis-text)" }}>
              <Bot size={14} style={{ color: "var(--mis-cyan)" }} />
              Agent state
            </div>
            <RiskBadge risk={selectedAgent.risk} />
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
            <div>
              <div style={{ color: "var(--mis-muted)" }}>Runtime</div>
              <div className="mt-0.5 truncate" style={{ color: "var(--mis-text)" }}>{selectedAgent.runtime}</div>
            </div>
            <div>
              <div style={{ color: "var(--mis-muted)" }}>Status</div>
              <div className="mt-0.5"><StatusBadge status={selectedAgent.status} /></div>
            </div>
            <div>
              <div style={{ color: "var(--mis-muted)" }}>Role</div>
              <div className="mt-0.5 truncate" style={{ color: "var(--mis-text)" }}>{selectedAgent.role}</div>
            </div>
            <div>
              <div style={{ color: "var(--mis-muted)" }}>Target zone</div>
              <div className="mt-0.5 truncate" style={{ color: "var(--mis-text)" }}>{focusZone.label}</div>
            </div>
          </div>
          {selectedAgent.latestRunId && (
            <button
              type="button"
              onClick={() => onOpenRoute(`/admin/runs/${selectedAgent.latestRunId}`)}
              className="mt-3 w-full rounded px-2.5 py-1.5 text-[11px] inline-flex items-center justify-between"
              style={{ background: "rgba(2,6,23,0.45)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.18)" }}
            >
              Latest run {selectedAgent.latestRunId}
              <ArrowRight size={12} />
            </button>
          )}
        </section>
      )}

      <section className="mt-4 grid grid-cols-2 gap-2">
        {[
          { label: "Agents", value: metrics.totalAgents },
          { label: "Runs", value: metrics.totalRuns },
          { label: "Approvals", value: metrics.pendingApprovals },
          { label: "Incidents", value: metrics.failedRuns + metrics.blockedTasks },
        ].map((item) => (
          <div key={item.label} className="rounded p-2" style={{ background: "var(--mis-surface2)" }}>
            <div className="text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
            <div className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{item.value}</div>
          </div>
        ))}
      </section>

      <section className="mt-4">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Agents in this zone</h3>
          <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{zoneAgents.length}</span>
        </div>
        <div className="space-y-2 max-h-48 overflow-auto pr-1">
          {zoneAgents.length === 0 && (
            <p className="rounded p-2 text-[11px]" style={{ color: "var(--mis-muted)", background: "var(--mis-surface2)" }}>
              No agent is currently mapped here. Click another zone or refresh live state.
            </p>
          )}
          {zoneAgents.map((agent) => (
            <button
              key={agent.id}
              type="button"
              onClick={() => onOpenRoute(agent.routeToDetail || "/workspace/agents")}
              className="w-full rounded p-2 text-left hover:opacity-80"
              style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,0.12)" }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[11px] font-medium" style={{ color: "var(--mis-text)" }}>{agent.name}</span>
                <StatusBadge status={agent.status} />
              </div>
              <div className="mt-1 truncate text-[10px]" style={{ color: "var(--mis-muted)" }}>{agent.taskTitle || agent.runtime}</div>
            </button>
          ))}
        </div>
      </section>

      {zoneTasks.length > 0 && (
        <section className="mt-4">
          <h3 className="text-xs font-semibold mb-2" style={{ color: "var(--mis-text)" }}>Task Hall cards</h3>
          <div className="space-y-2">
            {zoneTasks.map((task) => (
              <button
                key={task.id}
                type="button"
                onClick={() => onOpenRoute(task.route)}
                className="w-full rounded p-2 text-left hover:opacity-80"
                style={{ background: "var(--mis-surface2)", border: "1px solid rgba(46,134,171,0.16)" }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px]" style={{ color: "var(--mis-text)" }}>{task.title}</span>
                  <RiskBadge risk={task.risk} />
                </div>
                <div className="mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>{task.group} · {task.assignedAgent}</div>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="mt-4 rounded p-3" style={{ background: "rgba(2,6,23,0.36)", border: "1px solid rgba(148,163,184,0.14)" }}>
        <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>Authority boundary</div>
        <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
          This map only visualizes MIS state. Formal ledgers remain the source of truth for runs, tools, approvals, memory and audit.
        </p>
      </section>
    </aside>
  );
}
