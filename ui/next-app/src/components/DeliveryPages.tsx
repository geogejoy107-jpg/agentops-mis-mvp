import Link from "next/link";
import { Archive, ArrowLeft, BarChart3, FileText, ShieldCheck } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type {
  CustomerDeliveryBoardPayload,
  CustomerProjectIndexPayload,
  CustomerProjectReportPayload,
} from "@/lib/mis";

function count(value: unknown) {
  return Number(value || 0);
}

function statusClass(status: string) {
  if (["ready", "completed", "approved", "verified"].includes(status)) return "status statusGood";
  if (["needs_attention", "failed", "blocked", "rejected"].includes(status)) return "status statusBad";
  if (["waiting_approval", "in_progress", "attention", "warning"].includes(status)) return "status statusWarn";
  return "status";
}

function boolText(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function renderMarkdownLine(line: string, index: number) {
  const clean = line.replaceAll("`", "");
  if (line.startsWith("# ")) return <h2 key={index}>{clean.slice(2)}</h2>;
  if (line.startsWith("## ")) return <h3 key={index}>{clean.slice(3)}</h3>;
  if (line.startsWith("### ")) return <h4 key={index}>{clean.slice(4)}</h4>;
  if (line.startsWith("- ")) return <p className="markdownList" key={index}>- {clean.slice(2)}</p>;
  if (!line.trim()) return <div className="markdownGap" key={index} />;
  return <p key={index}>{clean}</p>;
}

export function ReportsParityPage({
  projects,
  projectsError,
  deliveryBoard,
  deliveryBoardError,
}: Readonly<{
  projects: CustomerProjectIndexPayload;
  projectsError?: string | null;
  deliveryBoard: CustomerDeliveryBoardPayload;
  deliveryBoardError?: string | null;
}>) {
  const summary = deliveryBoard.summary || {};
  const projectRows = projects.projects || [];
  const deliveries = deliveryBoard.deliveries || [];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Customer delivery parity route</p>
          <h1>Reports</h1>
          <p className="subtle">Customer delivery reports, archive status, and safe ledger evidence</p>
        </div>
        <Link className="miniButton" href="/workspace">Workspace</Link>
      </header>
      {projectsError ? <div className="banner error">Project index unavailable: {projectsError}</div> : null}
      {deliveryBoardError ? <div className="banner error">Delivery board unavailable: {deliveryBoardError}</div> : null}

      <section className="metrics">
        {[
          ["Deliveries", count(summary.deliveries), "var(--cyan)"],
          ["Ready", count(summary.ready), "var(--green)"],
          ["Waiting approval", count(summary.waiting_approval), "var(--amber)"],
          ["Needs attention", count(summary.needs_attention), "var(--red)"],
        ].map(([label, value, color]) => (
          <div className="metric" key={String(label)}>
            <BarChart3 className="metricIcon" size={17} />
            <span>{label}</span>
            <strong style={{ color: String(color) }}>{value}</strong>
          </div>
        ))}
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><ShieldCheck size={14} /> Customer delivery board</h2>
          <span>{deliveries.length} deliveries · read-only {boolText(deliveryBoard.safety?.read_only)}</span>
        </div>
        <div className="list">
          {deliveries.length ? deliveries.slice(0, 12).map((delivery) => (
            <article className="row tall" key={delivery.delivery_id}>
              <div>
                <strong>{delivery.title}</strong>
                <span>{delivery.artifact_id || delivery.delivery_id} · project {delivery.project_id || "-"}</span>
                <p>{delivery.summary || delivery.next_action || "No delivery summary loaded."}</p>
              </div>
              <div className="rowActions">
                <span className={statusClass(delivery.status)}>{delivery.status}</span>
                <span className="metaPill">approvals {delivery.pending_approval_ids?.length || 0}</span>
                <span className="metaPill">audit {delivery.evidence?.audit_logs || 0}</span>
                {delivery.ui_report_url && <Link className="miniButton good" href={delivery.ui_report_url}>Open report</Link>}
              </div>
            </article>
          )) : <p className="empty">No customer deliveries yet.</p>}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><FileText size={14} /> Customer project reports</h2>
          <span>{projects.total ?? projectRows.length} projects</span>
        </div>
        <div className="list">
          {projectRows.length ? projectRows.map((project) => (
            <Link className="row tall linkRow" href={`/workspace/customer-projects/${encodeURIComponent(project.project_id)}/report`} key={project.project_id}>
              <div>
                <strong>{project.title}</strong>
                <span>{project.project_id} · delivery {project.delivery_artifact_id || "none"}</span>
                <p>{project.report_artifact_id ? `Report artifact ${project.report_artifact_id}` : "Report artifact not archived yet."}</p>
              </div>
              <div className="rowActions">
                <span className={statusClass(project.status)}>{project.status}</span>
                <span className="metaPill">tasks {project.task_count || 0}</span>
                <span className="metaPill">runs {project.run_count || 0}</span>
                <span className="metaPill">pending {project.pending_approvals || 0}</span>
              </div>
            </Link>
          )) : <p className="empty">No customer projects yet.</p>}
        </div>
      </section>
    </AppFrame>
  );
}

export function CustomerProjectReportParityPage({
  projectId,
  report,
  error,
}: Readonly<{ projectId: string; report: CustomerProjectReportPayload | null; error?: string | null }>) {
  const counts = report?.counts || {};
  const safe = report?.safe_defaults || {};
  const execution = report?.execution_evidence || {};
  const manifests = execution.recent_manifests || [];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <Link className="backLink" href="/workspace/reports"><ArrowLeft size={14} /> Reports</Link>
          <p className="eyebrow">Customer project delivery report</p>
          <h1>Delivery Report</h1>
          <p className="subtle">Project {projectId}</p>
        </div>
        {report ? (
          <form method="post" action={`/workspace/customer-projects/${encodeURIComponent(projectId)}/report/archive`}>
            <button className="miniButton good" type="submit">
              <Archive size={13} /> {report.report_artifact_id ? "Refresh archive" : "Archive report"}
            </button>
          </form>
        ) : null}
      </header>
      {error || !report || report.error ? (
        <div className="banner error">{error || report?.error || "Report not found"}</div>
      ) : (
        <>
          <section className="metrics nine">
            {[
              ["Tasks", counts.tasks],
              ["Runs", counts.runs],
              ["Tool calls", counts.tool_calls],
              ["Pending approvals", counts.pending_approvals],
              ["Evaluations", counts.evaluations],
              ["Artifacts", counts.artifacts],
              ["Agent Plans", counts.agent_plans],
              ["Plan Evidence", counts.plan_evidence_manifests],
              ["Verified Evidence", counts.verified_plan_evidence_manifests],
            ].map(([label, value]) => (
              <div className="metric compactMetric" key={String(label)}>
                <span>{label}</span>
                <strong>{count(value)}</strong>
              </div>
            ))}
          </section>

          <section className="grid">
            <div className="panel">
              <div className="panelHeader">
                <h2><ShieldCheck size={14} /> Safety boundary</h2>
              </div>
              <div className="proofStrip">
                <span>external upload {boolText(safe.external_upload_performed)}</span>
                <span>credentials stored {boolText(safe.credentials_stored)}</span>
                <span>raw docs stored {boolText(safe.raw_documents_stored)}</span>
                <span>summary/hash only {boolText(safe.summary_hash_only)}</span>
              </div>
            </div>
            <div className="panel">
              <div className="panelHeader">
                <h2><FileText size={14} /> Ledger index</h2>
                <span>{report.status}</span>
              </div>
              <div className="proofStrip">
                <span>delivery {report.artifact_id || "none"}</span>
                <span>report artifact {report.report_artifact_id || "not archived"}</span>
                <span>approvals {(report.approval_ids || []).length}</span>
              </div>
            </div>
          </section>

          <section className="panel wide">
            <div className="panelHeader">
              <h2><ShieldCheck size={14} /> Agent Plan evidence</h2>
              <span>{count(execution.verified_plan_evidence_manifests)} verified</span>
            </div>
            <div className="proofStrip">
              <span>agent plans {count(execution.agent_plans)}</span>
              <span>manifests {count(execution.plan_evidence_manifests)}</span>
              <span>blocked {count(execution.blocked_plan_evidence_manifests)}</span>
              <span>approval gated {count(execution.approval_gated_tasks)}</span>
              <span>missing plans {count(execution.tasks_missing_agent_plan)}</span>
              <span>low-risk gaps {count(execution.low_risk_tasks_missing_verified_plan_evidence)}</span>
            </div>
            <p className="subtle">{execution.contract || "Agent Gateway evidence contract not loaded."}</p>
            <div className="list compactList">
              {manifests.length ? manifests.map((manifest) => (
                <div className="row" key={manifest.manifest_id || `${manifest.plan_id}:${manifest.run_id}`}>
                  <div>
                    <strong>{manifest.manifest_id || "manifest"}</strong>
                    <span>{manifest.plan_id || "plan"} · {manifest.run_id || "run"} · {manifest.agent_id || "agent"}</span>
                  </div>
                  <div className="rowActions">
                    <span className={statusClass(manifest.status || "unknown")}>{manifest.status || "unknown"}</span>
                    <span className="metaPill">{manifest.mismatch_policy || "policy"}</span>
                    {manifest.manifest_id ? (
                      <Link className="miniButton" href={`/workspace/evidence/${encodeURIComponent(manifest.manifest_id)}`}>Open evidence</Link>
                    ) : null}
                  </div>
                </div>
              )) : <p className="empty">No plan evidence manifests loaded.</p>}
            </div>
          </section>

          <article className="panel wide markdownReport">
            {(report.markdown || "").split("\n").map(renderMarkdownLine)}
          </article>
        </>
      )}
    </AppFrame>
  );
}
