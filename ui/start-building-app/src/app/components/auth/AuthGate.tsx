import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  KeyRound,
  LoaderCircle,
  LockKeyhole,
  RefreshCw,
  Server,
  ShieldCheck,
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
  const title = pick(locale, {
    zh: isBootstrap ? "初始化本地主机" : "登录 AgentOps MIS",
    en: isBootstrap ? "Initialize local host" : "Sign in to AgentOps MIS",
  });

  return (
    <HumanAuthContext.Provider value={contextValue}>
      <AppShell locked lockLabel={lockLabel}>
        <section
          data-testid="human-auth-workspace-gate"
          className="min-h-full w-full space-y-4"
        >
          <header className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h1 className="text-lg font-semibold" style={{ color: "var(--mis-text)" }}>
                  {pick(locale, { zh: "主机接入", en: "Host access" })}
                </h1>
                <span
                  className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] font-medium"
                  style={{
                    background: gate === "unavailable" ? "rgba(231,111,81,0.10)" : "rgba(34,211,238,0.10)",
                    border: `1px solid ${gate === "unavailable" ? "rgba(231,111,81,0.24)" : "rgba(34,211,238,0.20)"}`,
                    color: gate === "unavailable" ? "var(--mis-warning)" : "var(--mis-cyan)",
                  }}
                >
                  {gate === "checking" ? <LoaderCircle className="animate-spin" size={11} /> : <LockKeyhole size={11} />}
                  {lockLabel}
                </span>
              </div>
              <p className="mt-1 text-xs" style={{ color: "var(--mis-dim)" }}>
                {pick(locale, {
                  zh: "登录后进入现有任务、运行、审批和审计工作台。",
                  en: "Sign in to the existing tasks, runs, approvals, and audit workspace.",
                })}
              </p>
            </div>
            <div className="flex items-center gap-2 text-[11px]" style={{ color: "var(--mis-muted)" }}>
              <Server size={13} style={{ color: "var(--mis-success)" }} />
              {pick(locale, { zh: "本地主机 · 私人网络", en: "Local host · private network" })}
            </div>
          </header>

          <div className="grid grid-cols-12 items-start gap-4">
            <section
              data-testid="human-auth-access-panel"
              className="col-span-12 overflow-hidden rounded-lg xl:col-span-8"
              style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
            >
              <div className="flex items-center justify-between gap-3 border-b px-4 py-3" style={{ borderColor: "var(--mis-border)" }}>
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded"
                    style={{ background: "var(--mis-surface2)", color: "var(--mis-cyan)", border: "1px solid var(--mis-border)" }}
                  >
                    {isBootstrap ? <ShieldCheck size={15} aria-hidden="true" /> : <KeyRound size={15} aria-hidden="true" />}
                  </span>
                  <div className="min-w-0">
                    <h2 className="text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{title}</h2>
                    <p className="mt-0.5 text-[11px]" style={{ color: "var(--mis-dim)" }}>
                      {pick(locale, {
                        zh: isBootstrap ? "首次设置 · 创建主机所有者" : "使用主机账户继续",
                        en: isBootstrap ? "First-time setup · create the host owner" : "Continue with a host account",
                      })}
                    </p>
                  </div>
                </div>
                <span className="hidden text-[10px] sm:inline" style={{ color: "var(--mis-muted)" }}>
                  {pick(locale, { zh: "AgentOps MIS 工作区", en: "AgentOps MIS workspace" })}
                </span>
              </div>

              <div className="p-4 lg:p-5">
              {gate === "checking" ? (
                <div className="flex min-h-44 items-center justify-center gap-2.5 text-xs" style={{ color: "var(--mis-dim)" }}>
                  <LoaderCircle className="animate-spin" size={17} aria-hidden="true" />
                  {pick(locale, { zh: "正在验证主机会话...", en: "Checking host session..." })}
                </div>
              ) : gate === "unavailable" ? (
                <div className="max-w-2xl py-2">
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
                <form onSubmit={submit} className="max-w-3xl">
                  <p className="max-w-2xl text-xs leading-5" style={{ color: "var(--mis-dim)" }}>
                    {pick(locale, {
                      zh: isBootstrap ? "创建首位所有者账户，完成这台 AI 主机与工作台的安全绑定。" : "使用主机账户进入工作台。AI 员工密钥与运行数据不会发送到浏览器。",
                      en: isBootstrap ? "Create the first owner and securely bind this AI host to its workspace." : "Use your host account. Agent credentials and runtime data are never sent to the browser.",
                    })}
                  </p>

                  <div className="mt-5 grid gap-4 sm:grid-cols-2">
                    {isBootstrap && !hasInstallerHandoff && (
                      <div className="sm:col-span-2">
                        <AuthField
                          label={pick(locale, { zh: "主机设置码", en: "Host setup code" })}
                          hint={pick(locale, { zh: "安装时生成的一次性主机凭据", en: "One-time host credential created during installation" })}
                          value={setupCode}
                          onChange={setSetupCode}
                          type="password"
                          autoComplete="one-time-code"
                        />
                      </div>
                    )}
                    {hasInstallerHandoff && (
                      <div
                        data-testid="owner-setup-handoff-ready"
                        className="sm:col-span-2 flex items-center gap-2 rounded px-3 py-2 text-xs"
                        style={{ background: "rgba(42,157,143,0.08)", border: "1px solid rgba(42,157,143,0.28)", color: "var(--mis-success)" }}
                      >
                        <CheckCircle2 size={14} aria-hidden="true" />
                        {pick(locale, { zh: "已从本机安装器接收一次性主机配对凭据", en: "One-time host pairing credential received from the local installer" })}
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
                      className="mt-4 rounded px-3 py-2 text-sm"
                      style={{ border: "1px solid rgba(231,111,81,0.5)", background: "rgba(231,111,81,0.08)", color: "var(--mis-warning)" }}
                    >
                      {error}
                    </div>
                  )}

                  <button
                    disabled={submitting}
                    className="mt-5 inline-flex h-9 w-full items-center justify-center gap-2 rounded px-4 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto sm:min-w-44"
                    style={{ background: "var(--mis-cyan)", color: "var(--mis-bg)" }}
                  >
                    {submitting ? <LoaderCircle className="animate-spin" size={16} aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}
                    {pick(locale, { zh: isBootstrap ? "创建所有者并进入" : "登录工作台", en: isBootstrap ? "Create owner and continue" : "Enter workspace" })}
                  </button>
                </form>
              )}
              </div>
            </section>

            <aside
              data-testid="human-auth-host-boundary-panel"
              className="col-span-12 overflow-hidden rounded-lg xl:col-span-4"
              style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
            >
              <div className="flex items-center justify-between border-b px-4 py-3" style={{ borderColor: "var(--mis-border)" }}>
                <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
                  {pick(locale, { zh: "主机状态", en: "Host status" })}
                </div>
                <span className="inline-flex items-center gap-1 text-[10px]" style={{ color: "var(--mis-success)" }}>
                  <CheckCircle2 size={12} />
                  {pick(locale, { zh: "本机可用", en: "Host available" })}
                </span>
              </div>
              <div className="divide-y px-4" style={{ borderColor: "var(--mis-border)" }}>
                <BoundaryRow
                  icon={<Server size={16} />}
                  title={pick(locale, { zh: "权威账本留在本机", en: "Authoritative ledger stays local" })}
                  detail={pick(locale, { zh: "SQLite、知识库与项目文件由这台主机持有。", en: "SQLite, knowledge, and project files remain on this host." })}
                  status={pick(locale, { zh: "本机", en: "Local" })}
                />
                <BoundaryRow
                  icon={<Bot size={16} />}
                  title={pick(locale, { zh: "AI 员工在主机侧运行", en: "Agents run on the host" })}
                  detail={pick(locale, { zh: "Hermes 与 OpenClaw 不向浏览器暴露密钥。", en: "Hermes and OpenClaw never expose credentials to the browser." })}
                  status={pick(locale, { zh: "受控", en: "Controlled" })}
                />
                <BoundaryRow
                  icon={<KeyRound size={16} />}
                  title={pick(locale, { zh: "人类会话独立认证", en: "Human sessions use separate auth" })}
                  detail={pick(locale, { zh: "所有者登录与 AI 员工机器令牌相互隔离。", en: "Owner login is isolated from Agent machine tokens." })}
                  status={isBootstrap ? pick(locale, { zh: "待绑定", en: "Pending" }) : pick(locale, { zh: "已启用", en: "Enabled" })}
                />
              </div>
              <div className="flex items-center gap-2 border-t px-4 py-3 text-[11px]" style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)" }}>
                <ShieldCheck size={13} style={{ color: "var(--mis-success)" }} />
                {pick(locale, { zh: "私人网络 · 非公开互联网服务", en: "Private network · not a public internet service" })}
              </div>
            </aside>
          </div>
        </section>
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
    <label className="block text-xs font-medium">
      <span className="mb-1.5 flex flex-col gap-0.5 sm:flex-row sm:items-center sm:justify-between sm:gap-3">
        <span>{label}</span>
        {hint && <span className="text-[10px] font-normal" style={{ color: "var(--mis-muted)" }}>{hint}</span>}
      </span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        required={required}
        minLength={minLength}
        pattern={pattern}
        className="h-9 w-full rounded border px-3 text-sm outline-none transition-colors focus:ring-2"
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

function BoundaryRow({
  icon,
  title,
  detail,
  status,
}: {
  icon: ReactNode;
  title: string;
  detail: string;
  status: string;
}) {
  return (
    <div className="grid grid-cols-[28px_minmax(0,1fr)_auto] gap-3 py-3.5">
      <span className="flex h-7 w-7 items-center justify-center rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-cyan)" }}>
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{title}</div>
        <p className="mt-0.5 text-[11px] leading-4" style={{ color: "var(--mis-dim)" }}>{detail}</p>
      </div>
      <span className="text-[10px] font-medium" style={{ color: "var(--mis-success)" }}>{status}</span>
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
