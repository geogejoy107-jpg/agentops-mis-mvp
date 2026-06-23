import { useCallback, useState } from "react";
import type { ReactNode } from "react";
import { Bell, Languages, Menu, Moon, Search, Sun, X, Zap } from "lucide-react";
import { Link, useLocation } from "react-router";
import { usePreferences } from "../context/PreferencesContext";
import { CommandPalette, useCommandPaletteShortcut } from "./CommandPalette";
import { ContextBar } from "./ContextBar";
import { MobileNav, PrimaryNav } from "./PrimaryNav";
import { FLAT_NAVIGATION, NAVIGATION, navLabel } from "./navigation";

export function AppShellV2({ children }: { children: ReactNode }) {
  const { theme, locale, setTheme, setLocale } = usePreferences();
  const location = useLocation();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  useCommandPaletteShortcut(openPalette);

  const current = FLAT_NAVIGATION.find((item) => location.pathname === item.path || (item.path !== "/workspace" && location.pathname.startsWith(`${item.path}/`)));

  return (
    <div className={`ui-v2-shell theme-${theme} flex h-screen w-screen overflow-hidden`}>
      <PrimaryNav />
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b px-3 sm:px-5" style={{ background: "var(--ui-surface-1)", borderColor: "var(--ui-border)" }}>
          <button type="button" className="rounded-md p-2 lg:hidden" onClick={() => setMobileMenuOpen(true)} aria-label={locale === "zh" ? "打开菜单" : "Open menu"}><Menu size={18} /></button>
          <Link to="/workspace" className="flex items-center gap-2 lg:hidden">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: "var(--ui-accent)", color: "white" }}><Zap size={15} /></span>
            <strong className="hidden text-sm sm:block">AgentOps MIS</strong>
          </Link>
          <div className="hidden min-w-0 flex-1 sm:block">
            <div className="truncate text-xs" style={{ color: "var(--ui-text-subtle)" }}>{locale === "zh" ? "当前视图" : "Current view"}</div>
            <div className="truncate text-sm font-medium" style={{ color: "var(--ui-text)" }}>{current ? navLabel(locale, current.label) : location.pathname}</div>
          </div>
          <button type="button" onClick={openPalette} className="ui-v2-interactive ml-auto flex h-9 min-w-0 items-center gap-2 rounded-md border px-2.5 sm:w-72" style={{ background: "var(--ui-surface-2)", borderColor: "var(--ui-border)", color: "var(--ui-text-muted)" }} aria-label={locale === "zh" ? "打开命令面板" : "Open command palette"}>
            <Search size={14} /><span className="hidden flex-1 truncate text-left text-xs sm:block">{locale === "zh" ? "搜索页面和操作…" : "Search pages and actions…"}</span><kbd className="hidden rounded border px-1.5 py-0.5 text-[10px] sm:block" style={{ borderColor: "var(--ui-border)", color: "var(--ui-text-subtle)" }}>⌘K</kbd>
          </button>
          <button type="button" className="ui-v2-interactive rounded-md border p-2" style={{ borderColor: "var(--ui-border)", color: "var(--ui-text-muted)" }} onClick={() => setTheme(theme === "enterprise" ? "ops" : "enterprise")} aria-label={locale === "zh" ? "切换明暗主题" : "Toggle light and dark theme"}>
            {theme === "enterprise" ? <Moon size={15} /> : <Sun size={15} />}
          </button>
          <button type="button" className="ui-v2-interactive rounded-md border p-2" style={{ borderColor: "var(--ui-border)", color: "var(--ui-text-muted)" }} onClick={() => setLocale(locale === "en" ? "zh" : "en")} aria-label={locale === "zh" ? "切换语言" : "Switch language"}><Languages size={15} /></button>
          <button type="button" className="relative rounded-md p-2" style={{ color: "var(--ui-text-muted)" }} aria-label={locale === "zh" ? "通知" : "Notifications"}><Bell size={16} /><span className="absolute right-1.5 top-1.5 h-1.5 w-1.5 rounded-full" style={{ background: "var(--ui-warning)" }} /></button>
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[11px] font-semibold" style={{ background: "var(--ui-purple)", color: "white" }}>JW</span>
        </header>

        <ContextBar />
        <main className="ui-v2-scrollbar app-main flex-1 overflow-y-auto px-3 py-4 pb-20 sm:px-5 sm:py-5 lg:pb-6">{children}</main>
      </div>

      <MobileNav />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />

      {mobileMenuOpen && (
        <div className="fixed inset-0 z-[90] bg-slate-950/45 lg:hidden" onMouseDown={(event) => { if (event.target === event.currentTarget) setMobileMenuOpen(false); }}>
          <div className="h-full w-[min(86vw,320px)] overflow-y-auto border-r p-4" style={{ background: "var(--ui-surface-1)", borderColor: "var(--ui-border)" }}>
            <div className="mb-4 flex items-center justify-between">
              <Link to="/workspace" onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-2"><span className="flex h-8 w-8 items-center justify-center rounded-lg" style={{ background: "var(--ui-accent)", color: "white" }}><Zap size={15} /></span><strong>AgentOps MIS</strong></Link>
              <button type="button" className="rounded p-2" onClick={() => setMobileMenuOpen(false)} aria-label={locale === "zh" ? "关闭菜单" : "Close menu"}><X size={18} /></button>
            </div>
            <div className="space-y-5">
              {NAVIGATION.map((group) => (
                <section key={group.id}>
                  <div className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-[0.12em]" style={{ color: "var(--ui-text-subtle)" }}>{navLabel(locale, group.label)}</div>
                  <div className="space-y-1">
                    {group.items.map((item) => {
                      const Icon = item.icon;
                      return <Link key={item.id} to={item.path} onClick={() => setMobileMenuOpen(false)} className="flex items-center gap-3 rounded-md border px-3 py-2.5 text-sm" style={{ borderColor: "var(--ui-border)", color: "var(--ui-text-muted)" }}><Icon size={16} />{navLabel(locale, item.label)}</Link>;
                    })}
                  </div>
                </section>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
