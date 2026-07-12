import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, CheckCircle2, ClipboardCheck, Download, FileCheck2,
  LoaderCircle, MonitorCheck, Plus, RefreshCw, ShieldCheck, XCircle,
} from "lucide-react";
import {
  createPrivateHostAcceptanceMarker,
  loadPrivateHostAcceptanceSnapshot,
  type PrivateHostAcceptanceCheckId,
  type PrivateHostAcceptanceMarker,
  type PrivateHostAcceptanceSnapshot,
} from "../../data/liveApi";
import { useHumanAuth } from "../../context/HumanAuthContext";
import { pick, usePreferences } from "../../context/PreferencesContext";

type ManualCheckId = "second_device" | "tailscale_https" | "approved_artifact_download" | "disconnect_reconnect";
type ManualChecks = Record<ManualCheckId, boolean>;

const INITIAL_MANUAL_CHECKS: ManualChecks = {
  second_device: false,
  tailscale_https: false,
  approved_artifact_download: false,
  disconnect_reconnect: false,
};

function newReceiptId() {
  const value = typeof crypto.randomUUID === "function"
    ? crypto.randomUUID().replaceAll("-", "").slice(0, 16)
    : Array.from(crypto.getRandomValues(new Uint8Array(8)), (item) => item.toString(16).padStart(2, "0")).join("");
  return `devchk_${value}`;
}

function downloadJson(filename: string, value: unknown) {
  const blob = new Blob([`${JSON.stringify(value, null, 2)}\n`], { type: "application/json;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function PrivateHostAcceptance() {
  const { locale } = usePreferences();
  const { required, user } = useHumanAuth();
  const [receiptId] = useState(newReceiptId);
  const [snapshot, setSnapshot] = useState<PrivateHostAcceptanceSnapshot | null>(null);
  const [marker, setMarker] = useState<PrivateHostAcceptanceMarker | null>(null);
  const [manualChecks, setManualChecks] = useState<ManualChecks>(INITIAL_MANUAL_CHECKS);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const copy = pick(locale, {
    en: {
      title: "Private Host Device Acceptance",
      subtitle: "Same-origin browser checks for a second-device operator console",
      boundaryTitle: "Non-authoritative browser checklist",
      boundary: "This page proves only what the current browser can observe. The downloaded client receipt is not written as a Host Artifact or authoritative Audit receipt, does not prove a physical second device, and is not the Host authority-ledger acceptance receipt. A Host receipt API will replace it later.",
      refresh: "Refresh checks", createMarker: "Create marker task", creating: "Creating marker",
      automated: "Automated live API checks",
      automatedHint: "Current human Session and same-origin API readability; no Runtime is called.",
      manual: "Manual device attestations",
      manualHint: "Operator-attested only. Browser code cannot reliably prove these conditions.",
      receipt: "Device checklist receipt",
      receiptHint: "Downloads a bounded, non-authoritative client JSON file. It is not written to Artifact or Audit.",
      download: "Download JSON receipt", passed: "Passed", checks: "checks", dataSets: "readable lists",
      marker: "marker", notCreated: "not created", lastChecked: "Last checked", loading: "Checking",
      noRuntime: "No Runtime", liveApi: "Live API", manualLabel: "Manual", error: "Acceptance check failed",
      nonAuthoritative: "non-authoritative",
      humanAuthDisabled: "Human authentication is disabled; this is not a valid Private Host Session acceptance.",
      checkLabels: {
        human_session: "Human authentication and active Session",
        local_readiness: "Local readiness endpoint",
        tasks_readable: "Tasks list",
        evaluations_readable: "Evaluations list",
        approvals_readable: "Approvals list",
        memories_readable: "Memories list",
        audit_readable: "Audit list",
        artifacts_readable: "Artifacts list",
        marker_task_readable: "Acceptance marker task readback",
      } as Record<PrivateHostAcceptanceCheckId, string>,
      manualLabels: {
        second_device: "Opened from a separate physical device",
        tailscale_https: "Address bar shows the expected Tailscale HTTPS origin",
        approved_artifact_download: "Approved artifact download completed on the second device",
        disconnect_reconnect: "Disconnect/reconnect preserved the Host task and Session workflow",
      } as Record<ManualCheckId, string>,
    },
    zh: {
      title: "Private Host 第二设备验收",
      subtitle: "用于第二设备操控台的同源浏览器检查",
      boundaryTitle: "非权威浏览器检查清单",
      boundary: "本页只能证明当前浏览器可观察到的状态。下载的客户端回执不会写成 Host Artifact 或权威 Audit 回执，不能证明真实物理第二设备，也不是 Host 权威账本验收回执；后续将由 Host receipt API 替代。",
      refresh: "刷新检查", createMarker: "创建标记任务", creating: "正在创建标记",
      automated: "自动化实时 API 检查",
      automatedHint: "检查当前人类会话和同源 API 可读性，不调用任何 Runtime。",
      manual: "人工设备确认",
      manualHint: "仅代表操作者人工确认，浏览器代码无法可靠证明这些条件。",
      receipt: "设备检查清单回执",
      receiptHint: "下载一份有边界、非权威的客户端 JSON，不写入 Artifact 或 Audit。",
      download: "下载 JSON 回执", passed: "通过", checks: "项检查", dataSets: "个可读列表",
      marker: "标记任务", notCreated: "尚未创建", lastChecked: "最近检查", loading: "检查中",
      noRuntime: "未调用 Runtime", liveApi: "实时 API", manualLabel: "人工确认", error: "验收检查失败",
      nonAuthoritative: "非权威",
      humanAuthDisabled: "当前未启用人类身份认证，不能作为有效的 Private Host 会话验收。",
      checkLabels: {
        human_session: "人类身份认证与有效会话",
        local_readiness: "本地主机就绪接口",
        tasks_readable: "任务列表",
        evaluations_readable: "评估列表",
        approvals_readable: "审批列表",
        memories_readable: "记忆列表",
        audit_readable: "审计列表",
        artifacts_readable: "产物列表",
        marker_task_readable: "验收标记任务回读",
      } as Record<PrivateHostAcceptanceCheckId, string>,
      manualLabels: {
        second_device: "已从另一台物理设备打开",
        tailscale_https: "地址栏显示预期的 Tailscale HTTPS Origin",
        approved_artifact_download: "已在第二设备完成批准产物下载",
        disconnect_reconnect: "断线重连后 Host 任务与会话流程保持可用",
      } as Record<ManualCheckId, string>,
    },
  });

  const refresh = async (nextMarker = marker) => {
    setLoading(true);
    setError("");
    try {
      setSnapshot(await loadPrivateHostAcceptanceSnapshot(nextMarker ? {
        receipt_id: nextMarker.receipt_id,
        task_id: nextMarker.task_id,
      } : undefined));
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void refresh(null); }, []);

  const createMarker = async () => {
    setCreating(true);
    setError("");
    try {
      const created = await createPrivateHostAcceptanceMarker(receiptId);
      setMarker(created);
      await refresh(created);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setCreating(false);
    }
  };

  const automaticPassed = snapshot?.checks.filter((check) => check.ok).length || 0;
  const manualPassed = Object.values(manualChecks).filter(Boolean).length;
  const readableLists = snapshot ? Object.keys(snapshot.counts).length : 0;
  const receipt = useMemo(() => {
    const checks: Record<string, boolean> = Object.fromEntries((snapshot?.checks || []).map((check) => [check.id, Boolean(check.ok)]));
    for (const [key, value] of Object.entries(manualChecks)) checks[`manual_${key}`] = Boolean(value);
    return {
      receipt_type: "device_checklist_receipt",
      non_authoritative: true,
      receipt_id: receiptId,
      timestamp_utc: snapshot?.checked_at || new Date().toISOString(),
      location_origin: window.location.origin,
      workspace_id: snapshot?.actor.workspace_id || user?.workspace_id || null,
      user: {
        id: snapshot?.actor.user_id || user?.account_id || user?.user_id || null,
        role: snapshot?.actor.role || user?.role || null,
      },
      checks,
      related_ids: { marker_task_id: snapshot?.related_ids.marker_task_id || marker?.task_id || null },
      counts: snapshot?.counts || {},
      labels: { live: "same_origin_browser_api", mock: "not_used", manual: "operator_attested" },
    };
  }, [manualChecks, marker, receiptId, snapshot, user]);

  return (
    <div className="w-full space-y-5" data-testid="private-host-acceptance">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <MonitorCheck size={18} style={{ color: "var(--mis-cyan)" }} />
            <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
          </div>
          <p className="mt-1 text-xs" style={{ color: "var(--mis-dim)" }}>{copy.subtitle}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => void refresh()} disabled={loading}
            className="flex h-8 items-center gap-1.5 rounded px-3 text-[11px] disabled:opacity-50"
            style={{ border: "1px solid var(--mis-border)", background: "var(--mis-surface2)", color: "var(--mis-dim)" }}>
            <RefreshCw size={12} className={loading ? "animate-spin" : ""} />{copy.refresh}
          </button>
          <button type="button" onClick={() => void createMarker()} disabled={creating || Boolean(marker)}
            className="flex h-8 items-center gap-1.5 rounded px-3 text-[11px] font-medium disabled:opacity-50"
            style={{ background: "var(--mis-cyan)", color: "#08131f" }}>
            {creating ? <LoaderCircle size={12} className="animate-spin" /> : <Plus size={12} />}
            {creating ? copy.creating : copy.createMarker}
          </button>
        </div>
      </div>

      <div className="flex items-start gap-3 border px-4 py-3" style={{ borderColor: "rgba(245,158,11,0.35)", background: "rgba(245,158,11,0.08)" }}>
        <AlertTriangle size={16} className="mt-0.5 shrink-0" style={{ color: "var(--mis-warning)" }} />
        <div><div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{copy.boundaryTitle}</div>
          <p className="mt-1 max-w-5xl text-[11px] leading-5" style={{ color: "var(--mis-dim)" }}>{copy.boundary}</p></div>
      </div>

      {error && <div role="alert" className="flex items-center gap-2 border px-3 py-2 text-xs" style={{ borderColor: "rgba(248,113,113,0.4)", color: "#F87171" }}><XCircle size={14} />{copy.error}: {error}</div>}

      <div className="grid grid-cols-2 border md:grid-cols-4" style={{ borderColor: "var(--mis-border)", background: "var(--mis-surface)" }}>
        {[
          { label: copy.passed, value: `${automaticPassed}/${snapshot?.checks.length || 9}`, hint: copy.checks, icon: <ShieldCheck size={14} /> },
          { label: copy.dataSets, value: readableLists, hint: copy.liveApi, icon: <FileCheck2 size={14} /> },
          { label: copy.marker, value: marker?.task_id || copy.notCreated, hint: marker ? receiptId : copy.noRuntime, icon: <ClipboardCheck size={14} /> },
          { label: copy.manualLabel, value: `${manualPassed}/${Object.keys(manualChecks).length}`, hint: copy.manual, icon: <CheckCircle2 size={14} /> },
        ].map((item) => <div key={item.label} className="min-w-0 border-b px-4 py-3 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0" style={{ borderColor: "var(--mis-border)" }}>
          <div className="flex items-center gap-2 text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>{item.icon}{item.label}</div>
          <div className="mt-1 truncate text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{item.value}</div>
          <div className="mt-0.5 text-[10px]" style={{ color: "var(--mis-dim)" }}>{item.hint}</div>
        </div>)}
      </div>

      <section className="border" style={{ borderColor: "var(--mis-border)", background: "var(--mis-surface)" }}>
        <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--mis-border)" }}>
          <div><h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.automated}</h2><p className="mt-0.5 text-[11px]" style={{ color: "var(--mis-dim)" }}>{copy.automatedHint}</p></div>
          <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{copy.lastChecked}: {snapshot?.checked_at ? new Date(snapshot.checked_at).toLocaleString(locale === "zh" ? "zh-CN" : "en-US") : copy.loading}</span>
        </div>
        <div className="divide-y" style={{ borderColor: "var(--mis-border)" }}>
          {(snapshot?.checks || []).map((check) => <div key={check.id} className="grid grid-cols-[22px_minmax(0,1fr)_auto] items-center gap-2 px-4 py-2.5 text-xs" style={{ borderColor: "var(--mis-border)" }}>
            {check.ok ? <CheckCircle2 size={14} style={{ color: "var(--mis-success)" }} /> : <XCircle size={14} style={{ color: "#F87171" }} />}
            <span style={{ color: "var(--mis-text)" }}>{copy.checkLabels[check.id]}</span>
            <span className="max-w-72 truncate text-[10px]" style={{ color: check.ok ? "var(--mis-dim)" : "#F87171" }}>{check.error || `${check.status || (check.ok ? "ok" : "failed")}${check.count !== undefined ? ` · ${check.count}` : ""}`}</span>
          </div>)}
        </div>
      </section>

      <section className="border" style={{ borderColor: "var(--mis-border)", background: "var(--mis-surface)" }}>
        <div className="border-b px-4 py-3" style={{ borderColor: "var(--mis-border)" }}><h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.manual}</h2><p className="mt-0.5 text-[11px]" style={{ color: "var(--mis-dim)" }}>{copy.manualHint}</p></div>
        <div className="divide-y" style={{ borderColor: "var(--mis-border)" }}>
          {(Object.keys(manualChecks) as ManualCheckId[]).map((id) => <label key={id} className="flex cursor-pointer items-center gap-3 px-4 py-3 text-xs" style={{ borderColor: "var(--mis-border)", color: "var(--mis-text)" }}>
            <input type="checkbox" checked={manualChecks[id]} onChange={(event) => setManualChecks((current) => ({ ...current, [id]: event.target.checked }))} className="h-4 w-4 accent-cyan-500" />
            <span className="flex-1">{copy.manualLabels[id]}</span><span className="text-[10px] uppercase" style={{ color: "var(--mis-muted)" }}>{copy.manualLabel}</span>
          </label>)}
        </div>
      </section>

      <section className="flex flex-wrap items-center justify-between gap-3 border px-4 py-3" style={{ borderColor: "var(--mis-border)", background: "var(--mis-surface2)" }}>
        <div className="min-w-0"><div className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--mis-text)" }}><Download size={14} />{copy.receipt}<span className="rounded px-1.5 py-0.5 text-[9px] uppercase" style={{ background: "rgba(245,158,11,0.12)", color: "var(--mis-warning)" }}>{copy.nonAuthoritative}</span></div><p className="mt-1 text-[11px]" style={{ color: "var(--mis-dim)" }}>{copy.receiptHint}</p></div>
        <button type="button" disabled={!snapshot} onClick={() => downloadJson(`device_checklist_receipt-${receiptId}.json`, { ...receipt, timestamp_utc: new Date().toISOString() })} className="flex h-8 items-center gap-1.5 rounded px-3 text-[11px] disabled:opacity-50" style={{ border: "1px solid var(--mis-border)", background: "var(--mis-surface)", color: "var(--mis-text)" }}><Download size={12} />{copy.download}</button>
      </section>

      {!required && <div className="text-[10px]" style={{ color: "var(--mis-warning)" }}>{copy.humanAuthDisabled}</div>}
    </div>
  );
}
