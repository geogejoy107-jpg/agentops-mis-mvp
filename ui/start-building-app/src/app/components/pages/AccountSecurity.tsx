import { useCallback, useEffect, useMemo, useState } from "react";
import { Ban, CheckCircle2, LoaderCircle, LogOut, Monitor, RefreshCw, ShieldCheck } from "lucide-react";
import {
  loadHumanBrowserSessions,
  revokeHumanBrowserSession,
  type HumanBrowserSession,
  type HumanBrowserSessionsPayload,
} from "../../data/liveApi";
import { useHumanAuth } from "../../context/HumanAuthContext";
import { pick, usePreferences } from "../../context/PreferencesContext";

function formatDate(value: string | null | undefined, locale: "zh" | "en") {
  if (!value) return "-";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString(locale === "zh" ? "zh-CN" : "en-US");
}

function statusColor(status: HumanBrowserSession["status"]) {
  if (status === "active") return "var(--mis-success)";
  if (status === "expired") return "var(--mis-warning)";
  return "var(--mis-muted)";
}

export function AccountSecurity() {
  const { locale } = usePreferences();
  const { required, user, logout } = useHumanAuth();
  const [payload, setPayload] = useState<HumanBrowserSessionsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  const copy = pick(locale, {
    zh: {
      title: "账户与访问",
      subtitle: "管理这台主机上的账户和浏览器会话",
      account: "当前账户",
      accountHint: "人类浏览器账户与 Agent 机器凭据相互独立。",
      name: "显示名称",
      username: "用户名",
      role: "角色",
      workspace: "工作区",
      sessions: "浏览器会话",
      sessionsHint: "查看并撤销其他已登录浏览器。系统不采集 IP 或 User-Agent。",
      active: "有效",
      total: "总计",
      revoked: "已撤销",
      expired: "已过期",
      current: "当前会话",
      otherSession: "其他浏览器会话",
      created: "创建时间",
      lastSeen: "最近活动",
      expires: "到期时间",
      revoke: "撤销",
      revokeOther: "撤销其他会话",
      refresh: "刷新",
      signOut: "退出当前会话",
      confirmOne: "确定撤销这个浏览器会话吗？该浏览器需要重新登录。",
      confirmOther: "确定撤销除当前浏览器之外的所有会话吗？",
      ownerOnly: "只有 Owner 可以查看和撤销浏览器会话。",
      authDisabled: "当前主机未启用人类身份认证。",
      empty: "没有可显示的浏览器会话。",
      safeRef: "安全引用",
      boundary: "Cookie、原始 Session ID、Session Hash 和 Token 不会显示在此页面或写入审计元数据。",
    },
    en: {
      title: "Account and access",
      subtitle: "Manage the account and browser sessions on this host",
      account: "Current account",
      accountHint: "Human browser accounts remain separate from Agent machine credentials.",
      name: "Display name",
      username: "Username",
      role: "Role",
      workspace: "Workspace",
      sessions: "Browser sessions",
      sessionsHint: "Review and revoke other signed-in browsers. IP and User-Agent data are not collected.",
      active: "Active",
      total: "total",
      revoked: "Revoked",
      expired: "Expired",
      current: "Current session",
      otherSession: "Other browser session",
      created: "Created",
      lastSeen: "Last active",
      expires: "Expires",
      revoke: "Revoke",
      revokeOther: "Revoke other sessions",
      refresh: "Refresh",
      signOut: "Sign out current session",
      confirmOne: "Revoke this browser session? That browser will need to sign in again.",
      confirmOther: "Revoke every browser session except the current one?",
      ownerOnly: "Only an Owner can view and revoke browser sessions.",
      authDisabled: "Human authentication is not enabled on this host.",
      empty: "No browser sessions to display.",
      safeRef: "Safe reference",
      boundary: "Cookies, raw Session IDs, Session hashes, and tokens are never displayed here or written to audit metadata.",
    },
  });

  const canManageSessions = required && user?.role === "owner";

  const refresh = useCallback(async () => {
    if (!canManageSessions) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError("");
    try {
      setPayload(await loadHumanBrowserSessions());
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setLoading(false);
    }
  }, [canManageSessions]);

  useEffect(() => { void refresh(); }, [refresh]);

  const activeOtherCount = useMemo(
    () => payload?.sessions.filter((session) => session.status === "active" && !session.current).length || 0,
    [payload],
  );

  const revoke = async (sessionRef?: string) => {
    const allOther = !sessionRef;
    if (!window.confirm(allOther ? copy.confirmOther : copy.confirmOne)) return;
    setBusy(sessionRef || "all_other");
    setError("");
    try {
      await revokeHumanBrowserSession(allOther ? { all_other: true } : { session_ref: sessionRef });
      await refresh();
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : String(nextError));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="max-w-6xl space-y-6" data-testid="account-security-page">
      <header className="border-b pb-4" style={{ borderColor: "var(--mis-border)" }}>
        <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{copy.title}</h1>
        <p className="mt-1 text-xs" style={{ color: "var(--mis-dim)" }}>{copy.subtitle}</p>
      </header>

      <section className="grid gap-5 lg:grid-cols-[220px_minmax(0,680px)] lg:gap-10" data-testid="account-profile-section">
        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.account}</h2>
          <p className="mt-1.5 text-xs leading-5" style={{ color: "var(--mis-dim)" }}>{copy.accountHint}</p>
        </div>
        <dl className="border-t text-xs" style={{ borderColor: "var(--mis-border)" }}>
          {[
            [copy.name, user?.display_name || "-"],
            [copy.username, user?.username || "-"],
            [copy.role, user?.role || "-"],
            [copy.workspace, user?.workspace_id || "-"],
          ].map(([label, value]) => (
            <div key={label} className="grid gap-1 border-b py-3 md:grid-cols-[180px_minmax(0,1fr)]" style={{ borderColor: "var(--mis-border)" }}>
              <dt style={{ color: "var(--mis-muted)" }}>{label}</dt>
              <dd className="font-medium" style={{ color: "var(--mis-text)" }}>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="grid gap-5 lg:grid-cols-[220px_minmax(0,680px)] lg:gap-10" data-testid="browser-session-section">
        <div>
          <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{copy.sessions}</h2>
          <p className="mt-1.5 text-xs leading-5" style={{ color: "var(--mis-dim)" }}>{copy.sessionsHint}</p>
          {payload && (
            <p className="mt-2 text-[11px]" style={{ color: "var(--mis-muted)" }}>
              {payload.active_count} {copy.active} · {payload.session_count} {copy.total}
            </p>
          )}
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b pb-3" style={{ borderColor: "var(--mis-border)" }}>
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--mis-dim)" }}>
              <ShieldCheck size={15} style={{ color: "var(--mis-success)" }} />
              {canManageSessions ? copy.sessions : required ? copy.ownerOnly : copy.authDisabled}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void refresh()}
                disabled={!canManageSessions || loading}
                className="inline-flex h-8 w-8 items-center justify-center rounded border disabled:opacity-50"
                style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)", background: "var(--mis-surface)" }}
                title={copy.refresh}
                aria-label={copy.refresh}
              >
                <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
              </button>
              <button
                type="button"
                onClick={() => void revoke()}
                disabled={!canManageSessions || activeOtherCount === 0 || Boolean(busy)}
                className="inline-flex h-8 items-center gap-1.5 rounded border px-2.5 text-xs disabled:opacity-50"
                style={{ borderColor: "var(--mis-border)", color: "var(--mis-warning)", background: "var(--mis-surface)" }}
              >
                {busy === "all_other" ? <LoaderCircle size={14} className="animate-spin" /> : <Ban size={14} />}
                {copy.revokeOther}
              </button>
            </div>
          </div>

          {error && <div role="alert" className="border-b py-3 text-xs" style={{ borderColor: "var(--mis-border)", color: "var(--mis-warning)" }}>{error}</div>}
          {loading ? (
            <div className="flex items-center gap-2 border-b py-5 text-xs" style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)" }}>
              <LoaderCircle size={15} className="animate-spin" /> {copy.refresh}
            </div>
          ) : canManageSessions && payload?.sessions.length ? (
            <div>
              {payload.sessions.map((session) => (
                <article key={session.session_ref} className="border-b py-4" style={{ borderColor: "var(--mis-border)" }} data-testid="browser-session-row">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Monitor size={15} style={{ color: statusColor(session.status) }} />
                        <span className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
                          {session.current ? copy.current : copy.otherSession}
                        </span>
                        <span className="text-[10px] font-medium uppercase" style={{ color: statusColor(session.status) }}>
                          {copy[session.status]}
                        </span>
                      </div>
                      <div className="mt-2 text-[11px]" style={{ color: "var(--mis-muted)" }}>
                        {copy.safeRef}: <code>{session.session_ref}</code>
                      </div>
                    </div>
                    {session.current ? (
                      <span className="inline-flex items-center gap-1.5 text-[11px]" style={{ color: "var(--mis-success)" }}>
                        <CheckCircle2 size={13} /> {copy.current}
                      </span>
                    ) : session.status === "active" ? (
                      <button
                        type="button"
                        onClick={() => void revoke(session.session_ref)}
                        disabled={Boolean(busy)}
                        className="inline-flex h-8 items-center gap-1.5 rounded border px-2.5 text-xs disabled:opacity-50"
                        style={{ borderColor: "var(--mis-border)", color: "var(--mis-warning)", background: "var(--mis-surface)" }}
                      >
                        {busy === session.session_ref ? <LoaderCircle size={14} className="animate-spin" /> : <Ban size={14} />}
                        {copy.revoke}
                      </button>
                    ) : null}
                  </div>
                  <dl className="mt-3 grid gap-2 text-[11px] sm:grid-cols-3">
                    <div><dt style={{ color: "var(--mis-muted)" }}>{copy.created}</dt><dd className="mt-0.5" style={{ color: "var(--mis-dim)" }}>{formatDate(session.created_at, locale)}</dd></div>
                    <div><dt style={{ color: "var(--mis-muted)" }}>{copy.lastSeen}</dt><dd className="mt-0.5" style={{ color: "var(--mis-dim)" }}>{formatDate(session.last_seen_at, locale)}</dd></div>
                    <div><dt style={{ color: "var(--mis-muted)" }}>{copy.expires}</dt><dd className="mt-0.5" style={{ color: "var(--mis-dim)" }}>{formatDate(session.expires_at, locale)}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          ) : canManageSessions ? (
            <div className="border-b py-5 text-xs" style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)" }}>{copy.empty}</div>
          ) : null}

          <div className="flex flex-wrap items-center justify-between gap-3 pt-4">
            <p className="max-w-xl text-[11px] leading-5" style={{ color: "var(--mis-muted)" }}>{copy.boundary}</p>
            {required && (
              <button
                type="button"
                onClick={() => void logout()}
                className="inline-flex h-8 items-center gap-1.5 rounded border px-2.5 text-xs"
                style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)", background: "var(--mis-surface)" }}
              >
                <LogOut size={14} /> {copy.signOut}
              </button>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
