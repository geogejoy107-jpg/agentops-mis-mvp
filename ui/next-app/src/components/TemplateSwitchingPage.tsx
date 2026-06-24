import Link from "next/link";
import { ArrowRight, CheckCircle, Database, Layers3, Lock, Package, ShieldCheck, XCircle } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { BaseCapability, BaseRecord, CustomerTaskTemplateListPayload, TemplateBinding, TemplatePackage } from "@/lib/mis";
import type { ServerLoadResult } from "@/lib/misServer";

type TemplateSwitchingFeedback = {
  previewStatus?: string;
  previewTemplateId?: string;
  previewFromBaseId?: string;
  previewToBaseId?: string;
  migratableCount?: string;
  protectedCount?: string;
  error?: string;
};

type TemplateSwitchingPageProps = {
  templatePackages: ServerLoadResult<TemplatePackage[]>;
  templateBindings: ServerLoadResult<TemplateBinding[]>;
  bases: ServerLoadResult<{ bases: BaseRecord[]; capabilities: BaseCapability[] }>;
  customerTemplates: ServerLoadResult<CustomerTaskTemplateListPayload>;
  selectedTemplateId?: string;
  targetBaseId?: string;
  feedback?: TemplateSwitchingFeedback;
};

const coreAlwaysLocal = [
  "Run Ledger",
  "Tool Call Ledger",
  "Approval Workflow",
  "Audit Log",
  "Agent IAM",
  "Evaluation Gates",
];

const fieldRows = [
  { internal: "tasks.title", external: "page.title", migratable: true },
  { internal: "tasks.description", external: "page.content", migratable: true },
  { internal: "tasks.status", external: "select.status", migratable: true },
  { internal: "tasks.risk_level", external: "select.risk", migratable: true },
  { internal: "memories.canonical_text", external: "page.content", migratable: true },
  { internal: "runs.*", external: "local ledger only", migratable: false },
  { internal: "tool_calls.*", external: "summary/link only", migratable: false },
  { internal: "approvals.*", external: "local authority only", migratable: false },
  { internal: "audit_logs.*", external: "tamper-chain local", migratable: false },
];

const capabilityColumns = [
  "tasks",
  "comments",
  "artifacts",
  "metrics",
  "webhooks",
  "oauth",
  "writeback",
  "permissions",
  "audit",
  "realtime",
] as const;

function statusClass(status?: string | boolean | number | null) {
  const value = String(status ?? "").toLowerCase();
  if (["true", "1", "ok", "ready", "active", "managed", "pass", "created", "preview"].includes(value)) return "status statusGood";
  if (["false", "0", "blocked", "failed", "fail", "error", "unavailable"].includes(value)) return "status statusBad";
  if (["dry_run", "planned", "pending", "preview_only"].includes(value)) return "status statusWarn";
  return "status";
}

function boolText(value: unknown) {
  if (value === true || value === 1) return "true";
  if (value === false || value === 0) return "false";
  return "unknown";
}

function parseList(value?: string) {
  if (!value) return [];
  try {
    const parsed = JSON.parse(value);
    return Array.isArray(parsed) ? parsed.map(String) : [];
  } catch {
    return [];
  }
}

function parseRecord(value?: string) {
  if (!value) return {};
  try {
    const parsed = JSON.parse(value);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : {};
  } catch {
    return {};
  }
}

const fallbackBases: BaseRecord[] = [
  {
    base_id: "base_local_tasks",
    provider: "agent-mis",
    storage_mode: "managed",
    status: "active",
    display_name: "AgentOps MIS Tasks",
  },
  {
    base_id: "base_notion_tasks",
    provider: "notion",
    storage_mode: "external",
    status: "dry_run",
    display_name: "Notion Tasks",
  },
];

function short(value?: string | null) {
  if (!value) return "none";
  return value.length > 22 ? `${value.slice(0, 22)}...` : value;
}

function capabilityEnabled(value: unknown) {
  return value === true || value === 1 || value === "1" || value === "true";
}

function recordText(value: unknown, fallback: string) {
  if (Array.isArray(value)) return value.map(String).join(", ") || fallback;
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function fallbackTemplates(customerTemplates: CustomerTaskTemplateListPayload): TemplatePackage[] {
  return (customerTemplates.templates || []).map((template) => ({
    template_id: template.template_id,
    name: template.name_en || template.name || template.template_id,
    scenario: template.scenario || template.workflow,
    description: template.description || template.default_description,
    status: template.status || "ready",
    agent_roles_json: JSON.stringify(template.agent_roles || []),
    default_bases_json: JSON.stringify({ tasks: "base_local_tasks", memory: "base_local_memory", templates: "base_local_templates" }),
    swappable_bases_json: JSON.stringify({ tasks: ["base_notion_tasks"], memory: ["base_notion_memory"], templates: ["base_notion_templates"] }),
  }));
}

export function TemplateSwitchingPage({
  templatePackages,
  templateBindings,
  bases,
  customerTemplates,
  selectedTemplateId,
  targetBaseId,
  feedback,
}: Readonly<TemplateSwitchingPageProps>) {
  const packages = templatePackages.data.length ? templatePackages.data : fallbackTemplates(customerTemplates.data);
  const baseRows = bases.data.bases?.length ? bases.data.bases : fallbackBases;
  const capabilityRows = bases.data.capabilities || [];
  const bindings = templateBindings.data || [];
  const selectedTemplate = packages.find((template) => template.template_id === selectedTemplateId) || packages[0];
  const localTaskBase = baseRows.find((base) => base.base_id === "base_local_tasks") || baseRows.find((base) => base.storage_mode === "managed") || baseRows[0];
  const targetBase = baseRows.find((base) => base.base_id === targetBaseId)
    || baseRows.find((base) => base.base_id === "base_notion_tasks")
    || baseRows.find((base) => base.storage_mode === "external")
    || baseRows[1]
    || baseRows[0];
  const activeBindings = bindings.filter((binding) => binding.status === "active");
  const dryRunBases = baseRows.filter((base) => base.status === "dry_run").length;
  const externalBases = baseRows.filter((base) => base.storage_mode === "external" || base.provider !== "agent-mis");
  const defaultBases = parseRecord(selectedTemplate?.default_bases_json);
  const swappableBases = parseRecord(selectedTemplate?.swappable_bases_json);
  const roles = parseList(selectedTemplate?.agent_roles_json);
  const packageOptions = packages.length ? packages : [{ template_id: "tpl_ai_software_team", name: "AI software team", status: "ready" }];
  const targetOptions = externalBases.length ? externalBases : baseRows;
  const sourceOptions = baseRows.filter((base) => base.storage_mode === "managed" || base.provider === "agent-mis");
  const previewOk = feedback?.previewStatus === "created";

  return (
    <AppFrame>
      <header className="topbar" data-smoke="template-switching-route">
        <div>
          <p className="eyebrow">Gate 4 template switching parity</p>
          <h1>Template Switching</h1>
          <p className="subtle">Live template package and base-switching readback for the commercial Next.js track.</p>
        </div>
        <Link className="miniButton" href="/workspace/dispatch">Dispatch</Link>
      </header>

      {templatePackages.error ? <div className="banner error">Template packages unavailable: {templatePackages.error}</div> : null}
      {templateBindings.error ? <div className="banner error">Template bindings unavailable: {templateBindings.error}</div> : null}
      {bases.error ? <div className="banner error">Bases unavailable: {bases.error}</div> : null}
      {customerTemplates.error && !templatePackages.data.length ? <div className="banner error">Customer templates unavailable: {customerTemplates.error}</div> : null}
      {feedback?.error ? <div className="banner error">Migration preview failed: {feedback.error}</div> : null}
      {previewOk ? (
        <div className="banner success" data-smoke="template-migration-preview-feedback">
          Migration preview recorded for {feedback.previewTemplateId || selectedTemplate?.template_id || "template"}: {feedback.migratableCount || "0"} migratable objects, {feedback.protectedCount || "0"} protected local objects.
        </div>
      ) : null}

      <section className="metrics six" data-smoke="template-switching-live-read-model">
        {[
          ["Templates", String(packages.length), <Package key="templates" size={18} />, "ready"],
          ["Active bindings", String(activeBindings.length), <Layers3 key="bindings" size={18} />, activeBindings.length ? "active" : "planned"],
          ["Bases", String(baseRows.length), <Database key="bases" size={18} />, baseRows.length ? "ready" : "unavailable"],
          ["Dry-run bases", String(dryRunBases), <ShieldCheck key="dry-run" size={18} />, dryRunBases ? "dry_run" : "planned"],
          ["Protected core", String(coreAlwaysLocal.length), <Lock key="core" size={18} />, "pass"],
          ["Preview", previewOk ? "recorded" : "available", <ArrowRight key="preview" size={18} />, previewOk ? "created" : "preview"],
        ].map(([label, value, icon, status]) => (
          <div className="metric compactMetric" key={String(label)}>
            <span className="metricIcon">{icon}</span>
            <span>{label}</span>
            <strong className="metricText">{String(value)}</strong>
            <span className={statusClass(String(status))}>{String(status)}</span>
          </div>
        ))}
      </section>

      <section className="grid">
        <div className="panel" data-smoke="template-package-catalog">
          <div className="panelHeader">
            <h2><Package size={14} /> Template packages</h2>
            <span>/template-packages</span>
          </div>
          <div className="proofStrip">
            <span>live API readback</span>
            <span>customer fallback {boolText(!templatePackages.data.length && customerTemplates.data.templates?.length)}</span>
            <span>raw documents omitted</span>
          </div>
          <div className="list compact">
            {packageOptions.slice(0, 6).map((template) => {
              const templateRoles = parseList(template.agent_roles_json);
              return (
                <article className="row tall" key={template.template_id}>
                  <div>
                    <strong>{template.name || template.template_id}</strong>
                    <span>{template.template_id} · {template.scenario || "scenario"} · {template.status || "ready"}</span>
                    <p>{template.description || "Template package description unavailable."}</p>
                  </div>
                  <div className="rowActions">
                    <span className="metaPill">roles {templateRoles.length}</span>
                    <span className={statusClass(template.status || "ready")}>{template.status || "ready"}</span>
                  </div>
                </article>
              );
            })}
          </div>
        </div>

        <div className="panel" data-smoke="template-base-switching-plan">
          <div className="panelHeader">
            <h2><Database size={14} /> Base switching plan</h2>
            <span>/bases</span>
          </div>
          <div className="proofStrip">
            <span>source {localTaskBase?.base_id || "base_local_tasks"}</span>
            <span>target {targetBase?.base_id || "base_notion_tasks"}</span>
            <span>preview only</span>
          </div>
          <form className="formGrid" method="post" action="/workspace/templates/migration-preview">
            <label className="field">
              <span>Template</span>
              <select name="template_id" defaultValue={selectedTemplate?.template_id || packageOptions[0]?.template_id}>
                {packageOptions.map((template) => (
                  <option key={template.template_id} value={template.template_id}>{template.name || template.template_id}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Current base</span>
              <select name="from_base_id" defaultValue={localTaskBase?.base_id || "base_local_tasks"}>
                {(sourceOptions.length ? sourceOptions : baseRows).map((base) => (
                  <option key={base.base_id} value={base.base_id}>{base.display_name || base.base_id}</option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Target base</span>
              <select name="to_base_id" defaultValue={targetBase?.base_id || "base_notion_tasks"}>
                {(targetOptions.length ? targetOptions : baseRows).map((base) => (
                  <option key={base.base_id} value={base.base_id}>{base.display_name || base.base_id}</option>
                ))}
              </select>
            </label>
            <button className="miniButton good" type="submit"><ShieldCheck size={13} /> Preview migration</button>
          </form>
        </div>
      </section>

      <section className="grid">
        <div className="panel" data-smoke="template-core-ledger-protection">
          <div className="panelHeader">
            <h2><Lock size={14} /> Core ledger protection</h2>
            <span>local authority</span>
          </div>
          <p className="subtle">Runs, tools, approvals, audits, identity, and quality gates remain in AgentOps MIS even when task or memory summaries are exported.</p>
          <div className="proofStrip">
            {coreAlwaysLocal.map((item) => <span key={item}>{item}</span>)}
          </div>
        </div>

        <div className="panel" data-smoke="template-default-bindings">
          <div className="panelHeader">
            <h2><Layers3 size={14} /> Selected template bindings</h2>
            <span>{selectedTemplate?.template_id || "none"}</span>
          </div>
          <div className="miniMetrics">
            <span>default tasks <strong>{recordText(defaultBases.tasks, "base_local_tasks")}</strong></span>
            <span>default memory <strong>{recordText(defaultBases.memory, "base_local_memory")}</strong></span>
            <span>default templates <strong>{recordText(defaultBases.templates, "base_local_templates")}</strong></span>
            <span>roles <strong>{roles.length}</strong></span>
          </div>
          <div className="list compact">
            {Object.entries(swappableBases).slice(0, 4).map(([slot, value]) => (
              <article className="row" key={slot}>
                <div>
                  <strong>{slot}</strong>
                  <span>{recordText(value, "not configured")}</span>
                </div>
                <span className={statusClass("preview")}>preview</span>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="panel wide" data-smoke="template-field-mapping">
        <div className="panelHeader">
          <h2><ArrowRight size={14} /> Field mapping</h2>
          <span>/migration/preview</span>
        </div>
        <div className="tableWrap">
          <table className="dataTable">
            <thead>
              <tr>
                <th>Internal field</th>
                <th>External mapping</th>
                <th>Migratable</th>
              </tr>
            </thead>
            <tbody>
              {fieldRows.map((row) => (
                <tr key={row.internal}>
                  <td className="mono">{row.internal}</td>
                  <td>{row.external}</td>
                  <td>{row.migratable ? <CheckCircle size={14} color="var(--green)" /> : <XCircle size={14} color="var(--muted)" />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel wide" data-smoke="template-base-capability-comparison">
        <div className="panelHeader">
          <h2><Database size={14} /> Base capability comparison</h2>
          <span>{capabilityRows.length} rows</span>
        </div>
        <div className="tableWrap">
          <table className="dataTable">
            <thead>
              <tr>
                <th>Base</th>
                {capabilityColumns.map((column) => <th key={column}>{column}</th>)}
              </tr>
            </thead>
            <tbody>
              {capabilityRows.length ? capabilityRows.map((capability) => (
                <tr key={capability.base_id}>
                  <td className="mono">{short(capability.base_id)}</td>
                  {capabilityColumns.map((column) => (
                    <td key={`${capability.base_id}:${column}`}>
                      {capabilityEnabled(capability[column]) ? <CheckCircle size={14} color="var(--green)" /> : <XCircle size={14} color="var(--muted)" />}
                    </td>
                  ))}
                </tr>
              )) : (
                <tr><td colSpan={capabilityColumns.length + 1}>No base capabilities loaded.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </AppFrame>
  );
}
