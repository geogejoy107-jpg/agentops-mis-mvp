import { Archive, Database, FileCheck2, ServerCog, ShieldCheck } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type {
  AuditSummary,
  AuditRetentionControlsPayload,
  AuditRetentionPolicyPayload,
  CommercialEntitlementStatus,
  DeploymentReadinessPayload,
  LocalReadinessPayload,
  ReadinessGate,
  SecurityReadinessSummary,
  StorageBackendStatus,
} from "@/lib/mis";

function statusClass(status?: string) {
  if (["pass", "ready", "ok", "healthy", "active"].includes(status || "")) return "status statusGood";
  if (["fail", "blocked", "missing_docs", "unavailable"].includes(status || "")) return "status statusBad";
  if (["warn", "attention", "needs_demo_run", "needs_seed_or_run", "gated"].includes(status || "")) return "status statusWarn";
  return "status";
}

function boolText(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function count(value: unknown) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toLocaleString() : "0";
}

function gateFor(entitlements: CommercialEntitlementStatus, capability: string) {
  return (entitlements.gates || []).find((gate) => gate.capability === capability);
}

function shortPath(value?: string) {
  if (!value) return "not configured";
  const parts = value.split("/");
  return parts.slice(-2).join("/") || value;
}

function routeKey(route: { method?: string; path?: string }) {
  return `${route.method || ""} ${route.path || ""}`.trim();
}

function GateList({ gates }: Readonly<{ gates?: ReadinessGate[] }>) {
  const rows = (gates || []).slice(0, 7);
  if (!rows.length) return <p className="empty">No deployment gates loaded.</p>;
  return (
    <div className="list compactList">
      {rows.map((gate, index) => (
        <div className="row" key={`${gate.id || gate.label || "gate"}:${index}`}>
          <div>
            <strong>{gate.label || gate.id || "Deployment gate"}</strong>
            <span>{gate.detail || gate.summary || gate.next_action || gate.action || "No detail loaded."}</span>
          </div>
          <span className={statusClass(gate.status || (gate.ok ? "pass" : "attention"))}>{gate.status || (gate.ok ? "pass" : "attention")}</span>
        </div>
      ))}
    </div>
  );
}

export function DeploymentParityPage({
  deployment,
  retentionPolicy,
  retentionControls,
  local,
  security,
  entitlements,
  storage,
  audit,
  errors,
}: Readonly<{
  deployment: DeploymentReadinessPayload;
  retentionPolicy?: AuditRetentionPolicyPayload;
  retentionControls?: AuditRetentionControlsPayload;
  local: LocalReadinessPayload;
  security: SecurityReadinessSummary;
  entitlements: CommercialEntitlementStatus;
  storage: StorageBackendStatus;
  audit: AuditSummary[];
  errors?: string[];
}>) {
  const evidence = local.evidence || {};
  const docs = local.docs || [];
  const deploymentChecks = local.deployment_checks || {};
  const deploymentSafety = deployment.safety || {};
  const backupRestore = deployment.backup_restore || {};
  const docIds = new Set(docs.filter((doc) => doc.exists).map((doc) => doc.id));
  const backupDocsReady = ["customer_local_deployment_runbook", "local_backup_utility", "local_backup_smoke", "byoc_deployment_acceptance_smoke"].every((id) => docIds.has(id));
  const signedAuditExportReady = deploymentChecks.signed_audit_export_utility === true && deploymentChecks.signed_audit_export_contract === true;
  const recoveryDrillReady = deploymentChecks.byoc_deployment_acceptance_smoke === true && deploymentChecks.signed_export_tamper_detection === true;
  const postgresBackupUtilityAvailable = backupRestore.postgres_utility_available === true;
  const postgresBackupSmokeAvailable = backupRestore.postgres_smoke_available === true;
  const postgresBackupContractsAvailable = backupRestore.postgres_contracts_available === true;
  const postgresRecoveryAccepted = backupRestore.postgres_acceptance_recorded === true && backupRestore.postgres_acceptance_non_skipped === true;
  const postgresRecoveryStatus = String(backupRestore.postgres_acceptance_status || "not_recorded");
  const postgresSelected = storage.selected_backend === "postgres";
  const backupPanelStatus = postgresSelected ? (postgresRecoveryAccepted ? "ready" : "blocked") : (backupDocsReady ? "ready" : "attention");
  const byocCapabilities = ["postgres_adapter", "sso_hooks", "signed_audit_exports", "custom_connector_sdk"];
  const byocEnabled = byocCapabilities.filter((capability) => entitlements.capabilities?.[capability]).length;
  const retentionGate = gateFor(entitlements, "longer_audit_retention");
  const postgresGate = gateFor(entitlements, "postgres_adapter");
  const signedExportGate = gateFor(entitlements, "signed_audit_exports");
  const ssoGate = gateFor(entitlements, "sso_hooks");
  const connectorGate = gateFor(entitlements, "custom_connector_sdk");
  const storageChecks = Object.entries(storage.checks || {});
  const storageContract = storage.contract || (storage.selected_backend === "postgres" ? "postgres backend gate" : "sqlite free local");
  const storageContracts = storage.contracts || [];
  const runtimeWriteGate = storage.runtime_write_gate || {};
  const runtimeWriteContracts = runtimeWriteGate.contracts || [];
  const expectedRuntimeContracts = [
    "postgres_http_runtime_prepared_action_write_v1",
    "postgres_http_runtime_approval_decision_write_v1",
  ];
  const expectedRuntimeRoutes = [
    { method: "POST", path: "/api/integrations/openclaw/probe", label: "OpenClaw probe" },
    { method: "POST", path: "/api/integrations/hermes/run-task", label: "Hermes run-task" },
    { method: "POST", path: "/api/approvals/:approval_id/approve", label: "Row-gated approval approve" },
  ];
  const runtimeRoutes = runtimeWriteGate.allowlisted_routes || storage.write_allowlist || [];
  const runtimeRouteKeys = new Set(runtimeRoutes.map(routeKey));
  const runtimeContractReady = expectedRuntimeContracts.every((contractId) => runtimeWriteContracts.includes(contractId) || storageContracts.includes(contractId));
  const runtimeRoutesReady = expectedRuntimeRoutes.every((route) => runtimeRouteKeys.has(routeKey(route)));
  const runtimeWriteGateStatus = runtimeWriteGate.status || (runtimeContractReady && runtimeRoutesReady ? "ready" : "gated");
  const retention = deployment.retention || {};
  const enterpriseControls = deployment.enterprise_controls || {};
  const retentionPolicyDetails = retentionPolicy?.policy || {};
  const retentionCounts = retentionPolicy?.counts || {};
  const retentionControlDetails = retentionControls?.controls || {};
  const legalHoldSummary = retentionControls?.legal_hold_summary || {};
  const activeHoldText = legalHoldSummary.cannot_assert_no_holds ? "unknown" : count(legalHoldSummary.active_holds ?? retention.active_legal_holds);

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">BYOC deployment parity route</p>
          <h1>Deployment</h1>
          <p className="subtle">Read-only local-first and BYOC evidence for deployment health, backup, retention, and connector policy</p>
        </div>
        <span className={statusClass(deployment.status || "ready")}>{deployment.status || "read-only"}</span>
      </header>

      {(errors || []).filter(Boolean).map((error) => (
        <div className="banner error" key={error}>Deployment source unavailable: {error}</div>
      ))}

      <section className="metrics">
        {[
          ["Deployment", deployment.status || "unknown"],
          ["Local readiness", local.status || "unknown"],
          ["Production", security.status || "unknown"],
          ["Storage", `${storage.active_backend || "unknown"} / ${storage.selected_backend || "unknown"}`],
          ["BYOC caps", `${byocEnabled}/${byocCapabilities.length}`],
          ["Recovery drill", recoveryDrillReady ? "ready" : "attention"],
          ["PG recovery", postgresRecoveryAccepted ? "ready" : postgresRecoveryStatus],
          ["Signed export", signedAuditExportReady ? "ready" : "attention"],
          ["Token omitted", boolText(local.token_omitted !== false && security.token_omitted !== false)],
        ].map(([label, value]) => (
          <div className="metric compactMetric" key={String(label)}>
            <span>{label}</span>
            <strong>{String(value)}</strong>
          </div>
        ))}
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><ServerCog size={14} /> Deployment readiness verdict</h2>
          <span className={statusClass(deployment.status)}>{deployment.status || "unknown"}</span>
        </div>
        <div className="proofStrip">
          <span>contract {deployment.contract_id || "deployment_readiness_v1"}</span>
          <span>edition {deployment.edition || entitlements.edition || "free_local"}</span>
          <span>deployment ready {boolText(deployment.deployment_ready)}</span>
          <span>read-only {boolText(deploymentSafety.read_only)}</span>
          <span>live execution {boolText(deployment.live_execution_performed)}</span>
          <span>token omitted {boolText(deployment.token_omitted)}</span>
          <span>browser restore {deploymentSafety.browser_restore_write_exposed ? "open" : "closed"}</span>
        </div>
        <GateList gates={deployment.gates} />
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ServerCog size={14} /> Local deployment health</h2>
            <span className={statusClass(local.status)}>{local.status || "unknown"}</span>
          </div>
          <div className="proofStrip">
            <span>workspace {local.workspace_id || "local-demo"}</span>
            <span>live execution {boolText(local.live_execution_performed)}</span>
            <span>closed-loop runs {count(evidence.closed_loop_runs)}</span>
            <span>worker adapter {local.adapter_readiness?.recommended_adapter || "unknown"}</span>
          </div>
          <GateList gates={local.gates} />
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><Archive size={14} /> Backup and restore evidence</h2>
            <span className={statusClass(backupPanelStatus)}>{backupPanelStatus}</span>
          </div>
          <div className="proofStrip">
            <span>runbook {boolText(docIds.has("customer_local_deployment_runbook"))}</span>
            <span>utility {boolText(docIds.has("local_backup_utility"))}</span>
            <span>smoke {boolText(docIds.has("local_backup_smoke"))}</span>
            <span>recovery drill {boolText(recoveryDrillReady)}</span>
            <span>pre-restore copy {boolText(deploymentChecks.overwrite_creates_pre_restore_copy)}</span>
            <span>signed export {boolText(signedAuditExportReady)}</span>
            <span>tamper check {boolText(deploymentChecks.signed_export_tamper_detection)}</span>
            <span>pg utility {boolText(postgresBackupUtilityAvailable)}</span>
            <span>pg smoke {boolText(postgresBackupSmokeAvailable)}</span>
            <span>pg contracts {boolText(postgresBackupContractsAvailable)}</span>
            <span>pg recovery {postgresRecoveryStatus}</span>
            <span>pg non-skipped {boolText(backupRestore.postgres_acceptance_non_skipped)}</span>
            <span>pg current head {boolText(backupRestore.postgres_acceptance_head_current)}</span>
            <span>raw rows printed false</span>
          </div>
          <p className="subtle">
            Backup restore remains CLI-confirmed. Postgres utility files prove availability only; BYOC recovery requires a recorded, non-skipped container acceptance; signed audit export requires a customer key and keeps raw metadata omitted.
          </p>
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Database size={14} /> Storage backend migration gate</h2>
          <span className={statusClass(storage.status)}>{storage.status || "unknown"}</span>
        </div>
        <div className="proofStrip">
          <span>selected {storage.selected_backend || "unknown"}</span>
          <span>active {storage.active_backend || "none"}</span>
          <span>mode {storage.mode || "local"}</span>
          <span>writes allowed {boolText(storage.writes_allowed)}</span>
          <span>fallback {boolText(storage.fallback_performed)}</span>
          <span>contract {storageContract}</span>
        </div>
        <div className="storageGateGrid">
          <div className="storageGateBlock">
            <div className="subHeader">
              <h2>Free Local ledger</h2>
              <span className={statusClass(storage.sqlite?.free_local_default ? "ready" : "attention")}>{storage.sqlite?.free_local_default ? "default" : "not active"}</span>
            </div>
            <div className="proofStrip">
              <span>dependency {storage.sqlite?.dependency || "unknown"}</span>
              <span>db {shortPath(storage.sqlite?.db_path)}</span>
            </div>
          </div>
          <div className="storageGateBlock">
            <div className="subHeader">
              <h2>Postgres BYOC gate</h2>
              <span className={statusClass(storage.postgres?.server_backend_routable ? "ready" : "gated")}>{storage.postgres?.server_backend_routable ? "routable" : storage.reason || "gated"}</span>
            </div>
            <div className="proofStrip">
              <span>dsn {boolText(storage.postgres?.dsn_configured)}</span>
              <span>read-only http {boolText(storage.postgres?.read_only_http_routable)}</span>
              <span>free local dep {boolText(storage.postgres?.free_local_dependency)}</span>
              <span>requires {storage.postgres?.required_edition || storage.required_edition || "enterprise_byoc"}</span>
            </div>
          </div>
          <div className="storageGateBlock storage-runtime-write-contracts">
            <div className="subHeader">
              <h2>Fixed runtime prepared-action writes</h2>
              <span className={statusClass(runtimeWriteGateStatus === "active" ? "ready" : runtimeWriteGateStatus)}>{runtimeWriteGateStatus}</span>
            </div>
            <div className="proofStrip">
              <span>exact resume {boolText(runtimeWriteGate.exact_resume_required)}</span>
              <span>approval {runtimeWriteGate.approval_decision || "row_gated_prepared_action_only"}</span>
              <span>non-fixed runtime {runtimeWriteGate.non_fixed_runtime_writes || "blocked"}</span>
              <span>write http {boolText(storage.postgres?.write_http_routable)}</span>
              <span>routes {runtimeRoutesReady ? "fixed allowlist" : "gated"}</span>
              <span>live execution {boolText(runtimeWriteGate.live_execution_performed)}</span>
            </div>
          </div>
        </div>
        <div className="adapterGrid">
          {expectedRuntimeContracts.map((contractId) => (
            <article className="adapterCard" key={contractId}>
              <div>
                <strong>{contractId}</strong>
                <span>Postgres runtime write contract for Hermes/OpenClaw prepared-action exact resume</span>
              </div>
              <span className={statusClass((runtimeWriteContracts.includes(contractId) || storageContracts.includes(contractId)) ? "ready" : "attention")}>
                {(runtimeWriteContracts.includes(contractId) || storageContracts.includes(contractId)) ? "present" : "missing"}
              </span>
            </article>
          ))}
          {expectedRuntimeRoutes.map((route) => (
            <article className="adapterCard" key={routeKey(route)}>
              <div>
                <strong>{route.label}</strong>
                <span>{routeKey(route)}</span>
              </div>
              <span className={statusClass(runtimeRouteKeys.has(routeKey(route)) ? "ready" : "gated")}>
                {runtimeRouteKeys.has(routeKey(route)) ? "allowlisted" : "closed"}
              </span>
            </article>
          ))}
        </div>
        {storageChecks.length ? (
          <div className="adapterGrid">
            {storageChecks.map(([name, ok]) => (
              <article className="adapterCard" key={name}>
                <div>
                  <strong>{name.replace(/_/g, " ")}</strong>
                  <span>{ok ? "Postgres prerequisite satisfied" : "Postgres prerequisite still closed"}</span>
                </div>
                <span className={statusClass(ok ? "ready" : "attention")}>{ok ? "pass" : "closed"}</span>
              </article>
            ))}
          </div>
        ) : null}
        <p className="subtle">
          {storage.next_proof || "Next proof: keep Python/SQLite as the active provider until Next.js API parity and routed Postgres write-adapter evidence pass."}
        </p>
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><Database size={14} /> Storage and retention</h2>
            <span className={statusClass(postgresGate?.enabled ? "ready" : "gated")}>{postgresGate?.enabled ? "enabled" : "gated"}</span>
          </div>
          <div className="proofStrip">
            <span>sqlite {boolText(entitlements.capabilities?.sqlite_ledger)}</span>
            <span>postgres {boolText(entitlements.capabilities?.postgres_adapter)}</span>
            <span>retention {boolText(entitlements.capabilities?.longer_audit_retention)}</span>
            <span>signed export {boolText(entitlements.capabilities?.signed_audit_exports)}</span>
          </div>
          <div className="proofStrip">
            <span>retention policy {retentionPolicy?.contract_id || retention.contract_id || "audit_retention_policy_v1"}</span>
            <span>preview {retentionPolicy?.entitlement?.enforcement || retention.enforcement || "read_only_preview"}</span>
            <span>days {count(retentionPolicyDetails.retention_days || retention.retention_days)}</span>
            <span>eligible {count(retentionCounts.expired_candidates || retention.expired_candidates)}</span>
            <span>dry-run {boolText(retentionPolicyDetails.dry_run_only ?? retention.dry_run_only)}</span>
            <span>delete supported {boolText(retentionPolicy?.delete_supported)}</span>
            <span>delete performed {boolText(retentionPolicy?.delete_performed ?? retention.delete_performed)}</span>
            <span>rows deleted {count(retentionPolicy?.rows_deleted ?? retention.rows_deleted)}</span>
            <span>raw rows omitted {boolText(retentionPolicyDetails.raw_rows_omitted ?? retention.raw_rows_omitted)}</span>
          </div>
          <div className="proofStrip">
            <span>retention controls {retentionControls?.contract_id || retention.controls_contract_id || "audit_retention_controls_v1"}</span>
            <span>cleanup approval {boolText(retentionControlDetails.cleanup_approval_required ?? retention.cleanup_approval_required)}</span>
            <span>legal hold check {boolText(retentionControlDetails.legal_hold_required_before_cleanup ?? retention.legal_hold_required_before_cleanup)}</span>
            <span>hold registry {boolText(retentionControlDetails.legal_hold_registry_configured ?? retention.legal_hold_registry_configured)}</span>
            <span>active holds {activeHoldText}</span>
            <span>cleanup endpoint {boolText(retentionControlDetails.cleanup_endpoint_exposed ?? retention.cleanup_endpoint_exposed)}</span>
            <span>destructive cleanup {boolText(retentionControlDetails.destructive_cleanup_supported ?? retention.destructive_cleanup_supported)}</span>
          </div>
          <div className="list compactList">
            {[retentionGate, postgresGate, signedExportGate].filter(Boolean).map((gate) => (
              <div className="row" key={gate?.capability}>
                <div>
                  <strong>{gate?.capability?.replace(/_/g, " ")}</strong>
                  <span>requires {gate?.required_edition || "enterprise_byoc"} · {gate?.enforcement || "read_only_preview"}</span>
                </div>
                <span className={statusClass(gate?.enabled ? "ready" : "attention")}>{gate?.enabled ? "enabled" : gate?.status || "disabled"}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> SSO and connector policy</h2>
            <span className={statusClass(connectorGate?.enabled ? "ready" : "gated")}>{connectorGate?.enabled ? "enabled" : "gated"}</span>
          </div>
          <div className="proofStrip">
            <span>sso {boolText(entitlements.capabilities?.sso_hooks)}</span>
            <span>connector sdk {boolText(entitlements.capabilities?.custom_connector_sdk)}</span>
            <span>controls {String(enterpriseControls.status || "unknown")}</span>
            <span>sso configured {boolText(enterpriseControls.sso_configured)}</span>
            <span>private connectors {count(enterpriseControls.private_connector_active)}/{count(enterpriseControls.private_connector_total)}</span>
            <span>raw prompts omitted {boolText(security.safety?.raw_prompt_omitted)}</span>
            <span>token omitted {boolText(security.safety?.token_omitted)}</span>
          </div>
          <div className="list compactList">
            {[ssoGate, connectorGate].filter(Boolean).map((gate) => (
              <div className="row" key={gate?.capability}>
                <div>
                  <strong>{gate?.capability?.replace(/_/g, " ")}</strong>
                  <span>requires {gate?.required_edition || "enterprise_byoc"} · {gate?.enforcement || "read_only_preview"}</span>
                </div>
                <span className={statusClass(gate?.enabled ? "ready" : "attention")}>{gate?.enabled ? "enabled" : gate?.status || "disabled"}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><FileCheck2 size={14} /> Deployment evidence</h2>
          <span>{docs.length} docs/scripts</span>
        </div>
        <div className="adapterGrid">
          {docs.map((doc) => (
            <article className="adapterCard" key={doc.id || doc.path}>
              <div>
                <strong>{doc.id || "deployment evidence"}</strong>
                <span>{doc.path || "path omitted"}</span>
              </div>
              <span className={statusClass(doc.exists ? "ready" : "missing_docs")}>{doc.exists ? "present" : "missing"}</span>
            </article>
          ))}
        </div>
      </section>
    </AppFrame>
  );
}
