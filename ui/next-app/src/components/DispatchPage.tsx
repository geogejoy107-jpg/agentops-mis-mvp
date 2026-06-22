import Link from "next/link";
import { LockKeyhole, Play, ShieldCheck, Workflow } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { CommercialEntitlementStatus, CustomerTaskTemplateListPayload } from "@/lib/mis";

type DispatchFeedback = {
  status?: string;
  capability?: string;
  requiredEdition?: string;
  currentEdition?: string;
  projectId?: string;
  error?: string;
};

function boolText(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function gateFor(entitlements: CommercialEntitlementStatus, capability: string) {
  return (entitlements.gates || []).find((gate) => gate.capability === capability);
}

export function DispatchParityPage({
  entitlements,
  entitlementsError,
  templates,
  templatesError,
  feedback,
}: Readonly<{
  entitlements: CommercialEntitlementStatus;
  entitlementsError?: string | null;
  templates: CustomerTaskTemplateListPayload;
  templatesError?: string | null;
  feedback?: DispatchFeedback;
}>) {
  const reportTemplateGate = gateFor(entitlements, "report_templates");
  const reportTemplatesEnabled = Boolean(entitlements.capabilities?.report_templates);
  const rows = templates.templates || [];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Customer dispatch parity route</p>
          <h1>Dispatch</h1>
          <p className="subtle">Template-backed customer work entry with commercial fail-closed gates</p>
        </div>
        <Link className="miniButton" href="/workspace/reports">Reports</Link>
      </header>

      {entitlementsError ? <div className="banner error">Entitlements unavailable: {entitlementsError}</div> : null}
      {templatesError ? <div className="banner error">Templates unavailable: {templatesError}</div> : null}
      {feedback?.status === "blocked" ? (
        <div className="banner warn">
          <strong>Entitlement required:</strong> {feedback.capability || "report_templates"} requires {feedback.requiredEdition || "pro_workspace"}; current edition is {feedback.currentEdition || entitlements.edition || "free_local"}.
        </div>
      ) : null}
      {feedback?.status === "started" && feedback.projectId ? (
        <div className="banner success">
          Customer project started: <Link href={`/workspace/customer-projects/${encodeURIComponent(feedback.projectId)}/report`}>{feedback.projectId}</Link>
        </div>
      ) : null}
      {feedback?.error ? <div className="banner error">Dispatch failed: {feedback.error}</div> : null}

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Edition gate</h2>
            <span>{entitlements.edition_label || entitlements.edition || "Free Local"}</span>
          </div>
          <div className="proofStrip">
            <span>report_templates {boolText(reportTemplatesEnabled)}</span>
            <span>required {reportTemplateGate?.required_edition || "pro_workspace"}</span>
            <span>billing call {boolText(entitlements.safety?.billing_call_performed)}</span>
            <span>token omitted {boolText(entitlements.token_omitted)}</span>
          </div>
        </div>
        <div className="panel">
          <div className="panelHeader">
            <h2><LockKeyhole size={14} /> Safety contract</h2>
            <span>{reportTemplatesEnabled ? "enabled" : "fail-closed"}</span>
          </div>
          <p className="subtle">
            Free Local can inspect templates and reports, but template execution is blocked until the report_templates capability is enabled.
          </p>
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Workflow size={14} /> Customer task templates</h2>
          <span>{rows.length} templates</span>
        </div>
        <div className="list">
          {rows.length ? rows.map((template) => (
            <article className="row tall" key={template.template_id}>
              <div>
                <strong>{template.name_en || template.name || template.template_id}</strong>
                <span>{template.template_id} · {template.workflow || "workflow"} · {template.status || "status unknown"}</span>
                <p>{template.description || template.default_description || "No template description loaded."}</p>
              </div>
              <div className="rowActions">
                <span className="metaPill">risk {template.risk_level || "medium"}</span>
                <span className="metaPill">approvals {(template.required_approvals || []).length}</span>
                <form method="post" action="/workspace/dispatch/template-run">
                  <input type="hidden" name="template_id" value={template.template_id} />
                  <button className={`miniButton ${reportTemplatesEnabled ? "good" : ""}`} type="submit">
                    <Play size={13} /> Start template
                  </button>
                </form>
              </div>
            </article>
          )) : <p className="empty">No customer task templates loaded.</p>}
        </div>
      </section>
    </AppFrame>
  );
}
