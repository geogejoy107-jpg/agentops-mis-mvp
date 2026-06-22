import Link from "next/link";
import { ArrowLeft, GitBranch, ShieldCheck } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { EvidenceDrilldownPayload, VerificationCheck } from "@/lib/mis";

function count(value: unknown) {
  return Array.isArray(value) ? value.length : Number(value || 0);
}

function boolText(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function statusClass(status: string) {
  if (["verified", "ready", "completed", "approved"].includes(status)) return "status statusGood";
  if (["blocked", "failed", "rejected"].includes(status)) return "status statusBad";
  if (["warning", "pending", "submitted", "waiting_approval"].includes(status)) return "status statusWarn";
  return "status";
}

function CheckList({ checks }: Readonly<{ checks: VerificationCheck[] }>) {
  return (
    <div className="list compactList">
      {checks.length ? checks.map((check) => (
        <div className="row" key={check.id || check.message}>
          <div>
            <strong>{check.id || "check"}</strong>
            <span>{check.message || "No check message loaded."}</span>
          </div>
          <span className={statusClass(check.ok ? "verified" : "blocked")}>{check.ok ? "pass" : "fail"}</span>
        </div>
      )) : <p className="empty">No verification checks loaded.</p>}
    </div>
  );
}

export function EvidenceDrilldownPage({
  manifestId,
  evidence,
  error,
}: Readonly<{ manifestId: string; evidence: EvidenceDrilldownPayload; error?: string | null }>) {
  const manifest = evidence.manifest?.manifest;
  const manifestVerification = evidence.manifest?.verification;
  const plan = evidence.plan?.agent_plan;
  const planVerification = evidence.plan?.verification;
  const runGraph = evidence.runGraph || {};

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <Link className="backLink" href="/workspace/reports"><ArrowLeft size={14} /> Reports</Link>
          <p className="eyebrow">Read-only evidence drilldown</p>
          <h1>Evidence Drilldown</h1>
          <p className="subtle">Manifest {manifestId}</p>
        </div>
        <Link className="miniButton" href="/workspace/runs">Run ledger</Link>
      </header>

      {error || evidence.manifest?.error ? (
        <div className="banner error">{error || evidence.manifest?.error || "Evidence unavailable"}</div>
      ) : null}

      <section className="metrics nine">
        {[
          ["Manifest pass", boolText(manifestVerification?.pass)],
          ["Plan pass", boolText(planVerification?.pass)],
          ["Tool calls", count(runGraph.tool_calls)],
          ["Evaluations", count(runGraph.evaluations)],
          ["Artifacts", count(runGraph.artifacts)],
          ["Approvals", count(runGraph.approvals)],
          ["Audit logs", count(runGraph.audit_logs)],
          ["Runtime events", count(runGraph.runtime_events)],
          ["Token omitted", boolText(evidence.manifest?.token_omitted && evidence.plan?.token_omitted && evidence.runGraph?.token_omitted)],
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
            <h2><ShieldCheck size={14} /> Plan evidence manifest</h2>
            <span className={statusClass(manifest?.status || "unknown")}>{manifest?.status || "unknown"}</span>
          </div>
          <div className="proofStrip">
            <span>manifest {manifest?.manifest_id || manifestId}</span>
            <span>plan {manifest?.plan_id || "none"}</span>
            <span>run {manifest?.run_id || "none"}</span>
            <span>task {manifest?.task_id || "none"}</span>
            <span>agent {manifest?.agent_id || "none"}</span>
            <span>policy {manifest?.mismatch_policy || "unknown"}</span>
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><GitBranch size={14} /> Agent Plan</h2>
            <span className={statusClass(plan?.status || "unknown")}>{plan?.status || "unknown"}</span>
          </div>
          <div className="proofStrip">
            <span>plan {plan?.plan_id || "none"}</span>
            <span>risk {plan?.risk_level || "unknown"}</span>
            <span>approval required {boolText(Boolean(plan?.approval_required))}</span>
            <span>agent {plan?.agent_id || "none"}</span>
          </div>
          <p className="subtle">{plan?.task_understanding || "Plan understanding not loaded."}</p>
        </div>
      </section>

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Manifest verification</h2>
            <span>{boolText(manifestVerification?.pass)}</span>
          </div>
          <CheckList checks={manifestVerification?.checks || []} />
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Plan verification</h2>
            <span>{boolText(planVerification?.pass)}</span>
          </div>
          <CheckList checks={planVerification?.checks || []} />
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><GitBranch size={14} /> Run graph</h2>
          <span>{runGraph.run?.run_id || manifest?.run_id || "run"}</span>
        </div>
        <div className="proofStrip">
          <span>task {runGraph.task?.task_id || manifest?.task_id || "none"}</span>
          <span>run status {runGraph.run?.status || "unknown"}</span>
          <span>runtime {runGraph.run?.runtime_type || "unknown"}</span>
          <span>artifact rows {count(runGraph.artifacts)}</span>
          <span>audit rows {count(runGraph.audit_logs)}</span>
        </div>
      </section>
    </AppFrame>
  );
}
