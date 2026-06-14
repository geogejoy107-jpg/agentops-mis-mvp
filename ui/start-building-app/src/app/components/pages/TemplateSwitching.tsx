import { useState } from "react";
import { Package, ArrowRight, CheckCircle, XCircle, Lock } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { templatePackages } from "../../data/mockData";

type TargetBase = "notion" | "wb" | "plane" | "docmost";

const targetBases: Record<TargetBase, { name: string; status: string }> = {
  notion:  { name: "Notion", status: "dry_run" },
  wb:      { name: "W&B", status: "planned" },
  plane:   { name: "Plane", status: "planned" },
  docmost: { name: "Docmost", status: "planned" },
};

const fieldMappingTable = [
  { internal: "tasks.title", external: "page.title", migratable: true },
  { internal: "tasks.description", external: "page.content", migratable: true },
  { internal: "tasks.status", external: "select.status", migratable: true },
  { internal: "memories.canonical_text", external: "page.content", migratable: true },
  { internal: "runs.run_id", external: "N/A — stays in core", migratable: false },
  { internal: "tool_calls.*", external: "N/A — stays in core", migratable: false },
  { internal: "approvals.*", external: "N/A — stays in core", migratable: false },
  { internal: "audit_logs.*", external: "N/A — stays in core", migratable: false },
  { internal: "evaluations.*", external: "N/A — stays in core", migratable: false },
];

const coreAlwaysLocal = [
  "Run Ledger", "Tool Call Ledger", "Approval Workflow",
  "Audit Log", "Agent IAM", "Evaluation / Quality Gate",
];

const capabilityGrid = [
  { cap: "Task management", local: true, notion: true, wb: false, plane: true, docmost: false },
  { cap: "Memory storage", local: true, notion: true, wb: false, plane: false, docmost: true },
  { cap: "Artifact export", local: true, notion: true, wb: true, plane: false, docmost: false },
  { cap: "Metrics & charts", local: true, notion: false, wb: true, plane: true, docmost: false },
  { cap: "Webhook integration", local: false, notion: false, wb: true, plane: true, docmost: false },
  { cap: "Audit trail", local: true, notion: false, wb: false, plane: false, docmost: false },
  { cap: "OAuth support", local: false, notion: true, wb: true, plane: true, docmost: true },
];

export function TemplateSwitching() {
  const [selectedTemplate, setSelectedTemplate] = useState(templatePackages[0].template_id);
  const [targetBase, setTargetBase] = useState<TargetBase>("notion");

  const template = templatePackages.find(t => t.template_id === selectedTemplate)!;

  return (
    <div className="space-y-5 max-w-5xl">
      {/* Header */}
      <div>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Template + Base Switching</h1>
        <p className="text-xs mt-0.5" style={{ color: "var(--mis-dim)" }}>
          Choose a template package and preview migration to an external base
        </p>
      </div>

      {/* Template Package selector */}
      <div>
        <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Template Packages</div>
        <div className="grid grid-cols-2 gap-3">
          {templatePackages.map(tpl => (
            <button
              key={tpl.template_id}
              onClick={() => setSelectedTemplate(tpl.template_id)}
              className="text-left p-4 rounded-xl transition-all"
              style={{
                background: selectedTemplate === tpl.template_id ? "rgba(34,211,238,0.08)" : "var(--mis-surface)",
                border: `1px solid ${selectedTemplate === tpl.template_id ? "rgba(34,211,238,0.3)" : "var(--mis-border)"}`,
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <Package size={14} style={{ color: selectedTemplate === tpl.template_id ? "var(--mis-cyan)" : "var(--mis-muted)" }} />
                <span className="text-xs font-semibold" style={{ color: selectedTemplate === tpl.template_id ? "var(--mis-cyan)" : "var(--mis-text)" }}>
                  {tpl.name}
                </span>
                <StatusBadge status={tpl.status} />
              </div>
              <p className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{tpl.description}</p>
              <div className="flex flex-wrap gap-1 mt-2">
                {tpl.agent_roles.map(role => (
                  <span key={role} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
                    {role}
                  </span>
                ))}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Base switching */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-xs font-semibold mb-4" style={{ color: "var(--mis-text)" }}>Base Migration Preview</div>
        <div className="flex items-center gap-4 mb-4">
          {/* Current base */}
          <div
            className="flex-1 p-3 rounded-lg text-center"
            style={{ background: "rgba(42,157,143,0.08)", border: "1px solid rgba(42,157,143,0.2)" }}
          >
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>Current Base</div>
            <div className="text-sm font-semibold mt-0.5" style={{ color: "var(--mis-success)" }}>Agent-MIS Local</div>
            <StatusBadge status="ready" />
          </div>

          <ArrowRight size={18} style={{ color: "var(--mis-border)" }} />

          {/* Target base selector */}
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>Target Base</div>
            <div className="grid grid-cols-2 gap-1.5">
              {(Object.entries(targetBases) as [TargetBase, { name: string; status: string }][]).map(([key, base]) => (
                <button
                  key={key}
                  onClick={() => setTargetBase(key)}
                  className="p-2 rounded-lg text-xs text-center transition-all"
                  style={{
                    background: targetBase === key ? "rgba(46,134,171,0.12)" : "var(--mis-surface2)",
                    border: `1px solid ${targetBase === key ? "rgba(46,134,171,0.3)" : "transparent"}`,
                    color: targetBase === key ? "var(--mis-primary)" : "var(--mis-dim)",
                  }}
                >
                  {base.name}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Non-migratable warning */}
        <div
          className="flex items-start gap-2 text-[11px] px-3 py-2 rounded-lg mb-4"
          style={{ background: "rgba(122,90,248,0.08)", color: "var(--mis-purple)", border: "1px solid rgba(122,90,248,0.2)" }}
        >
          <Lock size={12} className="mt-0.5 shrink-0" />
          <div>
            <span className="font-semibold">Always stays in Agent-MIS Core: </span>
            {coreAlwaysLocal.join(" · ")}
          </div>
        </div>

        {/* Field mapping table */}
        <div className="text-[10px] uppercase tracking-wide mb-2" style={{ color: "var(--mis-muted)" }}>Field Mapping</div>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--mis-muted)" }}>
              {["Internal Field", `→ ${targetBases[targetBase].name}`, "Migratable"].map(h => (
                <th key={h} className="text-left pb-2 font-medium pr-4">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fieldMappingTable.map(row => (
              <tr key={row.internal} style={{ color: "var(--mis-dim)" }}>
                <td className="py-1.5 pr-4 font-mono text-[11px]">{row.internal}</td>
                <td className="py-1.5 pr-4 text-[11px]" style={{ color: row.migratable ? "var(--mis-dim)" : "var(--mis-muted)" }}>
                  {row.external}
                </td>
                <td className="py-1.5 pr-4">
                  {row.migratable
                    ? <CheckCircle size={13} style={{ color: "var(--mis-success)" }} />
                    : <XCircle size={13} style={{ color: "var(--mis-muted)" }} />
                  }
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Capability comparison */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="text-xs font-semibold mb-3" style={{ color: "var(--mis-text)" }}>Capability Comparison</div>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--mis-muted)" }}>
              {["Capability", "Agent-MIS Local", "Notion", "W&B", "Plane", "Docmost"].map(h => (
                <th key={h} className="text-left pb-2 font-medium pr-4">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {capabilityGrid.map(row => (
              <tr key={row.cap}>
                <td className="py-1.5 pr-4 text-xs" style={{ color: "var(--mis-dim)" }}>{row.cap}</td>
                {[row.local, row.notion, row.wb, row.plane, row.docmost].map((has, i) => (
                  <td key={i} className="py-1.5 pr-4">
                    {has
                      ? <CheckCircle size={13} style={{ color: "var(--mis-success)" }} />
                      : <XCircle size={13} style={{ color: "var(--mis-border)" }} />
                    }
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
