import { LockKeyhole, ShieldCheck, ToggleLeft } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { CommercialEntitlementStatus } from "@/lib/mis";

function boolText(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function statusClass(enabled: unknown) {
  return enabled ? "status statusGood" : "status statusWarn";
}

function titleize(value: string) {
  return value.replace(/_/g, " ");
}

export function CommercialParityPage({
  entitlements,
  error,
}: Readonly<{ entitlements: CommercialEntitlementStatus; error?: string | null }>) {
  const capabilities = Object.entries(entitlements.capabilities || {}).sort(([left], [right]) => left.localeCompare(right));
  const gates = [...(entitlements.gates || [])].sort((left, right) => String(left.capability || "").localeCompare(String(right.capability || "")));
  const enabledCount = capabilities.filter(([, enabled]) => enabled).length;

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Commercial parity route</p>
          <h1>Commercial</h1>
          <p className="subtle">Edition, capability, and fail-closed entitlement state from the MIS API</p>
        </div>
        <span className="status statusGood">read-only</span>
      </header>

      {error ? <div className="banner error">Entitlements unavailable: {error}</div> : null}

      <section className="metrics">
        {[
          ["Edition", entitlements.edition_label || entitlements.edition || "Free Local"],
          ["Workspace", entitlements.workspace_id || "local_demo"],
          ["Enabled caps", `${enabledCount}/${capabilities.length}`],
          ["Fail-closed gates", gates.length],
        ].map(([label, value]) => (
          <div className="metric compactMetric" key={String(label)}>
            <span>{label}</span>
            <strong>{String(value)}</strong>
          </div>
        ))}
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Edition contract</h2>
            <span>{entitlements.status || "status unknown"}</span>
          </div>
          <div className="proofStrip">
            <span>source {entitlements.edition_source || "default"}</span>
            <span>read only {boolText(entitlements.safety?.read_only)}</span>
            <span>billing call {boolText(entitlements.safety?.billing_call_performed)}</span>
            <span>token omitted {boolText(entitlements.token_omitted)}</span>
          </div>
        </div>
        <div className="panel">
          <div className="panelHeader">
            <h2><LockKeyhole size={14} /> Safety boundary</h2>
            <span>billing deferred</span>
          </div>
          <p className="subtle">
            Capability gates are local product boundaries first; paid billing integration remains outside this parity route.
          </p>
        </div>
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ToggleLeft size={14} /> Capability matrix</h2>
            <span>{capabilities.length} capabilities</span>
          </div>
          <div className="list compactList">
            {capabilities.length ? capabilities.map(([capability, enabled]) => (
              <div className="row" key={capability}>
                <div>
                  <strong>{titleize(capability)}</strong>
                  <span>{capability}</span>
                </div>
                <span className={statusClass(enabled)}>{enabled ? "enabled" : "disabled"}</span>
              </div>
            )) : <p className="empty">No entitlement capabilities loaded.</p>}
          </div>
        </div>
        <div className="panel">
          <div className="panelHeader">
            <h2><LockKeyhole size={14} /> Fail-closed gates</h2>
            <span>{gates.length} gates</span>
          </div>
          <div className="list compactList">
            {gates.length ? gates.map((gate) => (
              <div className="row" key={gate.capability || `${gate.required_edition}:${gate.enforcement}`}>
                <div>
                  <strong>{titleize(gate.capability || "unknown capability")}</strong>
                  <span>requires {gate.required_edition || "pro_workspace"} · {gate.enforcement || "enforcement unknown"}</span>
                </div>
                <span className={statusClass(gate.enabled)}>{gate.enabled ? "enabled" : gate.status || "disabled"}</span>
              </div>
            )) : <p className="empty">No commercial gates loaded.</p>}
          </div>
        </div>
      </section>
    </AppFrame>
  );
}
