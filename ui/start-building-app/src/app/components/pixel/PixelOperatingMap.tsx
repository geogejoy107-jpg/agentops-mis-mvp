import { useMemo, useState } from "react";
import { ArrowRight, Layers3, Route } from "lucide-react";
import { AgentSprite } from "./AgentSprite";
import { PixelCampusBackdrop } from "./PixelCampusBackdrop";
import { PixelZone } from "./PixelZone";
import { TaskCardSprite } from "./TaskCardSprite";
import { ZoneInspector } from "./ZoneInspector";
import type { PixelAgent, PixelLocale, PixelMetrics, PixelTaskCard, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONES, PIXEL_ZONE_BY_ID, zoneDisplay } from "./pixelModel";

interface Props {
  agents: PixelAgent[];
  taskCards: PixelTaskCard[];
  metrics: PixelMetrics;
  onOpenRoute: (route: string) => void;
  compact?: boolean;
  locale?: PixelLocale;
}

function zoneAgentsCount(agents: PixelAgent[], zone: PixelZoneDefinition) {
  return agents.filter((agent) => agent.targetZone === zone.id).length;
}

export function PixelOperatingMap({ agents, taskCards, metrics, onOpenRoute, compact = false, locale = "en" }: Props) {
  const zh = locale === "zh";
  const [selectedZone, setSelectedZone] = useState<PixelZoneDefinition | null>(PIXEL_ZONE_BY_ID.control_tower);
  const [hoveredZone, setHoveredZone] = useState<PixelZoneDefinition | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<PixelAgent | null>(null);
  const busiestZones = useMemo(() => PIXEL_ZONES.map((zone) => ({ zone, count: zoneAgentsCount(agents, zone) })).sort((a, b) => b.count - a.count).slice(0, 4), [agents]);

  const selectZone = (zone: PixelZoneDefinition) => { setSelectedAgent(null); setSelectedZone(zone); };
  const selectAgent = (agent: PixelAgent) => { setSelectedAgent(agent); setSelectedZone(PIXEL_ZONE_BY_ID[agent.targetZone]); };

  return (
    <div className={compact ? "w-full" : "grid grid-cols-12 gap-4"}>
      <style>{`
        @keyframes pixelPacketA { 0%{transform:translate(8%,18%);opacity:.05} 18%{opacity:.8} 50%{transform:translate(52%,46%);opacity:.9} 100%{transform:translate(90%,72%);opacity:.05} }
        @keyframes pixelPacketB { 0%{transform:translate(88%,16%);opacity:.05} 22%{opacity:.7} 58%{transform:translate(44%,50%);opacity:.9} 100%{transform:translate(12%,78%);opacity:.05} }
        @keyframes pixelPulse { 0%,100%{opacity:.24} 50%{opacity:.82} }
        @keyframes pixelAgentIdle { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-1px)} }
        @keyframes pixelAgentWork { 0%,100%{transform:translateY(0) rotate(-1deg)} 50%{transform:translateY(-2px) rotate(1deg)} }
        @keyframes pixelAgentWait { 0%,100%{transform:translateY(0);opacity:.82} 50%{transform:translateY(-1px);opacity:1} }
        @keyframes pixelAgentAlert { 0%,100%{transform:translateX(-1px)} 50%{transform:translateX(1px)} }
        @media (prefers-reduced-motion: reduce) { .pixel-agent-motion,.pixel-ambient-motion { animation:none !important; transition-duration:0ms !important; } }
      `}</style>

      <section className={compact ? "w-full" : "col-span-12 xl:col-span-8"}>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="inline-flex items-center gap-1.5 border px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(34,211,238,.1)", color: "var(--mis-cyan)", borderColor: "rgba(34,211,238,.22)", boxShadow: "2px 2px 0 rgba(2,6,23,.3)" }}>
              <Layers3 size={12} />
              {zh ? "夜班 Agent 园区 · 原创 CSS 场景" : "Night-shift Agent Campus · original CSS scene"}
            </div>
            {!compact && <p className="mt-1 text-[11px]" style={{ color: "var(--mis-dim)" }}>{zh ? "房间、小人和告警仍由正式 MIS 数据驱动；双击进入对应账本。" : "Rooms, people and alerts remain driven by formal MIS data; double-click to open the ledger."}</p>}
          </div>
          {!compact && <div className="flex flex-wrap items-center gap-1.5 text-[10px]" style={{ color: "var(--mis-muted)" }}>{busiestZones.map(({ zone, count }) => <button key={zone.id} type="button" onClick={() => selectZone(zone)} className="border px-2 py-1 hover:opacity-80" style={{ background: "var(--mis-surface2)", borderColor: "rgba(148,163,184,.16)" }}>{zoneDisplay(zone, locale).label}: <span style={{ color: "var(--mis-cyan)" }}>{count}</span></button>)}</div>}
        </div>

        <div className="relative overflow-hidden" style={{ minHeight: compact ? 280 : 560, aspectRatio: "16 / 10", background: "#17212b", border: "2px solid rgba(51,65,85,.9)", boxShadow: "inset 0 0 0 2px rgba(2,6,23,.72),0 20px 60px rgba(0,0,0,.34),6px 7px 0 rgba(2,6,23,.42)", imageRendering: "pixelated" }} onClick={() => { if (!compact) setSelectedAgent(null); }}>
          <PixelCampusBackdrop />
          <span className="pixel-ambient-motion absolute z-[2] h-2 w-2" style={{ background: "var(--mis-cyan)", boxShadow: "0 0 14px var(--mis-cyan)", animation: "pixelPacketA 8s linear infinite" }} />
          <span className="pixel-ambient-motion absolute z-[2] h-2 w-2" style={{ background: "var(--mis-purple)", boxShadow: "0 0 14px var(--mis-purple)", animation: "pixelPacketB 9s linear infinite" }} />
          <span className="pixel-ambient-motion absolute left-[50%] top-[48%] z-[2] h-px w-[38%] origin-left rotate-12" style={{ background: "linear-gradient(90deg,transparent,rgba(34,211,238,.34),transparent)", animation: "pixelPulse 2.8s ease-in-out infinite" }} />
          <span className="pixel-ambient-motion absolute left-[21%] top-[42%] z-[2] h-px w-[39%] origin-left -rotate-12" style={{ background: "linear-gradient(90deg,transparent,rgba(168,85,247,.32),transparent)", animation: "pixelPulse 3.4s ease-in-out infinite" }} />

          {PIXEL_ZONES.map((zone) => <PixelZone key={zone.id} zone={zone} metrics={metrics} selected={selectedZone?.id === zone.id} hovered={hoveredZone?.id === zone.id} onHover={setHoveredZone} onSelect={selectZone} onOpen={(target) => onOpenRoute(target.route)} showLabels={!compact || ["task_hall","approval_gate","incident_corner","control_tower"].includes(zone.id)} locale={locale} />)}
          {!compact && taskCards.map((task, index) => <TaskCardSprite key={task.id} task={task} index={index} onOpen={onOpenRoute} locale={locale} />)}
          {agents.map((agent, index) => <AgentSprite key={agent.id} agent={agent} index={index} active={selectedAgent?.id === agent.id} onSelect={selectAgent} locale={locale} />)}

          <div className="absolute bottom-3 left-3 right-3 z-30 flex flex-wrap items-center justify-between gap-2 border px-3 py-2" style={{ background: "rgba(2,6,23,.82)", borderColor: "rgba(148,163,184,.2)", backdropFilter: "blur(6px)", boxShadow: "3px 3px 0 rgba(2,6,23,.38)" }}>
            <div className="flex flex-wrap items-center gap-2 text-[10px]" style={{ color: "var(--mis-muted)" }}>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: "var(--mis-cyan)" }} />{zh ? "运行中" : "Running"}</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2 bg-amber-400" />{zh ? "审批" : "Approval"}</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2 bg-red-400" />{zh ? "故障" : "Incident"}</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: "var(--mis-purple)" }} />{zh ? "记忆 / 审计" : "Memory / audit"}</span>
            </div>
            {!compact && selectedZone && <button type="button" onClick={(event) => { event.stopPropagation(); onOpenRoute(selectedAgent?.routeToDetail || selectedZone.route); }} className="inline-flex items-center gap-1.5 border px-2 py-1 text-[10px]" style={{ background: "rgba(34,211,238,.1)", color: "var(--mis-cyan)", borderColor: "rgba(34,211,238,.25)" }}><Route size={12} />{zh ? "打开正式页面" : "Open formal page"}<ArrowRight size={12} /></button>}
          </div>
        </div>
      </section>

      {!compact && <div className="col-span-12 xl:col-span-4"><ZoneInspector selectedZone={selectedZone} hoveredZone={hoveredZone} selectedAgent={selectedAgent} metrics={metrics} agents={agents} taskCards={taskCards} onOpenRoute={onOpenRoute} locale={locale} /></div>}
    </div>
  );
}
