import { useState } from "react";
import { Database, ShieldAlert, ToggleLeft, ToggleRight, Eye, Clock } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { memories, auditLogs } from "../../data/mockData";

type ExportMode = "dry_run_only" | "page_parent" | "database_parent" | "workspace_private";

const modeLabels: Record<ExportMode, string> = {
  dry_run_only: "Dry Run Only",
  page_parent: "Page Parent",
  database_parent: "Database Parent",
  workspace_private: "Workspace Private",
};

const modeDescriptions: Record<ExportMode, string> = {
  dry_run_only: "Preview only. No real write to Notion. Safe default.",
  page_parent: "Export under a specific Notion parent page. Requires NOTION_PARENT_PAGE_ID.",
  database_parent: "Export into a Notion database. Requires NOTION_DATABASE_ID.",
  workspace_private: "Workspace-level private page. Only for public integration bots / personal access tokens.",
};

const notionSyncEvents = auditLogs.filter(a => a.action.startsWith("notion."));
const linkedMemories = memories.filter(m => m.source_type === "notion" || m.memory_type === "artifact_summary").slice(0, 3);

const exportPreview = {
  title: "AgentOps MIS 项目汇报工作台",
  dry_run: true,
  confirm_export: false,
  pages: [
    { title: "Sprint Summary", type: "page", fields: ["task_count", "run_count", "cost_total"] },
    { title: "Memory Candidates", type: "database", fields: ["canonical_text", "confidence", "review_status"] },
    { title: "Agent Performance", type: "page", fields: ["agent_id", "success_rate", "budget_used"] },
  ],
};

export function NotionBase() {
  const [exportMode, setExportMode] = useState<ExportMode>("dry_run_only");
  const [writebackEnabled, setWritebackEnabled] = useState(false);

  return (
    <div className="space-y-5 w-full">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div
          className="w-10 h-10 rounded-xl flex items-center justify-center"
          style={{ background: "rgba(46,134,171,0.15)", color: "var(--mis-primary)" }}
        >
          <Database size={18} />
        </div>
        <div>
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>Notion External Base</h1>
          <p className="text-xs" style={{ color: "var(--mis-dim)" }}>
            External memory/task/template base — not the core ledger
          </p>
        </div>
      </div>

      {/* Security warning */}
      <div
        className="flex items-start gap-3 rounded-xl p-4"
        style={{ background: "rgba(231,111,81,0.07)", border: "1px solid rgba(231,111,81,0.25)" }}
      >
        <ShieldAlert size={16} style={{ color: "var(--mis-warning)", marginTop: 1 }} />
        <div>
          <div className="text-xs font-semibold" style={{ color: "var(--mis-warning)" }}>Security Note</div>
          <p className="text-[11px] mt-0.5" style={{ color: "var(--mis-dim)" }}>
            If a Notion integration token is leaked, rotate it immediately in your Notion workspace settings.
            This system never stores or exposes the raw token value. Only structural metadata and hashes are recorded.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Config panel */}
        <div
          className="rounded-xl p-4 space-y-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Configuration</div>

          {/* Token status */}
          <div>
            <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>Integration Token</div>
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: "var(--mis-surface2)" }}>
              <span className="text-xs font-mono" style={{ color: "var(--mis-dim)" }}>secret_••••••••••••••••</span>
              <StatusBadge status="ready" />
            </div>
          </div>

          {/* Export mode */}
          <div>
            <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>Export Mode</div>
            <div className="space-y-1.5">
              {(Object.keys(modeLabels) as ExportMode[]).map(mode => (
                <button
                  key={mode}
                  onClick={() => setExportMode(mode)}
                  className="w-full text-left p-2.5 rounded-lg transition-colors"
                  style={{
                    background: exportMode === mode ? "rgba(46,134,171,0.12)" : "var(--mis-surface2)",
                    border: `1px solid ${exportMode === mode ? "rgba(46,134,171,0.3)" : "transparent"}`,
                  }}
                >
                  <div className="text-xs font-medium" style={{ color: exportMode === mode ? "var(--mis-primary)" : "var(--mis-text)" }}>
                    {modeLabels[mode]}
                  </div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
                    {modeDescriptions[mode]}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Writeback toggle */}
          <div>
            <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>Writeback</div>
            <button
              onClick={() => setWritebackEnabled(v => !v)}
              className="flex items-center gap-2 text-xs"
              style={{ color: writebackEnabled ? "var(--mis-warning)" : "var(--mis-dim)" }}
            >
              {writebackEnabled
                ? <ToggleRight size={20} style={{ color: "var(--mis-warning)" }} />
                : <ToggleLeft size={20} style={{ color: "var(--mis-muted)" }} />
              }
              {writebackEnabled ? "Enabled — confirm_export required" : "Disabled (default)"}
            </button>
            {writebackEnabled && (
              <div
                className="mt-2 text-[11px] px-3 py-2 rounded"
                style={{ background: "rgba(231,111,81,0.1)", color: "var(--mis-warning)", border: "1px solid rgba(231,111,81,0.2)" }}
              >
                Real write enabled. POST body must include <code>confirm_export: true</code>.
              </div>
            )}
          </div>
        </div>

        {/* Export Preview */}
        <div
          className="rounded-xl p-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="flex items-center gap-1.5 mb-3">
            <Eye size={13} style={{ color: "var(--mis-cyan)" }} />
            <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Export Preview</span>
            <StatusBadge status="dry_run" />
          </div>
          <div
            className="rounded-lg p-3 font-mono text-[11px] overflow-auto max-h-48"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)" }}
          >
            <div style={{ color: "var(--mis-muted)" }}>// Dry-run preview — no real write</div>
            <div className="mt-1">{`{`}</div>
            <div className="ml-3">{`"title": "${exportPreview.title}",`}</div>
            <div className="ml-3">{`"dry_run": ${exportPreview.dry_run},`}</div>
            <div className="ml-3">{`"confirm_export": ${exportPreview.confirm_export},`}</div>
            <div className="ml-3">{`"pages": [`}</div>
            {exportPreview.pages.map((p, i) => (
              <div key={i} className="ml-6">
                {`{ "title": "${p.title}", "type": "${p.type}" }${i < exportPreview.pages.length - 1 ? "," : ""}`}
              </div>
            ))}
            <div className="ml-3">{`]`}</div>
            <div>{`}`}</div>
          </div>

          {/* Linked memories */}
          <div className="mt-4">
            <div className="text-[10px] uppercase tracking-wide mb-2" style={{ color: "var(--mis-muted)" }}>Linked Memory Objects</div>
            <div className="space-y-1.5">
              {memories.filter(m => m.review_status === "approved").map(m => (
                <div key={m.memory_id} className="flex items-center gap-2 text-[11px]">
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: "var(--mis-success)" }} />
                  <span className="truncate" style={{ color: "var(--mis-dim)" }}>{m.canonical_text.slice(0, 50)}…</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Sync Events */}
      <div
        className="rounded-xl p-4"
        style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      >
        <div className="flex items-center gap-1.5 mb-3">
          <Clock size={13} style={{ color: "var(--mis-primary)" }} />
          <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>Sync Events</span>
        </div>
        {notionSyncEvents.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--mis-muted)" }}>No sync events recorded.</p>
        ) : (
          <div className="space-y-2">
            {notionSyncEvents.map(log => (
              <div
                key={log.audit_id}
                className="flex items-center justify-between py-2"
                style={{ borderBottom: "1px solid var(--mis-border)" }}
              >
                <div>
                  <span className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{log.action}</span>
                  <span className="text-[11px] ml-2" style={{ color: "var(--mis-muted)" }}>{log.metadata_json}</span>
                </div>
                <span className="text-[11px] shrink-0" style={{ color: "var(--mis-muted)" }}>
                  {new Date(log.created_at).toLocaleString()}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
