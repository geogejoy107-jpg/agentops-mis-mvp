import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import {
  ArrowRight,
  Bot,
  Boxes,
  ExternalLink,
  Gamepad2,
  Map,
  RefreshCw,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { pick, usePreferences } from "../../context/PreferencesContext";
import {
  AGENT_TARGET_OBJECT_BY_ZONE,
  localizedSpatialText,
  RESEARCH_DISTRICT_LEVEL_COPY,
  RESEARCH_DISTRICT_OBJECTS_BY_LEVEL,
  spatialMetricValue,
  type ResearchDistrictSemanticObject,
  type SpatialSemanticLevel,
} from "../../spatial/researchDistrictSemanticMap";
import { useSpatialOperationsSnapshot } from "../../spatial/useSpatialOperationsSnapshot";
import { statusDisplay } from "../pixel/pixelModel";
import { AdvancedSpatialSurface, type SpatialAgentArtMode } from "../spatial/AdvancedSpatialSurface";
import { AgentArtPortrait, spatialAgentStatusColor } from "../spatial/AgentArtPortrait";

function normalizedLevel(raw: string | null): SpatialSemanticLevel {
  const level = Number(raw);
  return level === 0 || level === 1 || level === 2 || level === 3 ? level : 1;
}

function normalizedArtMode(raw: string | null): SpatialAgentArtMode {
  return raw === "industrial" ? "industrial" : "cozy";
}

export function AdvancedSpatialOffice() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { locale } = usePreferences();
  const { metrics, agents, taskCards, loading, error, refresh } = useSpatialOperationsSnapshot();
  const level = normalizedLevel(searchParams.get("level"));
  const artMode = normalizedArtMode(searchParams.get("art"));
  const objects = RESEARCH_DISTRICT_OBJECTS_BY_LEVEL[level];
  const [selectedObjectId, setSelectedObjectId] = useState(objects[0]?.id || "");
  const selectedObject = objects.find((object) => object.id === selectedObjectId) || objects[0];

  const copy = pick(locale, {
    en: {
      title: "Spatial Research District",
      subtitle: "A game-like semantic surface over the formal AgentOps MIS ledgers. Every operational prop has a route, authority kind and projected signal; decorative terrain carries no authority meaning.",
      live: "Live projection",
      fallback: "Fallback data",
      advanced: "Advanced Canvas",
      authority: "MIS remains authoritative",
      basic: "Basic / Lite Office",
      refresh: "Refresh",
      agentRail: "Agents in district",
      agentRailBody: "The selected art track is the Agent itself. Status and risk remain separate channels.",
      semanticInspector: "Semantic inspector",
      authorityKind: "Authority kind",
      formalRoute: "Formal route",
      projectedSignal: "Projected signal",
      interaction: "Interaction",
      openLedger: "Open formal MIS page",
      worldBoundary: "World boundary",
      worldBoundaryBody: "This surface orients, projects and navigates. It never owns Agent, task, run, tool, approval, memory, artifact, evaluation, audit or delivery state.",
      source: "State source",
      sourceLive: "AgentOps MIS API with safe fallback per endpoint.",
      sourceFallback: "Demo-safe fallback because live API retrieval failed.",
      cozy: "Cozy character",
      industrial: "Industrial unit",
      objects: "Objects",
      runs: "Runs",
      taskCards: "Task cards",
    },
    zh: {
      title: "空间研究城区",
      subtitle: "覆盖在 AgentOps MIS 正式账本之上的游戏化语义界面。每个运营物件都具有正式路由、权威类型和投影信号；装饰地形不承载权威含义。",
      live: "实时投影",
      fallback: "回退数据",
      advanced: "高级 Canvas",
      authority: "MIS 仍是权威系统",
      basic: "基础 / 轻量办公室",
      refresh: "刷新",
      agentRail: "城区内 Agent",
      agentRailBody: "当前美术轨道中的角色或单位本身就是 Agent。状态与风险继续使用独立通道。",
      semanticInspector: "语义检查器",
      authorityKind: "权威类型",
      formalRoute: "正式路由",
      projectedSignal: "投影信号",
      interaction: "交互深度",
      openLedger: "打开正式 MIS 页面",
      worldBoundary: "世界边界",
      worldBoundaryBody: "该界面只负责定位、投影和导航，绝不拥有 Agent、任务、运行、工具、审批、记忆、Artifact、评估、审计或交付状态。",
      source: "状态来源",
      sourceLive: "AgentOps MIS API；单个端点失败时使用安全回退。",
      sourceFallback: "实时 API 获取失败，当前使用演示安全回退。",
      cozy: "生活模拟角色",
      industrial: "工业单位",
      objects: "物件",
      runs: "运行",
      taskCards: "任务卡",
    },
  });

  useEffect(() => {
    if (!objects.some((object) => object.id === selectedObjectId)) {
      setSelectedObjectId(objects[0]?.id || "");
    }
  }, [objects, selectedObjectId]);

  const updateQuery = (next: { art?: SpatialAgentArtMode; level?: SpatialSemanticLevel }) => {
    const params = new URLSearchParams(searchParams);
    if (next.art) params.set("art", next.art);
    if (next.level !== undefined) params.set("level", String(next.level));
    setSearchParams(params, { replace: true });
  };

  const openRoute = (route: string) => {
    if (route.startsWith("http")) {
      window.open(route, "_blank", "noreferrer");
      return;
    }
    navigate(route);
  };

  const focusAgent = (agentIndex: number) => {
    const agent = agents[agentIndex];
    if (!agent) return;
    const targetId = AGENT_TARGET_OBJECT_BY_ZONE[agent.targetZone];
    const target = objects.find((object) => object.id === targetId)
      || objects.find((object) => object.targetZone === agent.targetZone);
    if (target) setSelectedObjectId(target.id);
  };

  const metricLabel = (object: ResearchDistrictSemanticObject): string => (
    `${spatialMetricValue(object, metrics)} ${localizedSpatialText(object.metricLabel, locale)}`
  );

  const levelCopy = RESEARCH_DISTRICT_LEVEL_COPY[level];

  return (
    <div
      className="space-y-4 max-w-none"
      data-testid="advanced-spatial-office"
      data-spatial-renderer="advanced-canvas"
      data-spatial-level={level}
      data-spatial-art-mode={artMode}
      data-spatial-source={error ? "fallback" : "mixed-live"}
    >
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
            <span className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(34,211,238,.1)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,.2)" }}>
              <Sparkles size={11} />{error ? copy.fallback : copy.live}
            </span>
            <span className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(168,85,247,.1)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,.2)" }}>
              <Gamepad2 size={11} />{copy.advanced}
            </span>
            <span className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(42,157,143,.1)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,.2)" }}>
              <ShieldCheck size={11} />{copy.authority}
            </span>
          </div>
          <p className="mt-1 max-w-4xl text-xs leading-relaxed" style={{ color: "var(--mis-dim)" }}>{copy.subtitle}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/workspace/pixel-office" className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs" style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}>
            <Map size={13} />{copy.basic}
          </Link>
          <button type="button" onClick={() => void refresh()} disabled={loading} className="inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs disabled:opacity-50" style={{ background: "rgba(34,211,238,.1)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,.22)" }}>
            <RefreshCw size={13} className={loading ? "animate-spin" : ""} />{copy.refresh}
          </button>
        </div>
      </header>

      <section className="flex flex-wrap items-center justify-between gap-3 rounded-lg p-2.5" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <div className="flex items-center gap-1 rounded p-1" style={{ background: "var(--mis-surface2)" }}>
          {(["cozy", "industrial"] as const).map((mode) => (
            <button key={mode} type="button" onClick={() => updateQuery({ art: mode })} className="rounded px-3 py-1.5 text-[11px]" style={{ background: artMode === mode ? (mode === "cozy" ? "#6B4C35" : "#2F4A58") : "transparent", color: artMode === mode ? "#FFF4DD" : "var(--mis-dim)", border: artMode === mode ? "1px solid rgba(255,255,255,.18)" : "1px solid transparent" }} data-testid={`art-mode-${mode}`}>
              {mode === "cozy" ? copy.cozy : copy.industrial}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-1 rounded p-1" style={{ background: "var(--mis-surface2)" }}>
          {([0, 1, 2, 3] as const).map((nextLevel) => (
            <button key={nextLevel} type="button" onClick={() => updateQuery({ level: nextLevel })} className="rounded px-3 py-1.5 text-[11px]" style={{ background: level === nextLevel ? "rgba(34,211,238,.14)" : "transparent", color: level === nextLevel ? "var(--mis-cyan)" : "var(--mis-dim)", border: level === nextLevel ? "1px solid rgba(34,211,238,.22)" : "1px solid transparent" }} data-testid={`semantic-level-${nextLevel}`}>
              L{nextLevel}
            </button>
          ))}
        </div>
        <div className="min-w-0 text-right">
          <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{localizedSpatialText(levelCopy.label, locale)}</div>
          <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{localizedSpatialText(levelCopy.subtitle, locale)}</div>
        </div>
      </section>

      <section className="grid grid-cols-1 gap-4 2xl:grid-cols-[220px_minmax(0,1fr)_290px]">
        <aside className="order-2 overflow-hidden rounded-lg 2xl:order-1" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }} data-testid="spatial-agent-rail">
          <div className="border-b px-3 py-3" style={{ borderColor: "var(--mis-border)" }}>
            <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--mis-text)" }}><Bot size={13} />{copy.agentRail}</div>
            <p className="mt-1 text-[10px] leading-relaxed" style={{ color: "var(--mis-muted)" }}>{copy.agentRailBody}</p>
          </div>
          <div className="flex gap-2 overflow-x-auto p-2 2xl:block 2xl:max-h-[560px] 2xl:space-y-1 2xl:overflow-y-auto">
            {agents.slice(0, 8).map((agent, index) => (
              <button key={agent.id} type="button" onClick={() => focusAgent(index)} className="flex min-w-[190px] items-center gap-2 rounded p-2 text-left hover:bg-white/[.04] 2xl:min-w-0 2xl:w-full" style={{ border: "1px solid rgba(148,163,184,.09)" }} data-agent-id={agent.id}>
                <AgentArtPortrait agent={agent} artMode={artMode} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[11px] font-medium" style={{ color: "var(--mis-text)" }}>{agent.name}</span>
                  <span className="mt-0.5 block truncate text-[9px]" style={{ color: "var(--mis-muted)" }}>{agent.role} · {agent.runtime}</span>
                  <span className="mt-1 inline-flex items-center gap-1 text-[9px]" style={{ color: spatialAgentStatusColor(agent.status) }}>
                    <span className="h-1.5 w-1.5" style={{ background: spatialAgentStatusColor(agent.status) }} />
                    {statusDisplay(agent.status, locale)}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </aside>

        <main className="order-1 min-w-0 2xl:order-2">
          <AdvancedSpatialSurface
            agents={agents}
            metrics={metrics}
            level={level}
            artMode={artMode}
            locale={locale}
            selectedObjectId={selectedObject?.id}
            onSelectObject={(object) => setSelectedObjectId(object.id)}
            onOpenRoute={openRoute}
          />
          <div className="mt-2 flex gap-2 overflow-x-auto pb-1" data-testid="semantic-object-strip">
            {objects.map((object) => (
              <button key={object.id} type="button" onClick={() => setSelectedObjectId(object.id)} className="shrink-0 rounded px-2.5 py-1.5 text-[9px]" style={{ background: selectedObject?.id === object.id ? "rgba(34,211,238,.1)" : "var(--mis-surface)", color: selectedObject?.id === object.id ? "var(--mis-cyan)" : "var(--mis-dim)", border: selectedObject?.id === object.id ? "1px solid rgba(34,211,238,.22)" : "1px solid var(--mis-border)" }}>
                {localizedSpatialText(object.label, locale)}
              </button>
            ))}
          </div>
        </main>

        <aside className="order-3 rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }} data-testid="spatial-semantic-inspector">
          <div className="flex items-center gap-2 text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}><Boxes size={12} />{copy.semanticInspector}</div>
          {selectedObject && (
            <>
              <h2 className="mt-2 text-base font-semibold" style={{ color: "var(--mis-text)" }}>{localizedSpatialText(selectedObject.label, locale)}</h2>
              <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{localizedSpatialText(selectedObject.description, locale)}</p>
              <dl className="mt-4 space-y-3 text-[11px]">
                <div><dt className="text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.authorityKind}</dt><dd className="mt-1 font-mono" style={{ color: "var(--mis-text)" }}>{selectedObject.authorityKind}</dd></div>
                <div><dt className="text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.formalRoute}</dt><dd className="mt-1 break-all font-mono" style={{ color: "var(--mis-cyan)" }}>{selectedObject.formalRoute}</dd></div>
                <div><dt className="text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.projectedSignal}</dt><dd className="mt-1" style={{ color: "var(--mis-text)" }}>{metricLabel(selectedObject)}</dd></div>
                <div><dt className="text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.interaction}</dt><dd className="mt-1 font-mono" style={{ color: "var(--mis-text)" }}>{selectedObject.interaction}</dd></div>
              </dl>
              <button type="button" onClick={() => openRoute(selectedObject.formalRoute)} className="mt-4 inline-flex w-full items-center justify-between rounded px-3 py-2 text-[11px]" style={{ background: "rgba(34,211,238,.1)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,.22)" }}>
                {copy.openLedger}<ArrowRight size={13} />
              </button>
            </>
          )}

          <section className="mt-5 rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,.12)" }}>
            <div className="flex items-center gap-2 text-[10px] font-semibold" style={{ color: "var(--mis-text)" }}><ShieldCheck size={12} />{copy.worldBoundary}</div>
            <p className="mt-1 text-[10px] leading-relaxed" style={{ color: "var(--mis-muted)" }}>{copy.worldBoundaryBody}</p>
          </section>
          <section className="mt-3 rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,.12)" }}>
            <div className="text-[9px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.source}</div>
            <p className="mt-1 text-[10px] leading-relaxed" style={{ color: error ? "var(--mis-warning)" : "var(--mis-dim)" }}>{error ? copy.sourceFallback : copy.sourceLive}</p>
          </section>
          <section className="mt-3 grid grid-cols-2 gap-2">
            {[
              { label: copy.objects, value: objects.length },
              { label: "Agent", value: agents.length },
              { label: copy.runs, value: metrics.totalRuns },
              { label: copy.taskCards, value: taskCards.length },
            ].map((item) => (
              <div key={item.label} className="rounded p-2" style={{ background: "rgba(2,6,23,.24)" }}>
                <div className="text-[8px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{item.label}</div>
                <div className="mt-0.5 text-base font-semibold" style={{ color: "var(--mis-text)" }}>{item.value}</div>
              </div>
            ))}
          </section>
        </aside>
      </section>

      <footer className="flex flex-wrap items-center justify-between gap-2 rounded-lg px-3 py-2 text-[10px]" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)", color: "var(--mis-muted)" }}>
        <span>{copy.objects}: {objects.length} · L{level} · {artMode}</span>
        <span className="inline-flex items-center gap-1"><ExternalLink size={11} />AgentOps MIS authority routes only</span>
      </footer>
    </div>
  );
}
