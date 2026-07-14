import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
} from "lucide-react";
import {
  bootstrapHuman,
  getHumanAuthStatus,
  HUMAN_AUTH_UNAUTHORIZED_EVENT,
  loginHuman,
  logoutHuman,
  setHumanAuthCsrf,
  type HumanAuthStatus,
} from "../../data/liveApi";
import { HumanAuthContext } from "../../context/HumanAuthContext";
import { pick, usePreferences } from "../../context/PreferencesContext";
import { AppShell } from "../layout/AppShell";
import { WorkspaceSettingsPage, WorkspaceSettingsSection } from "../shared/WorkspaceSettings";

type GateState = "checking" | "login" | "bootstrap" | "ready" | "unavailable";
type OwnerSetupHandoff = { seen: boolean; value: string };

function errorCode(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const match = message.match(/"error"\s*:\s*"([^"]+)"/);
  return match?.[1] || "unknown";
}

function consumeOwnerSetupHandoff(): OwnerSetupHandoff {
  if (typeof window === "undefined" || !window.location.hash) return { seen: false, value: "" };
  const params = new URLSearchParams(window.location.hash.slice(1));
  const supplied = params.get("agentops-owner-setup");
  if (supplied === null) return { seen: false, value: "" };
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}`);
  return {
    seen: true,
    value: /^[A-Za-z0-9_-]{16,256}$/.test(supplied) ? supplied : "",
  };
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { locale } = usePreferences();
  const [gate, setGate] = useState<GateState>("checking");
  const [status, setStatus] = useState<HumanAuthStatus | null>(null);
  const [username, setUsername] = useState("");
  const [initialSetupHandoff] = useState(consumeOwnerSetupHandoff);
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [setupCode, setSetupCode] = useState(initialSetupHandoff.value);
  const [setupHandoffActive, setSetupHandoffActive] = useState(Boolean(initialSetupHandoff.value));
  const [displayName, setDisplayName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setGate("checking");
    setError("");
    try {
      const next = await getHumanAuthStatus();
      setStatus(next);
      if (!next.required || next.authenticated) setGate("ready");
      else setGate(next.bootstrap_required ? "bootstrap" : "login");
    } catch (nextError) {
      setError(authErrorMessage(errorCode(nextError), locale));
      setGate("unavailable");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const handleSetupHandoff = () => {
      const next = consumeOwnerSetupHandoff();
      if (!next.seen) return;
      if (gate !== "checking" && gate !== "bootstrap") {
        setSetupCode("");
        setSetupHandoffActive(false);
        return;
      }
      setSetupCode(next.value);
      setSetupHandoffActive(Boolean(next.value));
      setError(next.value ? "" : authErrorMessage("invalid_setup_code", locale));
    };
    window.addEventListener("hashchange", handleSetupHandoff);
    return () => window.removeEventListener("hashchange", handleSetupHandoff);
  }, [gate, locale]);

  useEffect(() => {
    const handleUnauthorized = () => {
      setHumanAuthCsrf(null);
      setStatus((current) => current ? { ...current, authenticated: false, user: undefined } : current);
      setGate("login");
      setError(pick(locale, {
        zh: "登录已过期，请重新登录。",
        en: "Your session expired. Please sign in again.",
      }));
    };
    window.addEventListener(HUMAN_AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
    return () => window.removeEventListener(HUMAN_AUTH_UNAUTHORIZED_EVENT, handleUnauthorized);
  }, [locale]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (gate === "bootstrap" && password !== confirmPassword) {
      setError(pick(locale, { zh: "两次输入的密码不一致。", en: "The passwords do not match." }));
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const session = gate === "bootstrap"
        ? await bootstrapHuman({ setup_code: setupCode, username, password, display_name: displayName || undefined })
        : await loginHuman({ username, password });
      setStatus({ required: true, authenticated: true, bootstrap_required: false, user: session.user });
      setPassword("");
      setConfirmPassword("");
      setSetupCode("");
      setSetupHandoffActive(false);
      setGate("ready");
    } catch (nextError) {
      const code = errorCode(nextError);
      if (!["weak_password", "invalid_username"].includes(code)) {
        setSetupCode("");
        setSetupHandoffActive(false);
      }
      setError(authErrorMessage(code, locale));
    } finally {
      setSubmitting(false);
    }
  };

  const logout = useCallback(async () => {
    try {
      await logoutHuman();
    } finally {
      setHumanAuthCsrf(null);
      setStatus((current) => current ? { ...current, authenticated: false, user: undefined } : current);
      setGate("login");
    }
  }, []);

  const contextValue = useMemo(() => ({
    required: Boolean(status?.required),
    user: status?.user || null,
    logout,
  }), [logout, status]);

  if (gate === "ready") {
    return <HumanAuthContext.Provider value={contextValue}>{children}</HumanAuthContext.Provider>;
  }

  const isBootstrap = gate === "bootstrap";
  const hasInstallerHandoff = isBootstrap && setupHandoffActive;
  const lockLabel = pick(locale, {
    zh: gate === "checking" ? "正在连接" : isBootstrap ? "需要初始化" : "需要登录",
    en: gate === "checking" ? "Connecting" : isBootstrap ? "Setup required" : "Sign-in required",
  });
  const pageTitle = pick(locale, {
    zh: "账户与访问",
    en: "Account and access",
  });
  const pageSubtitle = pick(locale, {
    zh: isBootstrap ? "完成本地主机的首次设置" : "登录后继续使用当前工作区",
    en: isBootstrap ? "Complete first-time setup for this local host" : "Sign in to continue to this workspace",
  });

  return (
    <HumanAuthContext.Provider value={contextValue}>
      <AppShell locked lockLabel={lockLabel}>
        <WorkspaceSettingsPage
          testId="human-auth-workspace-gate"
          title={pageTitle}
          subtitle={pageSubtitle}
        >
          <WorkspaceSettingsSection
            testId="human-auth-settings-layout"
            title={pick(locale, { zh: isBootstrap ? "首位所有者" : "工作区登录", en: isBootstrap ? "First owner" : "Workspace sign-in" })}
            description={pick(locale, {
              zh: isBootstrap ? "为这台主机创建管理员账户。以后在其他电脑上也使用这个账户登录。" : "使用这台主机上的账户进入工作区。",
              en: isBootstrap ? "Create the administrator account for this host. Use it to sign in from your other computers." : "Use an account on this host to enter the workspace.",
            })}
            meta={(
              <p data-testid="human-auth-host-boundary" className="mt-3 flex items-center gap-1.5 text-[11px]" style={{ color: "var(--mis-muted)" }}>
                <LockKeyhole size={11} aria-hidden="true" />
                {pick(locale, { zh: "数据保留在本地主机", en: "Data stays on this host" })}
              </p>
            )}
          >
            <div data-testid="human-auth-access-panel">
              {gate === "checking" ? (
                <div className="flex min-h-32 items-center gap-2.5 border-y text-xs" style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)" }}>
                  <LoaderCircle className="animate-spin" size={17} aria-hidden="true" />
                  {pick(locale, { zh: "正在验证主机会话...", en: "Checking host session..." })}
                </div>
              ) : gate === "unavailable" ? (
                <div className="border-y py-5" style={{ borderColor: "var(--mis-border)" }}>
                  <h3 className="text-sm font-semibold">{pick(locale, { zh: "无法连接本地主机", en: "Cannot reach local host" })}</h3>
                  <p className="mt-2 text-xs leading-5" style={{ color: "var(--mis-dim)" }}>{error}</p>
                  <button
                    type="button"
                    onClick={() => void refresh()}
                    className="mt-4 inline-flex h-9 items-center justify-center gap-2 rounded px-3 text-xs font-semibold"
                    style={{ background: "var(--mis-cyan)", color: "var(--mis-bg)" }}
                  >
                    <RefreshCw size={15} aria-hidden="true" />
                    {pick(locale, { zh: "重新连接", en: "Retry connection" })}
                  </button>
                </div>
              ) : (
                <form onSubmit={submit} data-testid="human-auth-workspace-form">
                  <div className="divide-y border-y" style={{ borderColor: "var(--mis-border)" }}>
                    {isBootstrap && !hasInstallerHandoff && (
                      <AuthField
                        label={pick(locale, { zh: "主机设置码", en: "Host setup code" })}
                        hint={pick(locale, { zh: "安装时生成的一次性凭据", en: "One-time credential from installation" })}
                        value={setupCode}
                        onChange={setSetupCode}
                        type="password"
                        autoComplete="one-time-code"
                      />
                    )}
                    {hasInstallerHandoff && (
                      <div
                        data-testid="owner-setup-handoff-ready"
                        className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-3 py-3 text-xs sm:grid-cols-[160px_minmax(0,1fr)]"
                      >
                        <span className="font-medium" style={{ color: "var(--mis-text)" }}>{pick(locale, { zh: "主机设置码", en: "Host setup code" })}</span>
                        <span className="flex items-center gap-2" style={{ color: "var(--mis-success)" }}>
                          <CheckCircle2 size={14} aria-hidden="true" />
                          {pick(locale, { zh: "已从本机安装器安全接收", en: "Securely received from the local installer" })}
                        </span>
                      </div>
                    )}
                    {isBootstrap && (
                      <AuthField
                        label={pick(locale, { zh: "显示名称", en: "Display name" })}
                        value={displayName}
                        onChange={setDisplayName}
                        autoComplete="name"
                        required={false}
                      />
                    )}
                    <AuthField
                      label={pick(locale, { zh: "用户名", en: "Username" })}
                      hint={isBootstrap ? pick(locale, { zh: "3–64 位小写字母、数字或 . _ -", en: "3–64 lowercase letters, digits, or . _ -" }) : undefined}
                      value={username}
                      onChange={setUsername}
                      autoComplete="username"
                      pattern={isBootstrap ? "[a-z0-9][a-z0-9._-]{2,63}" : undefined}
                    />
                    <AuthField
                      label={pick(locale, { zh: "密码", en: "Password" })}
                      hint={isBootstrap ? pick(locale, { zh: "至少 12 个字符", en: "At least 12 characters" }) : undefined}
                      value={password}
                      onChange={setPassword}
                      type="password"
                      autoComplete={isBootstrap ? "new-password" : "current-password"}
                      minLength={isBootstrap ? 12 : undefined}
                    />
                    {isBootstrap && (
                      <AuthField
                        label={pick(locale, { zh: "确认密码", en: "Confirm password" })}
                        value={confirmPassword}
                        onChange={setConfirmPassword}
                        type="password"
                        autoComplete="new-password"
                        minLength={12}
                      />
                    )}
                  </div>

                  {error && (
                    <div
                      role="alert"
                      className="border-b px-3 py-2.5 text-xs"
                      style={{ borderColor: "rgba(231,111,81,0.4)", color: "var(--mis-warning)" }}
                    >
                      {error}
                    </div>
                  )}

                  <div className="flex justify-end pt-4">
                    <button
                      disabled={submitting}
                      className="inline-flex h-9 w-full items-center justify-center gap-2 rounded px-4 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:min-w-40"
                      style={{ background: "var(--mis-cyan)", color: "var(--mis-bg)" }}
                    >
                      {submitting ? <LoaderCircle className="animate-spin" size={16} aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}
                      {pick(locale, { zh: isBootstrap ? "创建所有者并进入" : "登录工作台", en: isBootstrap ? "Create owner and continue" : "Enter workspace" })}
                    </button>
                  </div>
                </form>
              )}
            </div>
          </WorkspaceSettingsSection>
        </WorkspaceSettingsPage>
      </AppShell>
    </HumanAuthContext.Provider>
  );
}

function AuthField({
  label,
  hint,
  value,
  onChange,
  type = "text",
  autoComplete,
  required = true,
  minLength,
  pattern,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete: string;
  required?: boolean;
  minLength?: number;
  pattern?: string;
}) {
  return (
    <label className="grid grid-cols-[120px_minmax(0,1fr)] items-center gap-3 py-3 text-xs sm:grid-cols-[160px_minmax(0,1fr)]">
      <span className="min-w-0">
        <span className="block font-medium" style={{ color: "var(--mis-text)" }}>{label}</span>
        {hint && <span className="mt-0.5 block text-[10px] font-normal" style={{ color: "var(--mis-muted)" }}>{hint}</span>}
      </span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        required={required}
        minLength={minLength}
        pattern={pattern}
        className="h-9 w-full min-w-0 rounded border px-3 text-sm outline-none transition-colors focus:ring-2"
        style={{
          background: "var(--mis-surface)",
          borderColor: "var(--mis-border)",
          color: "var(--mis-text)",
          boxShadow: "0 0 0 0 color-mix(in srgb, var(--mis-cyan) 24%, transparent)",
        }}
      />
    </label>
  );
}

function authErrorMessage(code: string, locale: "zh" | "en"): string {
  const messages: Record<string, { zh: string; en: string }> = {
    invalid_setup_code: { zh: "主机设置码无效，请使用安装时生成的设置码。", en: "The host setup code is invalid." },
    bootstrap_unavailable: { zh: "这台主机已经完成初始化，请直接登录。", en: "This host is already initialized. Sign in instead." },
    invalid_username: { zh: "用户名需为 3–64 位小写字母、数字或 . _ -。", en: "Use 3–64 lowercase letters, digits, or . _ -." },
    weak_password: { zh: "密码至少需要 12 个字符。", en: "Password must contain at least 12 characters." },
    invalid_credentials: { zh: "用户名或密码不正确。", en: "The username or password is incorrect." },
    origin_validation_failed: { zh: "当前访问来源未被这台主机信任。", en: "This browser origin is not trusted by the host." },
    owner_already_initialized: { zh: "这台主机已经完成初始化，请直接登录。", en: "This host is already initialized. Sign in instead." },
    rate_limited: { zh: "尝试次数过多，请稍后再试。", en: "Too many attempts. Try again later." },
    unknown: { zh: "请求未完成，请检查主机连接后重试。", en: "The request did not complete. Check the host connection and retry." },
  };
  return messages[code]?.[locale] || messages.unknown[locale];
}
