import { Search, Bell, ChevronDown, Radio, Moon, Sun, Languages, Palette } from "lucide-react";
import { pick, usePreferences } from "../../context/PreferencesContext";
import type { ThemeMode } from "../../context/PreferencesContext";

const themeOrder: ThemeMode[] = ["enterprise", "ops", "workforce"];

export function Topbar() {
  const { theme, locale, setTheme, setLocale } = usePreferences();
  const copy = pick(locale, {
    en: {
      workspace: "Workspace",
      workspaceName: "AgentOps Demo",
      search: "Search agents, tasks, runs...",
      live: "Live",
      themeLabel: theme === "enterprise" ? "Enterprise" : theme === "ops" ? "Ops" : "Workforce",
      languageLabel: "EN",
      switchTheme: "Switch visual style",
      switchLanguage: "Switch language",
    },
    zh: {
      workspace: "工作区",
      workspaceName: "AgentOps 演示",
      search: "搜索代理、任务、运行...",
      live: "实时",
      themeLabel: theme === "enterprise" ? "企业版" : theme === "ops" ? "控制面" : "员工 OS",
      languageLabel: "中",
      switchTheme: "切换视觉风格",
      switchLanguage: "切换语言",
    },
  });

  const cycleTheme = () => {
    const nextIndex = (themeOrder.indexOf(theme) + 1) % themeOrder.length;
    setTheme(themeOrder[nextIndex]);
  };

  return (
    <header
      className="flex items-center justify-between gap-4 px-4 lg:px-5 h-12 shrink-0 border-b"
      style={{
        background: "var(--mis-surface)",
        borderColor: "var(--mis-border)",
      }}
    >
      {/* Left: workspace switcher */}
      <button
        className="flex items-center gap-1.5 text-xs rounded px-2 py-1 hover:opacity-80 transition-opacity shrink-0"
        style={{ color: "var(--mis-text)", background: "var(--mis-surface2)" }}
      >
        <span style={{ color: "var(--mis-dim)" }}>{copy.workspace}:</span>
        {copy.workspaceName}
        <ChevronDown size={12} style={{ color: "var(--mis-dim)" }} />
      </button>

      {/* Center: search */}
      <div
        className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded text-xs w-full max-w-xl"
        style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)" }}
      >
        <Search size={13} />
        <span>{copy.search}</span>
      </div>

      {/* Right */}
      <div className="flex items-center gap-2 shrink-0">
        {/* Live mode badge */}
        <div
          className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-medium"
          style={{ background: "rgba(42,157,143,0.15)", color: "var(--mis-success)" }}
        >
          <Radio size={11} className="animate-pulse" />
          {copy.live}
        </div>

        <button
          className="h-7 px-2 rounded flex items-center gap-1.5 text-[11px] hover:opacity-80"
          style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
          onClick={cycleTheme}
          title={copy.switchTheme}
        >
          {theme === "enterprise" ? <Sun size={13} /> : theme === "ops" ? <Moon size={13} /> : <Palette size={13} />}
          <span className="hidden lg:inline">{copy.themeLabel}</span>
        </button>

        <button
          className="h-7 px-2 rounded flex items-center gap-1.5 text-[11px] hover:opacity-80"
          style={{ background: "var(--mis-surface2)", color: "var(--mis-dim)", border: "1px solid var(--mis-border)" }}
          onClick={() => setLocale(locale === "en" ? "zh" : "en")}
          title={copy.switchLanguage}
        >
          <Languages size={13} />
          {copy.languageLabel}
        </button>

        {/* Notifications */}
        <button
          className="relative p-1.5 rounded hover:opacity-80"
          style={{ color: "var(--mis-dim)" }}
        >
          <Bell size={15} />
          <span
            className="absolute top-0.5 right-0.5 w-2 h-2 rounded-full"
            style={{ background: "var(--mis-warning)" }}
          />
        </button>

        {/* Avatar */}
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-semibold cursor-pointer"
          style={{ background: "var(--mis-purple)", color: "#fff" }}
          title="Jiwu Wang"
        >
          JW
        </div>
      </div>
    </header>
  );
}
