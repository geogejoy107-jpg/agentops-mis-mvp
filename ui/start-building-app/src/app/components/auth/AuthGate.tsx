import { FormEvent, ReactNode, useCallback, useEffect, useId, useMemo, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Eye,
  EyeOff,
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
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);

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
      setShowPassword(false);
      setShowConfirmPassword(false);
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
      setShowPassword(false);
      setShowConfirmPassword(false);
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
      setShowPassword(false);
      setShowConfirmPassword(false);
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
  const passwordReady = password.length >= 12;
  const passwordsMatch = confirmPassword.length > 0 && password === confirmPassword;
  const usernameReady = /^[a-z0-9][a-z0-9._-]{2,63}$/.test(username);
  const bootstrapFormReady = Boolean(setupCode.trim()) && usernameReady && passwordReady && passwordsMatch;
  const passwordHint = !isBootstrap
    ? undefined
    : password.length === 0
      ? pick(locale, { zh: "至少 12 个字符", en: "At least 12 characters" })
      : passwordReady
        ? pick(locale, { zh: "已满足 12 个字符", en: "12-character minimum met" })
        : pick(locale, {
            zh: `还需 ${12 - password.length} 个字符`,
            en: `${12 - password.length} more characters required`,
          });
  const confirmPasswordHint = confirmPassword.length === 0
    ? pick(locale, { zh: "再次输入相同密码", en: "Enter the same password again" })
    : passwordsMatch
      ? pick(locale, { zh: "两次输入一致", en: "Passwords match" })
      : pick(locale, { zh: "两次输入不一致", en: "Passwords do not match" });
  const togglePasswordLabel = showPassword
    ? pick(locale, { zh: "隐藏密码", en: "Hide password" })
    : pick(locale, { zh: "显示密码", en: "Show password" });
  const toggleConfirmPasswordLabel = showConfirmPassword
    ? pick(locale, { zh: "隐藏确认密码", en: "Hide confirmation password" })
    : pick(locale, { zh: "显示确认密码", en: "Show confirmation password" });
  const lockLabel = pick(locale, {
    zh: gate === "checking" ? "正在连接" : isBootstrap ? "需要初始化" : "需要登录",
    en: gate === "checking" ? "Connecting" : isBootstrap ? "Setup required" : "Sign-in required",
  });
  const pageTitle = pick(locale, {
    zh: "账户与访问",
    en: "Account and access",
  });
  const pageSubtitle = pick(locale, {
    zh: isBootstrap ? "创建账户后即可进入当前工作区" : "使用这台主机上的账户继续",
    en: isBootstrap ? "Create an account to enter this workspace" : "Continue with an account on this host",
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
            title={pick(locale, { zh: isBootstrap ? "创建所有者账户" : "登录工作区", en: isBootstrap ? "Create owner account" : "Sign in to workspace" })}
            description={pick(locale, {
              zh: isBootstrap ? "只需设置一次。之后可从本机或已授权的私人网络浏览器登录。" : "输入账户信息，继续管理任务、代理和运行记录。",
              en: isBootstrap ? "Set this up once, then sign in locally or from an authorized private-network browser." : "Enter your account details to manage tasks, agents, and runs.",
            })}
            meta={(
              <p data-testid="human-auth-host-boundary" className="mt-3 flex items-center gap-1.5 text-[11px]" style={{ color: "var(--mis-muted)" }}>
                <LockKeyhole size={11} aria-hidden="true" />
                {pick(locale, { zh: "账户与运行数据仅保留在主机", en: "Account and runtime data stay on the host" })}
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
                        className="grid gap-1.5 py-3 text-xs sm:grid-cols-[160px_minmax(0,1fr)] sm:items-center sm:gap-3"
                      >
                        <span className="font-medium" style={{ color: "var(--mis-text)" }}>{pick(locale, { zh: "安装授权", en: "Installer authorization" })}</span>
                        <span className="flex max-w-md items-center gap-2" style={{ color: "var(--mis-success)" }}>
                          <CheckCircle2 size={14} aria-hidden="true" />
                          {pick(locale, { zh: "已安全接收", en: "Received securely" })}
                        </span>
                      </div>
                    )}
                    {isBootstrap && (
                      <AuthField
                        label={pick(locale, { zh: "显示名称", en: "Display name" })}
                        value={displayName}
                        onChange={setDisplayName}
                        autoComplete="name"
                        placeholder={pick(locale, { zh: "例如：Joy", en: "For example: Joy" })}
                        required={false}
                      />
                    )}
                    <AuthField
                      label={pick(locale, { zh: "用户名", en: "Username" })}
                      hint={isBootstrap ? pick(locale, { zh: "3–64 位小写字母、数字或 . _ -", en: "3–64 lowercase letters, digits, or . _ -" }) : undefined}
                      value={username}
                      onChange={setUsername}
                      autoComplete="username"
                      placeholder={isBootstrap ? "joy-owner" : undefined}
                      pattern={isBootstrap ? "[a-z0-9][a-z0-9._-]{2,63}" : undefined}
                    />
                    <AuthField
                      label={pick(locale, { zh: "密码", en: "Password" })}
                      hint={passwordHint}
                      hintTone={password.length > 0 ? (passwordReady ? "success" : "warning") : "muted"}
                      value={password}
                      onChange={setPassword}
                      type={showPassword ? "text" : "password"}
                      autoComplete={isBootstrap ? "new-password" : "current-password"}
                      minLength={isBootstrap ? 12 : undefined}
                      revealControl={{
                        visible: showPassword,
                        label: togglePasswordLabel,
                        onToggle: () => setShowPassword((current) => !current),
                      }}
                    />
                    {isBootstrap && (
                      <AuthField
                        label={pick(locale, { zh: "确认密码", en: "Confirm password" })}
                        hint={confirmPasswordHint}
                        hintTone={confirmPassword.length > 0 ? (passwordsMatch ? "success" : "warning") : "muted"}
                        value={confirmPassword}
                        onChange={setConfirmPassword}
                        type={showConfirmPassword ? "text" : "password"}
                        autoComplete="new-password"
                        minLength={12}
                        revealControl={{
                          visible: showConfirmPassword,
                          label: toggleConfirmPasswordLabel,
                          onToggle: () => setShowConfirmPassword((current) => !current),
                        }}
                      />
                    )}
                  </div>

                  {error && (
                    <div className="grid gap-1.5 border-b py-3 text-xs sm:grid-cols-[160px_minmax(0,1fr)] sm:gap-3" style={{ borderColor: "var(--mis-border)" }}>
                      <span className="hidden sm:block" aria-hidden="true" />
                      <div role="alert" className="max-w-md rounded px-3 py-2.5" style={{ background: "color-mix(in srgb, var(--mis-warning) 8%, transparent)", color: "var(--mis-warning)" }}>
                        {error}
                      </div>
                    </div>
                  )}

                  <div className="grid gap-3 pt-4 sm:grid-cols-[160px_minmax(0,1fr)]">
                    <span className="hidden sm:block" aria-hidden="true" />
                    <div className="flex max-w-md justify-start">
                      <button
                        disabled={submitting || (isBootstrap && !bootstrapFormReady)}
                        className="inline-flex h-9 w-full items-center justify-center gap-2 rounded px-4 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto sm:min-w-40"
                        style={{ background: "var(--mis-primary)", color: "#fff" }}
                      >
                        {submitting ? <LoaderCircle className="animate-spin" size={16} aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}
                        {pick(locale, { zh: isBootstrap ? "创建账户并进入" : "登录", en: isBootstrap ? "Create account and continue" : "Sign in" })}
                      </button>
                    </div>
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
  hintTone = "muted",
  value,
  onChange,
  type = "text",
  autoComplete,
  required = true,
  minLength,
  pattern,
  placeholder,
  revealControl,
}: {
  label: string;
  hint?: string;
  hintTone?: "muted" | "success" | "warning";
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete: string;
  required?: boolean;
  minLength?: number;
  pattern?: string;
  placeholder?: string;
  revealControl?: {
    visible: boolean;
    label: string;
    onToggle: () => void;
  };
}) {
  const inputId = useId();
  const hintColor = hintTone === "success"
    ? "var(--mis-success)"
    : hintTone === "warning"
      ? "var(--mis-warning)"
      : "var(--mis-muted)";

  return (
    <div className="grid gap-1.5 py-3 text-xs sm:grid-cols-[160px_minmax(0,1fr)] sm:items-center sm:gap-3">
      <span className="min-w-0">
        <label htmlFor={inputId} className="block font-medium" style={{ color: "var(--mis-text)" }}>{label}</label>
        {hint && <span aria-live="polite" className="mt-0.5 block text-[10px] font-normal" style={{ color: hintColor }}>{hint}</span>}
      </span>
      <div className="relative min-w-0 max-w-md">
        <input
          id={inputId}
          type={type}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          autoComplete={autoComplete}
          required={required}
          minLength={minLength}
          pattern={pattern}
          placeholder={placeholder}
          className={`h-9 w-full min-w-0 rounded border px-3 text-sm outline-none transition-colors focus:ring-2 ${revealControl ? "pr-10" : ""}`}
          style={{
            background: "var(--mis-surface)",
            borderColor: "var(--mis-border)",
            color: "var(--mis-text)",
            boxShadow: "0 0 0 0 color-mix(in srgb, var(--mis-cyan) 24%, transparent)",
          }}
        />
        {revealControl && (
          <button
            type="button"
            onClick={revealControl.onToggle}
            aria-label={revealControl.label}
            aria-pressed={revealControl.visible}
            title={revealControl.label}
            className="absolute right-1 top-1 inline-flex h-7 w-7 items-center justify-center rounded"
            style={{ color: "var(--mis-dim)" }}
          >
            {revealControl.visible ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
          </button>
        )}
      </div>
    </div>
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
