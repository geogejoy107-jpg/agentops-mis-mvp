import { useState } from "react";
import { Database, ShieldAlert, ToggleLeft, ToggleRight, Eye, Clock } from "lucide-react";
import { StatusBadge } from "../shared/StatusBadge";
import { memories, auditLogs } from "../../data/mockData";
import { pick, usePreferences } from "../../context/PreferencesContext";

type ExportMode = "dry_run_only" | "page_parent" | "database_parent" | "workspace_private";

const modeLabels: Record<ExportMode, { en: string; zh: string }> = {
  dry_run_only: { en: "Dry Run Only", zh: "仅安全预演" },
  page_parent: { en: "Page Parent", zh: "父页面导出" },
  database_parent: { en: "Database Parent", zh: "数据库导出" },
  workspace_private: { en: "Workspace Private", zh: "工作区私有页" },
};

const modeDescriptions: Record<ExportMode, { en: string; zh: string }> = {
  dry_run_only: {
    en: "Preview only. No real write to Notion. Safe default.",
    zh: "只生成预览，不真实写入 Notion，是默认安全模式。",
  },
  page_parent: {
    en: "Export under a specific Notion parent page. Requires NOTION_PARENT_PAGE_ID.",
    zh: "导出到指定 Notion 父页面下，需要配置 NOTION_PARENT_PAGE_ID。",
  },
  database_parent: {
    en: "Export into a Notion database. Requires NOTION_DATABASE_ID.",
    zh: "导出到 Notion 数据库中，需要配置 NOTION_DATABASE_ID。",
  },
  workspace_private: {
    en: "Workspace-level private page. Only for public integration bots / personal access tokens.",
    zh: "创建工作区级私有页，仅适合公开集成机器人或个人访问令牌。",
  },
};

const notionSyncEvents = auditLogs.filter(a => a.action.startsWith("notion."));
const linkedMemories = memories.filter(m => m.source_type === "notion" || m.memory_type === "artifact_summary").slice(0, 3);

function notionActionLabel(action: string, locale: "en" | "zh") {
  const labels: Record<string, { en: string; zh: string }> = {
    "notion.dry_run_export": { en: "Notion dry-run export", zh: "Notion 安全预演导出" },
    "notion.export": { en: "Notion export", zh: "Notion 真实导出" },
    "notion.status": { en: "Notion status check", zh: "Notion 状态检查" },
  };
  return pick(locale, labels[action] ?? { en: action, zh: action });
}

function notionMetadataSummary(metadataJson: string, locale: "en" | "zh") {
  try {
    const metadata = JSON.parse(metadataJson) as Record<string, unknown>;
    const dryRun = metadata.dry_run === true;
    const confirmed = metadata.confirm_export === true;
    if (locale === "zh") {
      return `${dryRun ? "安全预演" : "真实写入"} · ${confirmed ? "已确认导出" : "未确认导出"}`;
    }
    return `${dryRun ? "dry-run" : "real write"} · ${confirmed ? "confirmed" : "not confirmed"}`;
  } catch {
    return metadataJson;
  }
}

export function NotionBase() {
  const { locale } = usePreferences();
  const [exportMode, setExportMode] = useState<ExportMode>("dry_run_only");
  const [writebackEnabled, setWritebackEnabled] = useState(false);
  const copy = pick(locale, {
    en: {
      title: "Notion External Base",
      subtitle: "External memory/task/template base, not the core ledger",
      securityTitle: "Security Note",
      securityBody:
        "If a Notion integration token is leaked, rotate it immediately in your Notion workspace settings. This system never stores or exposes the raw token value. Only structural metadata and hashes are recorded.",
      configuration: "Configuration",
      integrationToken: "Integration Token",
      exportMode: "Export Mode",
      writeback: "Writeback",
      writebackEnabled: "Enabled, confirm_export required",
      writebackDisabled: "Disabled (default)",
      writebackWarning: "Real write enabled. POST body must include confirm_export: true.",
      exportPreview: "Export Preview",
      dryRunComment: "// Dry-run preview, no real write",
      linkedMemoryObjects: "Linked Memory Objects",
      syncEvents: "Sync Events",
      noSyncEvents: "No sync events recorded.",
      previewTitle: "AgentOps MIS Project Reporting Workspace",
      previewPages: [
        { title: "Sprint Summary", type: "page" },
        { title: "Memory Candidates", type: "database" },
        { title: "Agent Performance", type: "page" },
      ],
      pageType: "page",
      databaseType: "database",
      tokenMask: "secret_••••••••••••••••",
    },
    zh: {
      title: "Notion 外部库",
      subtitle: "用于同步记忆、任务和模板，不替代核心运行账本",
      securityTitle: "安全提示",
      securityBody:
        "如果 Notion 集成令牌泄露，请立刻在 Notion 工作区设置中轮换。系统不会保存或展示原始 token，只记录结构化元数据和 hash。",
      configuration: "连接配置",
      integrationToken: "集成令牌",
      exportMode: "导出模式",
      writeback: "真实写回",
      writebackEnabled: "已开启，需要 confirm_export 确认",
      writebackDisabled: "已关闭（默认）",
      writebackWarning: "真实写入已开启，请求体必须包含 confirm_export: true。",
      exportPreview: "导出预览",
      dryRunComment: "// 安全预演，不会真实写入",
      linkedMemoryObjects: "关联记忆对象",
      syncEvents: "同步事件",
      noSyncEvents: "暂无同步事件。",
      previewTitle: "AgentOps MIS 项目汇报工作台",
      previewPages: [
        { title: "冲刺摘要", type: "页面" },
        { title: "记忆候选库", type: "数据库" },
        { title: "AI 员工绩效摘要", type: "页面" },
      ],
      pageType: "页面",
      databaseType: "数据库",
      tokenMask: "secret_••••••••••••••••",
    },
  });

  const exportPreview = {
    title: copy.previewTitle,
    dry_run: true,
    confirm_export: false,
    pages: copy.previewPages,
  };

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
          <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
          <p className="text-xs" style={{ color: "var(--mis-dim)" }}>
            {copy.subtitle}
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
          <div className="text-xs font-semibold" style={{ color: "var(--mis-warning)" }}>{copy.securityTitle}</div>
          <p className="text-[11px] mt-0.5" style={{ color: "var(--mis-dim)" }}>
            {copy.securityBody}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Config panel */}
        <div
          className="rounded-xl p-4 space-y-4"
          style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
        >
          <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{copy.configuration}</div>

          {/* Token status */}
          <div>
            <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>{copy.integrationToken}</div>
            <div className="flex items-center gap-2 px-3 py-2 rounded-lg" style={{ background: "var(--mis-surface2)" }}>
              <span className="text-xs font-mono" style={{ color: "var(--mis-dim)" }}>{copy.tokenMask}</span>
              <StatusBadge status="ready" />
            </div>
          </div>

          {/* Export mode */}
          <div>
            <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>{copy.exportMode}</div>
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
                    {pick(locale, modeLabels[mode])}
                  </div>
                  <div className="text-[11px] mt-0.5" style={{ color: "var(--mis-muted)" }}>
                    {pick(locale, modeDescriptions[mode])}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Writeback toggle */}
          <div>
            <div className="text-[10px] uppercase tracking-wide mb-1.5" style={{ color: "var(--mis-muted)" }}>{copy.writeback}</div>
            <button
              onClick={() => setWritebackEnabled(v => !v)}
              className="flex items-center gap-2 text-xs"
              style={{ color: writebackEnabled ? "var(--mis-warning)" : "var(--mis-dim)" }}
            >
              {writebackEnabled
                ? <ToggleRight size={20} style={{ color: "var(--mis-warning)" }} />
                : <ToggleLeft size={20} style={{ color: "var(--mis-muted)" }} />
              }
              {writebackEnabled ? copy.writebackEnabled : copy.writebackDisabled}
            </button>
            {writebackEnabled && (
              <div
                className="mt-2 text-[11px] px-3 py-2 rounded"
                style={{ background: "rgba(231,111,81,0.1)", color: "var(--mis-warning)", border: "1px solid rgba(231,111,81,0.2)" }}
              >
                {copy.writebackWarning}
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
            <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{copy.exportPreview}</span>
            <StatusBadge status="dry_run" />
          </div>
          <div
            className="rounded-lg p-3 font-mono text-[11px] overflow-auto max-h-48"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)" }}
          >
            <div style={{ color: "var(--mis-muted)" }}>{copy.dryRunComment}</div>
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
            <div className="text-[10px] uppercase tracking-wide mb-2" style={{ color: "var(--mis-muted)" }}>{copy.linkedMemoryObjects}</div>
            <div className="space-y-1.5">
              {linkedMemories.map(m => (
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
          <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{copy.syncEvents}</span>
        </div>
        {notionSyncEvents.length === 0 ? (
          <p className="text-xs" style={{ color: "var(--mis-muted)" }}>{copy.noSyncEvents}</p>
        ) : (
          <div className="space-y-2">
            {notionSyncEvents.map(log => (
              <div
                key={log.audit_id}
                className="flex items-center justify-between py-2"
                style={{ borderBottom: "1px solid var(--mis-border)" }}
              >
                <div>
                  <span className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{notionActionLabel(log.action, locale)}</span>
                  <span className="text-[11px] ml-2" style={{ color: "var(--mis-muted)" }}>{notionMetadataSummary(log.metadata_json, locale)}</span>
                </div>
                <span className="text-[11px] shrink-0" style={{ color: "var(--mis-muted)" }}>
                  {new Date(log.created_at).toLocaleString(locale === "zh" ? "zh-CN" : "en-US")}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
