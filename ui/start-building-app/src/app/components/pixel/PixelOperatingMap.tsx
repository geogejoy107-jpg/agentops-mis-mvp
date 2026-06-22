import { useMemo, useState } from "react";
import { ArrowRight, Building2, Layers3, Route } from "lucide-react";
import { AgentSprite } from "./AgentSprite";
import { PixelCampusBackdrop } from "./PixelCampusBackdrop";
import { PixelZone } from "./PixelZone";
import { TaskCardSprite } from "./TaskCardSprite";
import { ZoneInspector } from "./ZoneInspector";
import type { PixelAgent, PixelLocale, PixelMetrics, PixelTaskCard, PixelZoneDefinition } from "./pixelModel";
import { PIXEL_ZONES, PIXEL_ZONE_BY_ID, zoneDisplay } from "./pixelModel";
import {
  PIXEL_LAYER_BY_ZONE,
  PIXEL_OFFICE_LAYER_BY_ID,
  PIXEL_OFFICE_LAYERS,
  layerDisplay,
  type PixelOfficeLayerId,
} from "./pixelOfficeScene";
import { getPixelOfficeTheme, type PixelOfficeThemeId } from "./pixelOfficeTheme";

interface PixelOperatingMapProps {
  agents: PixelAgent[];
  taskCards: PixelTaskCard[];
  metrics: PixelMetrics;
  onOpenRoute: (route: string) => void;
  compact?: boolean;
  locale?: PixelLocale;
  themeId?: PixelOfficeThemeId;
}

function zoneAgentsCount(agents: PixelAgent[], zone: PixelZoneDefinition) {
  return agents.filter((agent) => agent.targetZone === zone.id).length;
}

export function PixelOperatingMap({
  agents,
  taskCards,
  metrics,
  onOpenRoute,
  compact = false,
  locale = "en",
  themeId,
}: PixelOperatingMapProps) {
  const zh = locale === "zh";
  const theme = getPixelOfficeTheme(themeId);
  const [selectedLayerId, setSelectedLayerId] = useState<PixelOfficeLayerId>("overview");
  const [selectedZone, setSelectedZone] = useState<PixelZoneDefinition | null>(PIXEL_ZONE_BY_ID.control_tower);
  const [hoveredZone, setHoveredZone] = useState<PixelZoneDefinition | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<PixelAgent | null>(null);

  const activeLayer = PIXEL_OFFICE_LAYER_BY_ID[compact ? "overview" : selectedLayerId];
  const layerCopy = layerDisplay(activeLayer, locale);

  const busiestZones = useMemo(
    () =>
      PIXEL_ZONES.map((zone) => ({ zone, count: zoneAgentsCount(agents, zone) }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 4),
    [agents],
  );

  const zoneIsDimmed = (zoneId: PixelZoneDefinition["id"]) =>
    activeLayer.id !== "overview" && !activeLayer.zoneIds.includes(zoneId);

  const selectLayer = (layerId: PixelOfficeLayerId) => {
    const nextLayer = PIXEL_OFFICE_LAYER_BY_ID[layerId];
    setSelectedLayerId(layerId);
    setSelectedAgent(null);
    setHoveredZone(null);
    const firstZone = nextLayer.zoneIds[0];
    setSelectedZone(firstZone ? PIXEL_ZONE_BY_ID[firstZone] : PIXEL_ZONE_BY_ID.control_tower);
  };

  const selectZone = (zone: PixelZoneDefinition) => {
    setSelectedAgent(null);
    setSelectedZone(zone);
    const layerId = PIXEL_LAYER_BY_ZONE[zone.id];
    if (!compact && layerId) setSelectedLayerId(layerId);
  };

  const selectAgent = (agent: PixelAgent) => {
    setSelectedAgent(agent);
    setSelectedZone(PIXEL_ZONE_BY_ID[agent.targetZone]);
    const layerId = PIXEL_LAYER_BY_ZONE[agent.targetZone];
    if (!compact && layerId) setSelectedLayerId(layerId);
  };

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
        @media (prefers-reduced-motion: reduce) { .pixel-agent-motion,.pixel-ambient-motion,.pixel-office-camera { animation:none !important; transition-duration:0ms !important; } }
      `}</style>

      <section className={compact ? "w-full" : "col-span-12 xl:col-span-8"}>
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="inline-flex items-center gap-1.5 border px-2 py-1 text-[10px] uppercase tracking-wide"
                style={{
                  background: theme.tones.active.background,
                  color: theme.tones.active.light,
                  borderColor: theme.tones.active.border,
                  borderRadius: theme.shape.controlRadius,
                  boxShadow: `2px 2px 0 ${theme.frame.insetBorder}`,
                }}
              >
                <Building2 size={12} />
                {theme.label[locale]}
              </span>
              <span
                className="inline-flex items-center gap-1.5 border px-2 py-1 text-[10px] uppercase tracking-wide"
                style={{ background: theme.frame.controlBar, color: "var(--mis-dim)", borderColor: theme.frame.controlBorder, borderRadius: theme.shape.controlRadius }}
              >
                <Layers3 size={12} />
                {layerCopy.label}
              </span>
            </div>
            {!compact && (
              <p className="mt-1 max-w-xl text-[11px]" style={{ color: "var(--mis-dim)" }}>
                {zh
                  ? `${layerCopy.description} 单击房间聚焦楼层，双击进入正式 MIS 账本。`
                  : `${layerCopy.description} Click a room to focus its floor; double-click to open the formal MIS ledger.`}
              </p>
            )}
          </div>

          {!compact && (
            <div className="flex flex-wrap gap-1.5" role="group" aria-label={zh ? "办公室楼层" : "Office floors"}>
              {PIXEL_OFFICE_LAYERS.map((layer) => {
                const selected = layer.id === selectedLayerId;
                const copy = layerDisplay(layer, locale);
                return (
                  <button
                    key={layer.id}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => selectLayer(layer.id)}
                    className="border px-2 py-1 text-[10px] transition-opacity hover:opacity-85"
                    style={{
                      background: selected ? theme.tones.active.background : theme.frame.controlBar,
                      color: selected ? theme.tones.active.light : "var(--mis-muted)",
                      borderColor: selected ? theme.tones.active.border : theme.frame.controlBorder,
                      borderRadius: theme.shape.controlRadius,
                    }}
                    title={copy.description}
                  >
                    {copy.label}
                  </button>
                );
              })}
            </div>
          )}
        </div>

        {!compact && (
          <div className="mb-2 flex flex-wrap gap-1.5 text-[10px]" style={{ color: "var(--mis-muted)" }}>
            {busiestZones.map(({ zone, count }) => (
              <button
                key={zone.id}
                type="button"
                onClick={() => selectZone(zone)}
                className="border px-2 py-1 hover:opacity-80"
                style={{ background: theme.frame.controlBar, borderColor: theme.frame.controlBorder, borderRadius: theme.shape.controlRadius }}
              >
                {zoneDisplay(zone, locale).label}: <span style={{ color: theme.tones.active.light }}>{count}</span>
              </button>
            ))}
          </div>
        )}

        <div
          className="relative overflow-hidden"
          style={{
            minHeight: compact ? 280 : 560,
            aspectRatio: "16 / 10",
            background: theme.frame.canvas,
            border: `2px solid ${theme.frame.border}`,
            boxShadow: `inset 0 0 0 2px ${theme.frame.insetBorder}, ${theme.frame.shadow}`,
            imageRendering: "pixelated",
            borderRadius: theme.shape.roomRadius,
          }}
          onClick={() => {
            if (!compact) setSelectedAgent(null);
          }}
        >
          <div
            className="pixel-office-camera absolute inset-0 transition-transform duration-500 ease-out"
            style={{ transform: `scale(${activeLayer.camera.scale})`, transformOrigin: activeLayer.camera.origin }}
          >
            <PixelCampusBackdrop theme={theme} />
            <span
              className="pixel-ambient-motion absolute z-[2] h-2 w-2"
              style={{ background: theme.frame.glowA, boxShadow: `0 0 14px ${theme.frame.glowA}`, animation: "pixelPacketA 8s linear infinite" }}
            />
            <span
              className="pixel-ambient-motion absolute z-[2] h-2 w-2"
              style={{ background: theme.frame.glowB, boxShadow: `0 0 14px ${theme.frame.glowB}`, animation: "pixelPacketB 9s linear infinite" }}
            />
            <span
              className="pixel-ambient-motion absolute left-[50%] top-[48%] z-[2] h-px w-[38%] origin-left rotate-12"
              style={{ background: `linear-gradient(90deg,transparent,${theme.frame.glowA},transparent)`, animation: "pixelPulse 2.8s ease-in-out infinite" }}
            />
            <span
              className="pixel-ambient-motion absolute left-[21%] top-[42%] z-[2] h-px w-[39%] origin-left -rotate-12"
              style={{ background: `linear-gradient(90deg,transparent,${theme.frame.glowB},transparent)`, animation: "pixelPulse 3.4s ease-in-out infinite" }}
            />

            {PIXEL_ZONES.map((zone) => (
              <PixelZone
                key={zone.id}
                zone={zone}
                metrics={metrics}
                selected={selectedZone?.id === zone.id}
                hovered={hoveredZone?.id === zone.id}
                onHover={setHoveredZone}
                onSelect={selectZone}
                onOpen={(target) => onOpenRoute(target.route)}
                showLabels={!compact || ["task_hall", "approval_gate", "incident_corner", "control_tower"].includes(zone.id)}
                theme={theme}
                dimmed={zoneIsDimmed(zone.id)}
                locale={locale}
              />
            ))}

            {!compact &&
              taskCards.map((task, index) => (
                <TaskCardSprite
                  key={task.id}
                  task={task}
                  index={index}
                  onOpen={onOpenRoute}
                  theme={theme}
                  dimmed={zoneIsDimmed("task_hall")}
                  locale={locale}
                />
              ))}

            {agents.map((agent, index) => (
              <AgentSprite
                key={agent.id}
                agent={agent}
                index={index}
                active={selectedAgent?.id === agent.id}
                onSelect={selectAgent}
                theme={theme}
                dimmed={zoneIsDimmed(agent.targetZone)}
                locale={locale}
              />
            ))}
          </div>

          <div
            className="absolute bottom-3 left-3 right-3 z-30 flex flex-wrap items-center justify-between gap-2 border px-3 py-2"
            style={{ background: theme.frame.controlBar, borderColor: theme.frame.controlBorder, backdropFilter: "blur(6px)", borderRadius: theme.shape.controlRadius }}
          >
            <div className="flex flex-wrap items-center gap-2 text-[10px]" style={{ color: "var(--mis-muted)" }}>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: theme.tones.active.light }} />{zh ? "运行中" : "Running"}</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: theme.tones.warning.light }} />{zh ? "审批" : "Approval"}</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: theme.tones.danger.light }} />{zh ? "故障" : "Incident"}</span>
              <span className="inline-flex items-center gap-1"><span className="h-2 w-2" style={{ background: theme.tones.purple.light }} />{zh ? "记忆 / 审计" : "Memory / audit"}</span>
            </div>
            {!compact && selectedZone && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onOpenRoute(selectedAgent?.routeToDetail || selectedZone.route);
                }}
                className="inline-flex items-center gap-1.5 border px-2 py-1 text-[10px]"
                style={{ background: theme.tones.active.background, color: theme.tones.active.light, borderColor: theme.tones.active.border, borderRadius: theme.shape.controlRadius }}
              >
                <Route size={12} />
                {zh ? "打开正式页面" : "Open formal page"}
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
            locale={locale}
          />
        </div>
      )}
    </div>
  );
}