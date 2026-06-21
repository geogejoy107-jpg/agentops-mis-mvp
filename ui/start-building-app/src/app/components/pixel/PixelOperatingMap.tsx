import { useMemo, useState } from "react";
import { ArrowRight, Layers3, Route } from "lucide-react";
import { AgentSprite } from "./AgentSprite";
import { PixelCampusBackdrop } from "./PixelCampusBackdrop";
import { PixelZone } from "./PixelZone";
import { TaskCardSprite } from "./TaskCardSprite";
import { ZoneInspector } from "./ZoneInspector";
import type { PixelAgent, PixelMetrics, PixelTaskCard, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONES, PIXEL_ZONE_BY_ID } from "./pixelModel";

interface PixelOperatingMapProps {
  agents: PixelAgent[];
  taskCards: PixelTaskCard[];
  metrics: PixelMetrics;
  onOpenRoute: (route: string) => void;
  compact?: boolean;
}

function zoneAgentsCount(agents: PixelAgent[], zone: PixelZoneDefinition) {
  return agents.filter((agent) => agent.targetZone === zone.id).length;
}

export function PixelOperatingMap({ agents, taskCards, metrics, onOpenRoute, compact = false }: PixelOperatingMapProps) {
  const [selectedZone, setSelectedZone] = useState<PixelZoneDefinition | null>(PIXEL_ZONE_BY_ID.control_tower);
  const [hoveredZone, setHoveredZone] = useState<PixelZoneDefinition | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<PixelAgent | null>(null);

  const busiestZones = useMemo(
    () =>
      PIXEL_ZONES.map((zone) => ({ zone, count: zoneAgentsCount(agents, zone) }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 4),
    [agents],
  );

  const handleSelectZone = (zone: PixelZoneDefinition) => {
    setSelectedAgent(null);
    setSelectedZone(zone);
  };

  const handleSelectAgent = (agent: PixelAgent) => {
    setSelectedAgent(agent);
    setSelectedZone(PIXEL_ZONE_BY_ID[agent.targetZone]);
  };

  return (
    <div className={compact ? "w-full" : "grid grid-cols-12 gap-4"}>
      <style>{`
        @keyframes pixelPacketA {
          0% { transform: translate(8%, 18%); opacity: .05; }
          18% { opacity: .8; }
          50% { transform: translate(52%, 46%); opacity: .9; }
          100% { transform: translate(90%, 72%); opacity: .05; }
        }
        @keyframes pixelPacketB {
          0% { transform: translate(88%, 16%); opacity: .05; }
          22% { opacity: .7; }
          58% { transform: translate(44%, 50%); opacity: .9; }
          100% { transform: translate(12%, 78%); opacity: .05; }
        }
        @keyframes pixelPulse {
          0%, 100% { opacity: .24; }
          50% { opacity: .82; }
        }
        @keyframes pixelAgentIdle {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-1px); }
        }
        @keyframes pixelAgentWork {
          0%, 100% { transform: translateY(0) rotate(-1deg); }
          50% { transform: translateY(-2px) rotate(1deg); }
        }
        @keyframes pixelAgentWait {
          0%, 100% { transform: translateY(0); opacity: .82; }
          50% { transform: translateY(-1px); opacity: 1; }
        }
        @keyframes pixelAgentAlert {
          0%, 100% { transform: translateX(-1px); }
          50% { transform: translateX(1px); }
        }
      `}</style>

      <section className={compact ? "w-full" : "col-span-12 xl:col-span-8"}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div
              className="inline-flex items-center gap-1.5 border px-2 py-1 text-[10px] uppercase tracking-wide"
              style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", borderColor: "rgba(34,211,238,0.22)", boxShadow: "2px 2px 0 rgba(2,6,23,.3)" }}
            >
              <Layers3 size={12} />
              Original Pixel Campus v2
            </div>
            {!compact && (
              <p className="mt-1 text-[11px]" style={{ color: "var(--mis-dim)" }}>
                The map is a live MIS visualizer: rooms, agents and alerts are derived from the same operating data as the formal pages.
              </p>
            )}
          </div>
          {!compact && (
            <div className="flex flex-wrap items-center gap-1.5 text-[10px]" style={{ color: "var(--mis-muted)" }}>
              {busiestZones.map(({ zone, count }) => (
                <button
                  key={zone.id}
                  type="button"
                  onClick={() => handleSelectZone(zone)}
                  className="border px-2 py-1 hover:opacity-80"
                  style={{ background: "var(--mis-surface2)", borderColor: "rgba(148,163,184,0.16)", boxShadow: "2px 2px 0 rgba(2,6,23,.28)" }}
                >
                  {zone.label}: <span style={{ color: "var(--mis-cyan)" }}>{count}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div
          className="relative overflow-hidden"
          style={{
            minHeight: compact ? 280 : 560,
            aspectRatio: "16 / 10",
            background: "#17212b",
            border: "2px solid rgba(51,65,85,.9)",
            boxShadow: "inset 0 0 0 2px rgba(2,6,23,.72), 0 20px 60px rgba(0,0,0,0.34), 6px 7px 0 rgba(2,6,23,.42)",
            imageRendering: "pixelated",
          }}
          onClick={() => {
            if (!compact) setSelectedAgent(null);
          }}
        >
          <PixelCampusBackdrop />

          <div
            className="absolute z-[2] h-2 w-2"
            style={{ background: "var(--mis-cyan)", boxShadow: "0 0 14px var(--mis-cyan)", animation: "pixelPacketA 8s linear infinite" }}
          />
          <div
            className="absolute z-[2] h-2 w-2"
            style={{ background: "var(--mis-purple)", boxShadow: "0 0 14px var(--mis-purple)", animation: "pixelPacketB 9s linear infinite" }}
          />
          <div
            className="absolute left-[50%] top-[48%] z-[2] h-[1px] w-[38%] origin-left rotate-12"
            style={{ background: "linear-gradient(90deg, rgba(34,211,238,0), rgba(34,211,238,0.34), rgba(34,211,238,0))", animation: "pixelPulse 2.8s ease-in-out infinite" }}
          />
          <div
            className="absolute left-[21%] top-[42%] z-[2] h-[1px] w-[39%] origin-left -rotate-12"
            style={{ background: "linear-gradient(90deg, rgba(168,85,247,0), rgba(168,85,247,0.32), rgba(168,85,247,0))", animation: "pixelPulse 3.4s ease-in-out infinite" }}
          />

          {PIXEL_ZONES.map((zone) => (
            <PixelZone
              key={zone.id}
              zone={zone}
              metrics={metrics}
              selected={selectedZone?.id === zone.id}
              hovered={hoveredZone?.id === zone.id}
              onHover={setHoveredZone}
              onSelect={handleSelectZone}
              onOpen={(targetZone) => onOpenRoute(targetZone.route)}
              showLabels={!compact || ["task_hall", "approval_gate", "incident_corner", "control_tower"].includes(zone.id)}
            />
          ))}

          {!compact && taskCards.map((task, index) => <TaskCardSprite key={task.id} task={task} index={index} onOpen={onOpenRoute} />)}

          {agents.map((agent, index) => (
            <AgentSprite
              key={agent.id}
              agent={agent}
              index={index}
              active={selectedAgent?.id === agent.id}
              onSelect={handleSelectAgent}
            />
          ))}

          <div
            className="absolute bottom-3 left-3 right-3 z-30 flex flex-wrap items-center justify-between gap-2 border px-3 py-2"
            style={{ background: "rgba(2,6,23,0.82)", borderColor: "rgba(148,163,184,0.2)", backdropFilter: "blur(6px)", boxShadow: "3px 3px 0 rgba(2,6,23,.38)" }}
          >
            <div className="flex flex-wrap items-center gap-2 text-[10px]" style={{ color: "var(--mis-muted)" }}>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: "var(--mis-cyan)" }} /> Running</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: "#FBBF24" }} /> Approval</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: "#F87171" }} /> Incident</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: "var(--mis-purple)" }} /> Memory / audit</span>
            </div>
            {!compact && selectedZone && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenRoute(selectedAgent?.routeToDetail || selectedZone.route);
                }}
                className="inline-flex items-center gap-1.5 border px-2 py-1 text-[10px]"
                style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", borderColor: "rgba(34,211,238,0.25)" }}
              >
                <Route size={12} />
                Open formal page
                <ArrowRight size={12} />
              </button>
            )}
          </div>
        </div>
      </section>

      {!compact && (
        <div className="col-span-12 xl:col-span-4">
          <ZoneInspector
            selectedZone={selectedZone}
            hoveredZone={hoveredZone}
            selectedAgent={selectedAgent}
            metrics={metrics}
            agents={agents}
            taskCards={taskCards}
            onOpenRoute={onOpenRoute}
          />
        </div>
      )}
    </div>
  );
}
