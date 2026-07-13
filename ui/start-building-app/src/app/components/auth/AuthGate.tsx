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
          className="mx-auto flex min-h-full w-full max-w-[1180px] items-center px-5 py-8 lg:px-10 lg:py-12"
        >
          <div className="grid w-full gap-10 xl:grid-cols-[minmax(0,1.25fr)_minmax(300px,0.75fr)] xl:gap-14">
            <div className="min-w-0">
              <div className="mb-8 flex items-center gap-3">
                <span
                  className="flex h-10 w-10 items-center justify-center rounded"
                  style={{ background: "var(--mis-cyan)", color: "var(--mis-bg)" }}
                >
                  <ShieldCheck size={19} aria-hidden="true" />
                </span>
                <div>
                  <div className="text-[11px] font-semibold uppercase" style={{ color: "var(--mis-cyan)" }}>
                    {pick(locale, {
                      zh: isBootstrap ? "所有者设置" : "私人主机会话",
                      en: isBootstrap ? "Owner setup" : "Private host session",
                    })}
                  </div>
                  <div className="mt-0.5 text-xs" style={{ color: "var(--mis-dim)" }}>
                    {pick(locale, { zh: "AgentOps MIS 本地 AI 主机", en: "AgentOps MIS local AI host" })}
                  </div>
                </div>
              </div>

              {gate === "checking" ? (
                <div className="flex min-h-72 items-center gap-3 text-sm" style={{ color: "var(--mis-dim)" }}>
                  <LoaderCircle className="animate-spin" size={21} aria-hidden="true" />
                  {pick(locale, { zh: "正在验证主机会话...", en: "Checking host session..." })}
                </div>
              ) : gate === "unavailable" ? (
                <div className="max-w-xl">
                  <h1 className="text-2xl font-semibold">{pick(locale, { zh: "无法连接本地主机", en: "Cannot reach local host" })}</h1>
                  <p className="mt-3 text-sm leading-6" style={{ color: "var(--mis-dim)" }}>{error}</p>
                  <button
                    type="button"
                    onClick={() => void refresh()}
                    className="mt-6 inline-flex h-10 items-center justify-center gap-2 rounded px-4 text-sm font-semibold"
                    style={{ background: "var(--mis-cyan)", color: "var(--mis-bg)" }}
                  >
                    <RefreshCw size={15} aria-hidden="true" />
                    {pick(locale, { zh: "重新连接", en: "Retry connection" })}
                  </button>
                </div>
              ) : (
                <form onSubmit={submit} className="max-w-2xl">
                  <h1 className="text-2xl font-semibold">{title}</h1>
                  <p className="mt-3 max-w-xl text-sm leading-6" style={{ color: "var(--mis-dim)" }}>
                    {pick(locale, {
                      zh: isBootstrap ? "创建首位 Owner，完成这台 AI 主机与工作台的安全绑定。" : "使用主机账户进入工作台。Agent 密钥与运行数据不会发送到浏览器。",
                      en: isBootstrap ? "Create the first owner and securely bind this AI host to its workspace." : "Use your host account. Agent credentials and runtime data are never sent to the browser.",
                    })}
                  </p>

                  <div className="mt-7 grid gap-4 sm:grid-cols-2">
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
                    className="mt-6 inline-flex h-10 min-w-40 items-center justify-center gap-2 rounded px-4 text-sm font-semibold disabled:cursor-not-allowed disabled:opacity-60"
                    style={{ background: "var(--mis-cyan)", color: "var(--mis-bg)" }}
                  >
                    {submitting ? <LoaderCircle className="animate-spin" size={16} aria-hidden="true" /> : <ArrowRight size={16} aria-hidden="true" />}
                    {pick(locale, { zh: isBootstrap ? "创建 Owner 并进入" : "登录工作台", en: isBootstrap ? "Create owner and continue" : "Enter workspace" })}
                  </button>
                </form>
              )}
            </div>

            <aside className="border-t pt-7 xl:border-l xl:border-t-0 xl:pl-10 xl:pt-0" style={{ borderColor: "var(--mis-border)" }}>
              <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
                {pick(locale, { zh: "本地主机边界", en: "Local host boundary" })}
              </div>
              <div className="mt-5 space-y-6">
                <BoundaryRow
                  icon={<Server size={16} />}
                  title={pick(locale, { zh: "权威账本留在本机", en: "Authoritative ledger stays local" })}
                  detail={pick(locale, { zh: "SQLite、知识库与项目文件由这台主机持有。", en: "SQLite, knowledge, and project files remain on this host." })}
                  status={pick(locale, { zh: "本机", en: "Local" })}
                />
                <BoundaryRow
                  icon={<Bot size={16} />}
                  title={pick(locale, { zh: "Agent 在主机侧运行", en: "Agents run on the host" })}
                  detail={pick(locale, { zh: "Hermes 与 OpenClaw 不向浏览器暴露密钥。", en: "Hermes and OpenClaw never expose credentials to the browser." })}
                  status={pick(locale, { zh: "受控", en: "Controlled" })}
                />
                <BoundaryRow
                  icon={<KeyRound size={16} />}
                  title={pick(locale, { zh: "人类会话独立认证", en: "Human sessions use separate auth" })}
                  detail={pick(locale, { zh: "Owner 登录与 Agent 机器令牌相互隔离。", en: "Owner login is isolated from Agent machine tokens." })}
                  status={isBootstrap ? pick(locale, { zh: "待绑定", en: "Pending" }) : pick(locale, { zh: "已启用", en: "Enabled" })}
                />
              </div>
              <div className="mt-8 flex items-center gap-2 border-t pt-5 text-xs" style={{ borderColor: "var(--mis-border)", color: "var(--mis-dim)" }}>
                <CheckCircle2 size={14} style={{ color: "var(--mis-success)" }} />
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
    <label className="block text-sm font-medium">
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
        className="h-10 w-full rounded border px-3 outline-none transition-colors focus:ring-2"
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
    <div className="grid grid-cols-[28px_minmax(0,1fr)_auto] gap-3">
      <span className="mt-0.5 flex h-7 w-7 items-center justify-center rounded" style={{ background: "var(--mis-surface2)", color: "var(--mis-cyan)" }}>
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-xs font-medium" style={{ color: "var(--mis-text)" }}>{title}</div>
        <p className="mt-1 text-[11px] leading-5" style={{ color: "var(--mis-dim)" }}>{detail}</p>
      </div>
      <span className="mt-0.5 text-[10px] font-medium" style={{ color: "var(--mis-success)" }}>{status}</span>
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
