"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Bot, KeyRound, RefreshCw, ShieldCheck, TerminalSquare } from "lucide-react";
import { AppFrame } from "./AppFrame";
import { loadAgentControlSnapshot, type AgentControlSnapshot, type ReadinessGate } from "@/lib/mis";

type LoadState = {
  data: AgentControlSnapshot | null;
  error: string | null;
  loading: boolean;
};

function statusClass(status?: string) {
  if (["ready", "running", "pass", "healthy"].includes(status || "")) return "status statusGood";
  if (["blocked", "failed", "fail", "unavailable"].includes(status || "")) return "status statusBad";
  if (["attention", "degraded", "review_required", "warn"].includes(status || "")) return "status statusWarn";
  return "status";
}

function boolStatus(value?: boolean) {
  return value ? "ready" : "attention";
}

function numberValue(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function GateList({ gates }: Readonly<{ gates?: ReadinessGate[] }>) {
  const rows = (gates || []).slice(0, 6);
  if (!rows.length) return <p className="empty">No readiness gates loaded.</p>;
  return (
    <div className="list compact">
      {rows.map((gate, index) => (
        <article className="row" key={`${gate.id || gate.label || "gate"}:${index}`}>
          <div>
            <strong>{gate.label || gate.id || "Readiness gate"}</strong>
            <span>{gate.detail || gate.summary || gate.next_action || gate.action || "No detail loaded."}</span>
          </div>
          <span className={statusClass(gate.status || (gate.ok ? "ready" : "attention"))}>{gate.status || (gate.ok ? "pass" : "attention")}</span>
        </article>
      ))}
    </div>
  );
}

export function AgentsParityPage() {
  const [state, setState] = useState<LoadState>({ data: null, error: null, loading: true });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      setState({ data: await loadAgentControlSnapshot(), error: null, loading: false });
    } catch (err) {
      setState({ data: null, error: err instanceof Error ? err.message : String(err), loading: false });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const agents = state.data?.agents || [];
  const security = state.data?.security;
  const worker = state.data?.workerStatus;
  const adapter = state.data?.adapterReadiness;
  const runningDaemons = (worker?.daemons || []).filter((daemon) => daemon.running).length;
  const adapterRows = useMemo(() => Object.values(adapter?.adapters || {}), [adapter?.adapters]);

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Production safety parity route</p>
          <h1>Agents</h1>
          <p className="subtle">Read-only control plane for worker readiness, scoped execution, and production safety gates.</p>
        </div>
        <button className="iconButton" onClick={refresh} disabled={state.loading} aria-label="Refresh agents control plane">
          <RefreshCw size={17} className={state.loading ? "spin" : ""} />
        </button>
      </header>

      {state.error ? <div className="banner error">MIS API unavailable through /api/mis agent-control endpoints: {state.error}</div> : null}

      <section className="metrics">
        {[
          ["Agents", agents.length, <Bot key="agents" size={18} />, "ready"],
          ["Worker status", worker?.status || "unknown", <Activity key="workers" size={18} />, worker?.status],
          ["Production", security?.production_ready ? "ready" : "local", <ShieldCheck key="security" size={18} />, boolStatus(security?.production_ready)],
          ["Adapter", adapter?.summary?.recommended_adapter || worker?.adapter_readiness?.recommended_adapter || "mock", <TerminalSquare key="adapter" size={18} />, adapter?.status],
        ].map(([label, value, icon, status]) => (
          <div className="metric" key={String(label)}>
            <span className="metricIcon">{icon}</span>
            <span>{label}</span>
            <strong className="metricText">{state.loading && !state.data ? "..." : String(value)}</strong>
            <span className={statusClass(String(status || "unknown"))}>{String(status || "unknown")}</span>
          </div>
        ))}
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Production security</h2>
            <span>{security?.auth_mode || "auth unknown"}</span>
          </div>
          <p className="subtle">{security?.contract || "Production mode must fail closed before shared deployment."}</p>
          <div className="proofStrip">
            <span className={statusClass(security?.safety?.read_only ? "ready" : "attention")}>read only</span>
            <span className={statusClass(security?.safety?.token_omitted ? "ready" : "attention")}>token omitted</span>
            <span className={statusClass(security?.safety?.live_execution_performed === false ? "ready" : "attention")}>no live execution</span>
          </div>
          <GateList gates={security?.gates} />
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><Activity size={14} /> Worker fleet</h2>
            <span>{worker?.fleet_health?.overall || worker?.status || "unknown"}</span>
          </div>
          <div className="miniMetrics">
            <span>workers <strong>{numberValue(worker?.worker_count)}</strong></span>
            <span>daemons <strong>{runningDaemons}/{numberValue(worker?.daemons?.length)}</strong></span>
            <span>pending <strong>{numberValue(worker?.pending_worker_tasks)}</strong></span>
            <span>stuck <strong>{numberValue(worker?.stuck_worker_tasks)}</strong></span>
            <span>remote <strong>{numberValue(worker?.remote_worker_count)}</strong></span>
            <span>sessions <strong>{numberValue(worker?.active_remote_sessions)}</strong></span>
          </div>
          <GateList gates={worker?.fleet_health?.gates} />
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><TerminalSquare size={14} /> Adapter readiness</h2>
          <span>recommended {adapter?.summary?.recommended_adapter || "mock"}</span>
        </div>
        <div className="adapterGrid">
          {adapterRows.map((item) => (
            <article className="adapterCard" key={item.adapter || "adapter"}>
              <div>
                <strong>{item.adapter || "adapter"}</strong>
                <span>{item.recommended_action || "agentops worker readiness"}</span>
              </div>
              <span className={statusClass(item.readiness)}>{item.readiness || "unknown"}</span>
              <div className="proofStrip">
                <span className={statusClass(item.token_omitted ? "ready" : "attention")}>token omitted</span>
                <span className={statusClass(item.requires_confirm_run ? "attention" : "ready")}>{item.requires_confirm_run ? "confirm required" : "safe default"}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><KeyRound size={14} /> Agent registry</h2>
          <span>{agents.length} visible</span>
        </div>
        <div className="list compact">
          {agents.slice(0, 12).map((agent) => (
            <article className="row" key={agent.agent_id}>
              <div>
                <strong>{agent.name || agent.agent_id}</strong>
                <span>{agent.agent_id} · {agent.role || "agent"} · {agent.runtime_type || "runtime"}</span>
              </div>
              <span className={statusClass(agent.status)}>{agent.status || "unknown"}</span>
            </article>
          ))}
        </div>
      </section>
    </AppFrame>
  );
}
