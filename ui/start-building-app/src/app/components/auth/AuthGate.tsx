import { FormEvent, ReactNode, useCallback, useEffect, useMemo, useState } from "react";
import { Languages, LoaderCircle, LockKeyhole, ShieldCheck } from "lucide-react";
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

type GateState = "checking" | "login" | "bootstrap" | "ready" | "unavailable";

function messageFrom(error: unknown): string {
  if (!(error instanceof Error)) return String(error);
  const separator = error.message.indexOf(":");
  return separator >= 0 ? error.message.slice(separator + 1).trim() : error.message;
}

export function AuthGate({ children }: { children: ReactNode }) {
  const { locale, setLocale } = usePreferences();
  const [gate, setGate] = useState<GateState>("checking");
  const [status, setStatus] = useState<HumanAuthStatus | null>(null);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [setupCode, setSetupCode] = useState("");
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
      setError(messageFrom(nextError));
      setGate("unavailable");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

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
    setSubmitting(true);
    setError("");
    try {
      const session = gate === "bootstrap"
        ? await bootstrapHuman({ setup_code: setupCode, username, password, display_name: displayName || undefined })
        : await loginHuman({ username, password });
      setStatus({ required: true, authenticated: true, bootstrap_required: false, user: session.user });
      setPassword("");
      setSetupCode("");
      setGate("ready");
    } catch (nextError) {
      setError(messageFrom(nextError));
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
  const title = pick(locale, {
    zh: isBootstrap ? "初始化本地主机" : "登录 AgentOps MIS",
    en: isBootstrap ? "Initialize local host" : "Sign in to AgentOps MIS",
  });

  return (
    <div className="min-h-screen bg-[#f4f6f8] text-[#17202a] dark:bg-[#0b1220] dark:text-[#edf2f7] flex items-center justify-center p-5">
      <div className="w-full max-w-[420px] border border-[#d9dee5] bg-white shadow-sm dark:border-[#273244] dark:bg-[#111b2c]">
        <div className="flex items-center justify-between border-b border-[#e4e8ed] px-6 py-4 dark:border-[#273244]">
          <div className="flex items-center gap-3">
            <span className="flex h-9 w-9 items-center justify-center bg-[#146c94] text-white">
              <ShieldCheck size={19} aria-hidden="true" />
            </span>
            <div>
              <div className="text-sm font-semibold">AgentOps MIS</div>
              <div className="text-xs text-[#667085] dark:text-[#a8b3c5]">
                {pick(locale, { zh: "本地 AI 主机操控台", en: "Local AI host console" })}
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setLocale(locale === "zh" ? "en" : "zh")}
            className="flex h-9 w-9 items-center justify-center border border-[#d9dee5] hover:bg-[#f3f5f7] dark:border-[#344055] dark:hover:bg-[#1a2638]"
            aria-label={locale === "zh" ? "Switch to English" : "切换到中文"}
            title={locale === "zh" ? "English" : "中文"}
          >
            <Languages size={17} aria-hidden="true" />
          </button>
        </div>

        <div className="p-6">
          {gate === "checking" ? (
            <div className="flex min-h-52 flex-col items-center justify-center gap-3 text-sm text-[#667085] dark:text-[#a8b3c5]">
              <LoaderCircle className="animate-spin" size={24} aria-hidden="true" />
              {pick(locale, { zh: "正在验证主机会话...", en: "Checking host session..." })}
            </div>
          ) : gate === "unavailable" ? (
            <div className="space-y-4">
              <h1 className="text-xl font-semibold">{pick(locale, { zh: "无法连接本地主机", en: "Cannot reach local host" })}</h1>
              <p className="text-sm leading-6 text-[#667085] dark:text-[#a8b3c5]">{error}</p>
              <button type="button" onClick={() => void refresh()} className="h-10 w-full bg-[#146c94] px-4 text-sm font-semibold text-white hover:bg-[#0f5b7e]">
                {pick(locale, { zh: "重新连接", en: "Retry connection" })}
              </button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div>
                <div className="mb-2 flex items-center gap-2 text-[#146c94] dark:text-[#62b6d9]">
                  <LockKeyhole size={18} aria-hidden="true" />
                  <span className="text-xs font-semibold uppercase">{isBootstrap ? "Owner setup" : "Private access"}</span>
                </div>
                <h1 className="text-xl font-semibold">{title}</h1>
                <p className="mt-2 text-sm leading-6 text-[#667085] dark:text-[#a8b3c5]">
                  {pick(locale, {
                    zh: isBootstrap ? "创建首位 Owner。知识库、账本与 Agent 仍保留在这台主机。" : "使用主机账户进入工作台。Agent 密钥不会发送到浏览器。",
                    en: isBootstrap ? "Create the first owner. Knowledge, ledger, and agents remain on this host." : "Use your host account. Agent credentials are never sent to the browser.",
                  })}
                </p>
              </div>

              {isBootstrap && (
                <>
                  <AuthField label={pick(locale, { zh: "主机设置码", en: "Host setup code" })} value={setupCode} onChange={setSetupCode} type="password" autoComplete="one-time-code" />
                  <AuthField label={pick(locale, { zh: "显示名称（可选）", en: "Display name (optional)" })} value={displayName} onChange={setDisplayName} autoComplete="name" required={false} />
                </>
              )}
              <AuthField label={pick(locale, { zh: "用户名", en: "Username" })} value={username} onChange={setUsername} autoComplete="username" />
              <AuthField label={pick(locale, { zh: "密码", en: "Password" })} value={password} onChange={setPassword} type="password" autoComplete={isBootstrap ? "new-password" : "current-password"} />

              {error && <div role="alert" className="border border-[#d92d20] bg-[#fff5f4] px-3 py-2 text-sm text-[#b42318] dark:bg-[#351818] dark:text-[#ffb4ac]">{error}</div>}

              <button disabled={submitting} className="flex h-10 w-full items-center justify-center gap-2 bg-[#146c94] px-4 text-sm font-semibold text-white hover:bg-[#0f5b7e] disabled:cursor-not-allowed disabled:opacity-60">
                {submitting && <LoaderCircle className="animate-spin" size={16} aria-hidden="true" />}
                {pick(locale, { zh: isBootstrap ? "创建 Owner 并进入" : "登录", en: isBootstrap ? "Create owner and continue" : "Sign in" })}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}

function AuthField({
  label,
  value,
  onChange,
  type = "text",
  autoComplete,
  required = true,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  autoComplete: string;
  required?: boolean;
}) {
  return (
    <label className="block text-sm font-medium">
      <span className="mb-1.5 block">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        autoComplete={autoComplete}
        required={required}
        className="h-10 w-full border border-[#cfd5dd] bg-white px-3 outline-none focus:border-[#146c94] focus:ring-2 focus:ring-[#146c94]/20 dark:border-[#344055] dark:bg-[#0b1422]"
      />
    </label>
  );
}
