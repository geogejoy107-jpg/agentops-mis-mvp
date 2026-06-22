"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Database, Eye, RefreshCw, ShieldAlert, UploadCloud } from "lucide-react";
import { AppFrame } from "./AppFrame";
import {
  loadAudit,
  loadNotionPreview,
  runNotionConfirmedExport,
  runNotionDryRunExport,
  type AuditSummary,
  type NotionExportResult,
  type NotionPreview,
} from "@/lib/mis";

type LoadState = {
  audit: AuditSummary[];
  error: string | null;
  loading: boolean;
  preview: NotionPreview | null;
};

function booleanText(value: unknown) {
  return value ? "true" : "false";
}

function statusClass(status?: string) {
  if (["ready", "dry_run", "configured"].includes(status || "")) return "status statusGood";
  if (["blocked", "failed", "error"].includes(status || "")) return "status statusBad";
  return "status statusWarn";
}

function formatDate(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function safeExcerpt(markdown?: string) {
  const text = (markdown || "").replace(/\s+/g, " ").trim();
  return text ? `${text.slice(0, 420)}${text.length > 420 ? "..." : ""}` : "No preview markdown loaded.";
}

export function NotionExternalBaseParityPage() {
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [exportResult, setExportResult] = useState<NotionExportResult | null>(null);
  const [state, setState] = useState<LoadState>({ audit: [], error: null, loading: true, preview: null });

  const refresh = async () => {
    setState((current) => ({ ...current, error: null, loading: true }));
    try {
      const [preview, audit] = await Promise.all([loadNotionPreview(), loadAudit()]);
      setState({
        audit: audit.filter((item) => item.action.startsWith("notion.") || item.entity_id === "notion"),
        error: null,
        loading: false,
        preview,
      });
    } catch (err) {
      setState({ audit: [], error: err instanceof Error ? err.message : String(err), loading: false, preview: null });
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const status = state.preview?.status || {};
  const connectors = status.connectors || [];
  const counts = useMemo(() => {
    return {
      dryRunConnectors: connectors.filter((connector) => connector.dry_run_default).length,
      writebackConnectors: connectors.filter((connector) => connector.writeback_allowed).length,
    };
  }, [connectors]);

  const runDryRun = async () => {
    setActionBusy("dry_run");
    setExportResult(null);
    try {
      setExportResult(await runNotionDryRunExport());
      await refresh();
    } finally {
      setActionBusy(null);
    }
  };

  const runConfirmed = async () => {
    setActionBusy("confirmed");
    setExportResult(null);
    try {
      setExportResult(await runNotionConfirmedExport());
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setExportResult({
        provider: "notion",
        created: false,
        error: message.includes("entitlement_required") || message.includes("403") ? "entitlement_required" : message,
        capability: message.includes("notion_confirmed_export") ? "notion_confirmed_export" : undefined,
        billing_call_performed: false,
        live_execution_performed: false,
        token_omitted: true,
      });
    } finally {
      setActionBusy(null);
    }
  };

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Next.js parity route</p>
          <h1>Notion External Base</h1>
          <p className="subtle">
            dry-run default {booleanText(status.dry_run_default)} · writeback allowed {booleanText(status.writeback_allowed)} · export mode {status.export_mode || "dry_run"}
          </p>
        </div>
        <button className="iconButton" onClick={refresh} disabled={state.loading || Boolean(actionBusy)} aria-label="Refresh Notion external base">
          <RefreshCw size={17} className={state.loading ? "spin" : ""} />
        </button>
      </header>

      {state.error ? <div className="banner error">MIS API unavailable through /api/mis/integrations/notion: {state.error}</div> : null}

      <section className="banner warn">
        <ShieldAlert size={16} />
        Notion is an external presentation base, not the canonical run ledger. Raw tokens, raw prompts, raw responses, and private transcripts stay omitted.
      </section>

      {exportResult ? (
        <div className={`banner ${exportResult.error ? "error" : "success"}`}>
          {exportResult.error === "entitlement_required" ? "entitlement_required: notion_confirmed_export requires pro_workspace; billing call false; live execution false; token omitted true" : null}
          {!exportResult.error && exportResult.dry_run ? `dry-run export created no external page; sync event ${exportResult.sync_event_id || "-"}` : null}
          {!exportResult.error && exportResult.created ? "confirmed export created external page through prepared action" : null}
        </div>
      ) : null}

      <section className="metricGrid">
        <article className="metric">
          <span><Database size={15} />Configuration</span>
          <strong>{status.configured ? "configured" : "dry_run"}</strong>
          <small>token raw value omitted</small>
        </article>
        <article className="metric">
          <span><ShieldAlert size={15} />Writeback</span>
          <strong>{booleanText(status.writeback_allowed)}</strong>
          <small>confirm_export required before real write</small>
        </article>
        <article className="metric">
          <span><Eye size={15} />Preview</span>
          <strong>{state.preview?.report?.block_count || 0}</strong>
          <small>Notion blocks, no provider write</small>
        </article>
      </section>

      <div className="grid">
        <section className="panel">
          <div className="panelHeader">
            <div>
              <strong>External base safety</strong>
              <span>notion_confirmed_export stays fail-closed in Free Local</span>
            </div>
            <span className={statusClass(status.configured ? "configured" : "dry_run")}>{status.configured ? "configured" : "dry_run"}</span>
          </div>
          <div className="miniMetrics">
            <span className="metaPill">has token {booleanText(status.has_token)}</span>
            <span className="metaPill">parent page {booleanText(status.has_parent_page_id)}</span>
            <span className="metaPill">database {booleanText(status.has_database_id)}</span>
            <span className="metaPill">workspace private {booleanText(status.workspace_private_export)}</span>
            <span className="metaPill">version {status.notion_version || "-"}</span>
          </div>
          <p className="subtle">Last sync {formatDate(status.last_sync)} · Last error {status.last_error || "-"}</p>
          <div className="approvalActions">
            <form className="inlineForm" method="post" action="/workspace/external-bases/notion/export">
              <input type="hidden" name="mode" value="dry_run" />
              <button
                className="miniButton good"
                disabled={Boolean(actionBusy)}
                onClick={(event) => {
                  event.preventDefault();
                  void runDryRun();
                }}
                type="submit"
              >
                <Eye size={13} />Run dry-run export
              </button>
            </form>
            <form className="inlineForm" method="post" action="/workspace/external-bases/notion/export">
              <input type="hidden" name="mode" value="confirmed" />
              <button
                className="miniButton bad"
                disabled={Boolean(actionBusy)}
                onClick={(event) => {
                  event.preventDefault();
                  void runConfirmed();
                }}
                type="submit"
              >
                <UploadCloud size={13} />Confirm export
              </button>
            </form>
          </div>
        </section>

        <section className="panel">
          <div className="panelHeader">
            <div>
              <strong>Export Preview</strong>
              <span>{state.preview?.write_behavior || "preview only; no external write"}</span>
            </div>
            <span className="status statusGood">preview only</span>
          </div>
          <p className="subtle">{state.preview?.report?.title || "AgentOps MIS Project Reporting Workspace"}</p>
          <p>{safeExcerpt(state.preview?.report?.markdown)}</p>
          <div className="miniMetrics">
            <span className="metaPill">{state.preview?.tasks?.length || 0} tasks</span>
            <span className="metaPill">{state.preview?.memory_candidates?.length || 0} memory candidates</span>
            <span className="metaPill">raw token omitted true</span>
          </div>
        </section>
      </div>

      <div className="tableWrap">
        <table className="dataTable">
          <thead>
            <tr>
              <th>Connector</th>
              <th>Status</th>
              <th>Dry Run</th>
              <th>Writeback</th>
              <th>Auth</th>
              <th>Last Checked</th>
            </tr>
          </thead>
          <tbody>
            {connectors.map((connector) => (
              <tr key={connector.connector_id}>
                <td className="mono">{connector.connector_id}<span>{connector.base_id}</span></td>
                <td><span className={statusClass(connector.status)}>{connector.status || "unknown"}</span></td>
                <td>{booleanText(connector.dry_run_default)}</td>
                <td>{booleanText(connector.writeback_allowed)}</td>
                <td>{connector.auth_type || "-"}</td>
                <td>{formatDate(connector.last_checked_at || connector.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {!connectors.length ? <p className="empty tableEmpty">No Notion connectors loaded.</p> : null}
      </div>

      <section className="panel wide">
        <div className="panelHeader">
          <div>
            <strong>Sync Events</strong>
            <span>Notion audit evidence, provider payload hashes only</span>
          </div>
          <span className="status">append-only</span>
        </div>
        <div className="list compact">
          {state.audit.slice(0, 8).map((audit) => (
            <article className="row" key={audit.audit_id}>
              <div>
                <strong>{audit.action}</strong>
                <span>{audit.entity_type}:{audit.entity_id}</span>
              </div>
              <span className="metaPill">{formatDate(audit.created_at)}</span>
            </article>
          ))}
          {!state.audit.length ? (
            <div className="emptyState">
              <AlertTriangle size={24} />
              <p>No Notion sync events recorded.</p>
            </div>
          ) : null}
        </div>
      </section>
    </AppFrame>
  );
}
