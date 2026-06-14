import { useMemo, useState } from "react";
import { ArrowRight, CheckCircle, Database, Layers3, Lock, Package, ShieldCheck, XCircle } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { templatePackages } from "../../data/mockData";
import { pick, usePreferences } from "../../context/PreferencesContext";

type TargetBase = "notion" | "wb" | "plane" | "docmost";

const targetBases: Record<TargetBase, { name: string; status: string }> = {
  notion: { name: "Notion", status: "dry_run" },
  wb: { name: "W&B", status: "planned" },
  plane: { name: "Plane", status: "planned" },
  docmost: { name: "Docmost", status: "planned" },
};

const fieldMappingTable = [
  { internal: "tasks.title", external: "page.title", migratable: true },
  { internal: "tasks.description", external: "page.content", migratable: true },
  { internal: "tasks.status", external: "select.status", migratable: true },
  { internal: "memories.canonical_text", external: "page.content", migratable: true },
  { internal: "runs.run_id", external: "N/A: stays in core", migratable: false },
  { internal: "tool_calls.*", external: "N/A: stays in core", migratable: false },
  { internal: "approvals.*", external: "N/A: stays in core", migratable: false },
  { internal: "audit_logs.*", external: "N/A: stays in core", migratable: false },
  { internal: "evaluations.*", external: "N/A: stays in core", migratable: false },
];

const coreAlwaysLocal = [
  "Run Ledger",
  "Tool Call Ledger",
  "Approval Workflow",
  "Audit Log",
  "Agent IAM",
  "Evaluation / Quality Gate",
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
  const { locale } = usePreferences();
  const [selectedTemplate, setSelectedTemplate] = useState(templatePackages[0].template_id);
  const [targetBase, setTargetBase] = useState<TargetBase>("notion");

  const template = templatePackages.find(t => t.template_id === selectedTemplate)!;
  const migratableCount = fieldMappingTable.filter(row => row.migratable).length;
  const copy = useMemo(() => pick(locale, {
    en: {
      eyebrow: "Admin Console",
      title: "Template + Base Switching",
      subtitle: "Choose an operating template, preview what can move to an external base, and keep the sensitive AgentOps ledger local.",
      packages: "Template packages",
      currentPlan: "Current migration plan",
      currentBase: "Current base",
      targetBase: "Target base",
      coreProtection: "Core protection",
      coreProtectionBody: "These records stay in AgentOps MIS because they are audit, approval, identity, and quality-gate evidence.",
      fieldMapping: "Field mapping",
      internalField: "Internal field",
      migratable: "Migratable",
      capability: "Capability comparison",
      selectedTemplate: "Selected template",
      migrationMode: "Migration mode",
      protectedObjects: "Protected objects",
      previewOnly: "Preview only",
      ready: "Ready",
      dryRun: "Dry-run",
      planned: "Planned",
      demoChecks: "Demo checks",
      demo1: "Show template choice",
      demo2: "Switch Notion target",
      demo3: "Point out local-only ledger",
      demo4: "Open backend audit if needed",
      protectedCount: "protected tables",
      fieldsReady: "fields ready",
    },
    zh: {
      eyebrow: "后台管理端",
      title: "模板与外部库切换",
      subtitle: "选择运营模板，预览哪些内容能迁移到外部知识库，同时把敏感的 AgentOps 账本留在本地核心。",
      packages: "模板包",
      currentPlan: "当前迁移计划",
      currentBase: "当前本地库",
      targetBase: "目标外部库",
      coreProtection: "核心保护边界",
      coreProtectionBody: "这些记录属于审计、审批、身份和质量门证据，必须保留在 AgentOps MIS 本地核心。",
      fieldMapping: "字段映射",
      internalField: "内部字段",
      migratable: "可迁移",
      capability: "能力对比",
      selectedTemplate: "已选模板",
      migrationMode: "迁移模式",
      protectedObjects: "受保护对象",
      previewOnly: "仅预览",
      ready: "可用",
      dryRun: "安全预演",
      planned: "规划中",
      demoChecks: "录屏检查",
      demo1: "展示模板选择",
      demo2: "切换 Notion 目标",
      demo3: "指出本地账本不外迁",
      demo4: "需要时跳转后台审计",
      protectedCount: "张受保护表",
      fieldsReady: "个字段可迁移",
    },
  }), [locale]);

  return (
    <div className="space-y-4 w-full">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>
            {copy.eyebrow}
          </div>
          <h1 className="text-xl font-semibold mt-1" style={{ color: "var(--mis-text)" }}>
            {copy.title}
          </h1>
          <p className="text-xs mt-1 max-w-3xl" style={{ color: "var(--mis-dim)" }}>
            {copy.subtitle}
          </p>
        </div>

        <div className="grid grid-cols-3 gap-2 min-w-full xl:min-w-[460px]">
          {[
            { label: copy.selectedTemplate, value: template.name, icon: <Package size={14} /> },
            { label: copy.migrationMode, value: targetBases[targetBase].name, icon: <Database size={14} /> },
            { label: copy.protectedObjects, value: `${coreAlwaysLocal.length} ${copy.protectedCount}`, icon: <ShieldCheck size={14} /> },
          ].map(item => (
            <div key={item.label} className="rounded-lg p-2.5" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
              <div className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--mis-muted)" }}>
                <span style={{ color: "var(--mis-cyan)" }}>{item.icon}</span>
                {item.label}
              </div>
              <div className="text-xs font-semibold truncate mt-1" style={{ color: "var(--mis-text)" }}>{item.value}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-12 gap-4 items-start">
        <section className="col-span-12 xl:col-span-8 space-y-4">
          <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between mb-3">
              <div className="text-sm font-semibold flex items-center gap-2" style={{ color: "var(--mis-text)" }}>
                <Layers3 size={15} style={{ color: "var(--mis-cyan)" }} />
                {copy.packages}
              </div>
              <StatusBadge status={template.status} />
            </div>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {templatePackages.map(tpl => (
                <button
                  key={tpl.template_id}
                  onClick={() => setSelectedTemplate(tpl.template_id)}
                  className="text-left p-4 rounded-lg transition-all min-h-[132px]"
                  style={{
                    background: selectedTemplate === tpl.template_id ? "rgba(34,211,238,0.08)" : "var(--mis-surface2)",
                    border: `1px solid ${selectedTemplate === tpl.template_id ? "rgba(34,211,238,0.34)" : "var(--mis-border)"}`,
                  }}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <Package size={14} style={{ color: selectedTemplate === tpl.template_id ? "var(--mis-cyan)" : "var(--mis-muted)" }} />
                    <span className="text-xs font-semibold" style={{ color: selectedTemplate === tpl.template_id ? "var(--mis-cyan)" : "var(--mis-text)" }}>
                      {tpl.name}
                    </span>
                    <StatusBadge status={tpl.status} />
                  </div>
                  <p className="text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{tpl.description}</p>
                  <div className="flex flex-wrap gap-1 mt-2">
                    {tpl.agent_roles.map(role => (
                      <span key={role} className="text-[10px] px-1.5 py-0.5 rounded" style={{ background: "var(--mis-bg)", color: "var(--mis-muted)" }}>
                        {role}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-center justify-between gap-3 mb-4">
              <div className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.fieldMapping}</div>
              <div className="text-[11px]" style={{ color: "var(--mis-muted)" }}>
                {migratableCount} / {fieldMappingTable.length} {copy.fieldsReady}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs min-w-[680px]">
                <thead>
                  <tr style={{ color: "var(--mis-muted)" }}>
                    {[copy.internalField, `→ ${targetBases[targetBase].name}`, copy.migratable].map(h => (
                      <th key={h} className="text-left pb-2 font-medium pr-4">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {fieldMappingTable.map(row => (
                    <tr key={row.internal} style={{ color: "var(--mis-dim)", borderTop: "1px solid var(--mis-border)" }}>
                      <td className="py-2 pr-4 font-mono text-[11px]">{row.internal}</td>
                      <td className="py-2 pr-4 text-[11px]" style={{ color: row.migratable ? "var(--mis-dim)" : "var(--mis-muted)" }}>
                        {row.external}
                      </td>
                      <td className="py-2 pr-4">
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
          </div>
        </section>

        <aside className="col-span-12 xl:col-span-4 space-y-4">
          <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="text-sm font-semibold mb-3" style={{ color: "var(--mis-text)" }}>{copy.currentPlan}</div>
            <div className="flex items-center gap-3 mb-4">
              <div className="flex-1 p-3 rounded-lg text-center" style={{ background: "rgba(42,157,143,0.1)", border: "1px solid rgba(42,157,143,0.24)" }}>
                <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.currentBase}</div>
                <div className="text-sm font-semibold mt-0.5" style={{ color: "var(--mis-success)" }}>Agent-MIS Local</div>
                <StatusBadge status="ready" />
              </div>
              <ArrowRight size={18} style={{ color: "var(--mis-muted)" }} />
              <div className="flex-1 p-3 rounded-lg text-center" style={{ background: "rgba(46,134,171,0.1)", border: "1px solid rgba(46,134,171,0.24)" }}>
                <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{copy.targetBase}</div>
                <div className="text-sm font-semibold mt-0.5" style={{ color: "var(--mis-primary)" }}>{targetBases[targetBase].name}</div>
                <StatusBadge status={targetBases[targetBase].status} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              {(Object.entries(targetBases) as [TargetBase, { name: string; status: string }][]).map(([key, base]) => (
                <button
                  key={key}
                  onClick={() => setTargetBase(key)}
                  className="p-2.5 rounded-lg text-xs text-left transition-all"
                  style={{
                    background: targetBase === key ? "rgba(46,134,171,0.14)" : "var(--mis-surface2)",
                    border: `1px solid ${targetBase === key ? "rgba(46,134,171,0.36)" : "var(--mis-border)"}`,
                    color: targetBase === key ? "var(--mis-primary)" : "var(--mis-dim)",
                  }}
                >
                  <div className="font-semibold">{base.name}</div>
                  <div className="text-[10px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
                    {base.status === "dry_run" ? copy.dryRun : copy.planned}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="flex items-start gap-2">
              <Lock size={14} className="mt-0.5 shrink-0" style={{ color: "var(--mis-purple)" }} />
              <div>
                <div className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.coreProtection}</div>
                <p className="text-[11px] leading-relaxed mt-1" style={{ color: "var(--mis-dim)" }}>
                  {copy.coreProtectionBody}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {coreAlwaysLocal.map(item => (
                <span key={item} className="text-[10px] px-2 py-1 rounded" style={{ background: "rgba(122,90,248,0.1)", color: "var(--mis-purple)" }}>
                  {item}
                </span>
              ))}
            </div>
          </div>

          <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="text-sm font-semibold mb-3" style={{ color: "var(--mis-text)" }}>{copy.demoChecks}</div>
            {[copy.demo1, copy.demo2, copy.demo3, copy.demo4].map((item, index) => (
              <div key={item} className="flex items-center gap-2 py-2" style={{ borderTop: index === 0 ? "0" : "1px solid var(--mis-border)" }}>
                <CheckCircle size={13} style={{ color: "var(--mis-success)" }} />
                <span className="text-[11px]" style={{ color: "var(--mis-dim)" }}>{item}</span>
              </div>
            ))}
          </div>
        </aside>
      </div>

      <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        <div className="text-sm font-semibold mb-3" style={{ color: "var(--mis-text)" }}>{copy.capability}</div>
        <div className="overflow-x-auto">
          <table className="w-full text-xs min-w-[760px]">
            <thead>
              <tr style={{ color: "var(--mis-muted)" }}>
                {["Capability", "Agent-MIS Local", "Notion", "W&B", "Plane", "Docmost"].map(h => (
                  <th key={h} className="text-left pb-2 font-medium pr-4">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {capabilityGrid.map(row => (
                <tr key={row.cap} style={{ borderTop: "1px solid var(--mis-border)" }}>
                  <td className="py-2 pr-4 text-xs" style={{ color: "var(--mis-dim)" }}>{row.cap}</td>
                  {[row.local, row.notion, row.wb, row.plane, row.docmost].map((has, i) => (
                    <td key={i} className="py-2 pr-4">
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
    </div>
  );
}
