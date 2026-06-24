import { ClipboardCheck, GitBranch, ListChecks, LockKeyhole, Rocket, ShieldAlert, ShieldCheck, ToggleLeft } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { CommercialEntitlementStatus, CommercialReleaseStatusPayload } from "@/lib/mis";

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

function compactStatus(value: unknown) {
  return titleize(String(value || "unknown")).replace("blocked release promotion required", "blocked promotion");
}

function displayList(items: string[] | undefined, limit = 5) {
  return (items || []).filter(Boolean).slice(0, limit);
}

export function CommercialParityPage({
  entitlements,
  error,
  releaseStatus,
  releaseError,
}: Readonly<{
  entitlements: CommercialEntitlementStatus;
  error?: string | null;
  releaseStatus?: CommercialReleaseStatusPayload;
  releaseError?: string | null;
}>) {
  const capabilities = Object.entries(entitlements.capabilities || {}).sort(([left], [right]) => left.localeCompare(right));
  const gates = [...(entitlements.gates || [])].sort((left, right) => String(left.capability || "").localeCompare(String(right.capability || "")));
  const enabledCount = capabilities.filter(([, enabled]) => enabled).length;
  const release = releaseStatus || {};
  const preflight = release.promotion_preflight || {};
  const promotionPacket = release.promotion_packet || {};
  const receiptPlan = release.release_grade_receipt_plan || {};
  const currentEvidence = release.current_evidence_status || {};
  const exactHead = release.external_exact_head_ci || {};
  const blockers = release.blockers?.length ? release.blockers : preflight.known_blockers || [];
  const currentGates = displayList(currentEvidence.gates_requiring_current_evidence, 6);
  const releaseGradeGates = release.receipt_summary?.gates_with_release_grade_receipts || [];

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
      {releaseError ? <div className="banner error">Release status unavailable: {releaseError}</div> : null}

      <section className="metrics six">
        {[
          ["Edition", entitlements.edition_label || entitlements.edition || "Free Local"],
          ["Workspace", entitlements.workspace_id || "local_demo"],
          ["Enabled caps", `${enabledCount}/${capabilities.length}`],
          ["Fail-closed gates", gates.length],
          ["Release gate", compactStatus(release.status)],
          ["Exact-head CI", boolText(currentEvidence.exact_head_ci_verified || exactHead.exact_head_ci_verified)],
        ].map(([label, value]) => (
          <div className="metric compactMetric" key={String(label)}>
            <span>{label}</span>
            <strong>{String(value)}</strong>
          </div>
        ))}
      </section>

      <section className="grid">
        <div className="panel" data-smoke="commercial-release-status">
          <div className="panelHeader">
            <h2><Rocket size={14} /> Release promotion</h2>
            <span>{compactStatus(release.status)}</span>
          </div>
          <div className="proofStrip">
            <span>{release.contract_id || "commercial_release_status_api_v1"}</span>
            <span>release complete {boolText(release.release_complete)}</span>
            <span>handoff {boolText(release.commercial_handoff_allowed)}</span>
            <span>ready to merge {boolText(release.ready_to_merge)}</span>
          </div>
          <div className="list compactList">
            {displayList(blockers, 4).map((blocker) => (
              <div className="row" key={blocker}>
                <div>
                  <strong>{titleize(blocker)}</strong>
                  <span>promotion blocker</span>
                </div>
                <span className="status statusWarn">blocked</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel" data-smoke="commercial-exact-head-ci-command">
          <div className="panelHeader">
            <h2><GitBranch size={14} /> Exact-head CI</h2>
            <span>{boolText(exactHead.checked)}</span>
          </div>
          <div className="proofStrip">
            <span>{exactHead.contract_id || "commercial_exact_head_ci_evidence_v1"}</span>
            <span>network called {boolText(exactHead.network_called)}</span>
            <span>verified {boolText(currentEvidence.exact_head_ci_verified || exactHead.exact_head_ci_verified)}</span>
            <span>source {currentEvidence.exact_head_ci_source || "static_current_evidence_status"}</span>
          </div>
          {exactHead.checked ? (
            <div className="list compactList">
              <div className="row">
                <div>
                  <strong>{exactHead.status || "external check completed"}</strong>
                  <span>{exactHead.run_id ? `run ${exactHead.run_id}` : "GitHub Actions readback"}</span>
                </div>
                <span className={statusClass(exactHead.exact_head_ci_verified)}>{exactHead.exact_head_ci_verified ? "verified" : "blocked"}</span>
              </div>
            </div>
          ) : null}
          <p className="subtle"><code>{exactHead.command || release.commands?.exact_head_ci || "python3 scripts/commercial_exact_head_ci_evidence.py --from-gh --require-current-head"}</code></p>
          <form action="/workspace/commercial" method="get" data-smoke="commercial-external-ci-readback-form">
            <input type="hidden" name="exact_head_ci" value="1" />
            <button className="miniButton" type="submit">Check exact-head CI</button>
          </form>
        </div>
      </section>

      <section className="grid">
        <div className="panel" data-smoke="commercial-release-promotion-preflight">
          <div className="panelHeader">
            <h2><ShieldAlert size={14} /> Promotion preflight</h2>
            <span>{preflight.contract_id || "commercial_release_promotion_preflight_v1"}</span>
          </div>
          <div className="proofStrip">
            <span>promotion {boolText(preflight.release_promotion_allowed)}</span>
            <span>release-grade update {boolText(preflight.release_grade_update_allowed)}</span>
            <span>worktree clean {boolText(release.git_state?.worktree_clean)}</span>
          </div>
          <div className="list compactList">
            {displayList(preflight.source_contracts, 4).map((contract) => (
              <div className="row" key={contract}>
                <div>
                  <strong>{contract}</strong>
                  <span>source contract</span>
                </div>
                <span className="status statusWarn">required</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel" data-smoke="commercial-promotion-packet">
          <div className="panelHeader">
            <h2><ClipboardCheck size={14} /> Promotion packet</h2>
            <span>{compactStatus(promotionPacket.status)}</span>
          </div>
          <div className="proofStrip">
            <span>{promotionPacket.contract_id || "commercial_release_promotion_packet_v1"}</span>
            <span>read only {boolText(promotionPacket.read_only)}</span>
            <span>CI safe {boolText(promotionPacket.ci_safe)}</span>
          </div>
          <p className="subtle"><code>{release.commands?.promotion_packet || "python3 scripts/commercial_release_promotion_packet.py --include-external-ci-evidence"}</code></p>
          <div className="list compactList">
            {displayList(Object.keys(promotionPacket.packet_requires || {}), 4).map((requirement) => (
              <div className="row" key={requirement}>
                <div>
                  <strong>{titleize(requirement)}</strong>
                  <span>packet requirement</span>
                </div>
                <span className="status statusWarn">required</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel" data-smoke="commercial-current-evidence-gates">
          <div className="panelHeader">
            <h2><ListChecks size={14} /> Current evidence</h2>
            <span>{currentEvidence.contract_id || "commercial_current_evidence_status_v1"}</span>
          </div>
          <div className="proofStrip">
            <span>local receipts {(currentEvidence.gates_with_local_receipts || []).length}</span>
            <span>release-grade receipts {releaseGradeGates.length}</span>
            <span>real runtime required {boolText(currentEvidence.real_runtime_required)}</span>
          </div>
          <div className="list compactList">
            {currentGates.length ? currentGates.map((gate) => (
              <div className="row" key={gate}>
                <div>
                  <strong>{titleize(gate)}</strong>
                  <span>current evidence required</span>
                </div>
                <span className="status statusWarn">pending</span>
              </div>
            )) : (
              <div className="row">
                <div>
                  <strong>No current evidence gaps</strong>
                  <span>release-grade receipts can be checked</span>
                </div>
                <span className="status statusGood">ready</span>
              </div>
            )}
          </div>
        </div>
      </section>

      <section className="grid">
        <div className="panel" data-smoke="commercial-release-grade-receipt-plan">
          <div className="panelHeader">
            <h2><ClipboardCheck size={14} /> Receipt promotion plan</h2>
            <span>{compactStatus(receiptPlan.status)}</span>
          </div>
          <div className="proofStrip">
            <span>{receiptPlan.contract_id || "commercial_release_grade_receipt_plan_v1"}</span>
            <span>read only {boolText(receiptPlan.read_only)}</span>
            <span>CI safe {boolText(receiptPlan.ci_safe)}</span>
          </div>
          <p className="subtle"><code>{release.commands?.release_grade_receipt_plan || "python3 scripts/commercial_release_grade_receipt_plan.py --include-external-ci-evidence"}</code></p>
          <div className="list compactList">
            {displayList(Object.keys(receiptPlan.plan_requires || {}), 4).map((requirement) => (
              <div className="row" key={requirement}>
                <div>
                  <strong>{titleize(requirement)}</strong>
                  <span>receipt plan requirement</span>
                </div>
                <span className="status statusWarn">required</span>
              </div>
            ))}
          </div>
        </div>
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
