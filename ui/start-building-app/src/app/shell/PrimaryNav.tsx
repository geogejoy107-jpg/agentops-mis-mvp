import { useState } from "react";
import { ChevronDown, ChevronRight, Zap } from "lucide-react";
import { Link, useLocation } from "react-router";
import { usePreferences } from "../context/PreferencesContext";
import { NAVIGATION, navLabel } from "./navigation";

function isActive(pathname: string, path: string) {
  if (path === "/workspace") return pathname === "/workspace" || pathname === "/";
  return pathname === path || pathname.startsWith(`${path}/`);
}

export function PrimaryNav() {
  const { locale } = usePreferences();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  return (
    <aside className="hidden h-full w-[var(--ui-sidebar-width)] shrink-0 flex-col border-r lg:flex" style={{ background: "var(--ui-surface-1)", borderColor: "var(--ui-border)" }}>
      <Link to="/workspace" className="flex h-16 items-center gap-3 border-b px-4" style={{ borderColor: "var(--ui-border)" }}>
        <span className="flex h-9 w-9 items-center justify-center rounded-lg" style={{ background: "var(--ui-accent)", color: "white" }}>
          <Zap size={17} />
        </span>
        <span className="min-w-0">
          <strong className="block truncate text-sm" style={{ color: "var(--ui-text)" }}>AgentOps MIS</strong>
          <span className="block truncate text-[11px]" style={{ color: "var(--ui-text-subtle)" }}>AI company control plane</span>
        </span>
      </Link>

      <nav className="ui-v2-scrollbar flex-1 overflow-y-auto px-3 py-4" aria-label={locale === "zh" ? "主导航" : "Primary navigation"}>
        <div className="space-y-4">
          {NAVIGATION.map((group) => {
            const closed = Boolean(collapsed[group.id]);
            return (
              <section key={group.id}>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-md px-2 py-1 text-[11px] font-semibold uppercase tracking-[0.12em]"
                  style={{ color: "var(--ui-text-subtle)" }}
                  onClick={() => setCollapsed((current) => ({ ...current, [group.id]: !current[group.id] }))}
                  aria-expanded={!closed}
                >
                  {navLabel(locale, group.label)}
                  {closed ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                </button>
                {!closed && (
                  <ul className="mt-1 space-y-0.5">
                    {group.items.map((item) => {
                      const active = isActive(location.pathname, item.path);
                      const Icon = item.icon;
                      return (
                        <li key={item.id}>
                          <Link
                            to={item.path}
                            className="ui-v2-interactive flex min-h-9 items-center gap-2.5 rounded-md border px-2.5 text-[13px]"
                            style={{
                              color: active ? "var(--ui-accent-strong)" : "var(--ui-text-muted)",
                              background: active ? "rgba(34,211,238,.08)" : "transparent",
                              borderColor: active ? "rgba(34,211,238,.22)" : "transparent",
                            }}
                          >
                            <Icon size={15} aria-hidden="true" />
                            <span className="truncate">{navLabel(locale, item.label)}</span>
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
      </nav>

      <div className="border-t px-4 py-3 text-[11px]" style={{ borderColor: "var(--ui-border)", color: "var(--ui-text-subtle)" }}>
        <div>Local-first control plane</div>
        <div className="mt-0.5">Draft UI v2</div>
      </div>
    </aside>
  );
}

const MOBILE_ITEMS = [
  { group: 0, item: 0 },
  { group: 0, item: 2 },
  { group: 1, item: 0 },
  { group: 2, item: 0 },
  { group: 4, item: 0 },
];

export function MobileNav() {
  const { locale } = usePreferences();
  const location = useLocation();

  return (
    <nav
      className="fixed inset-x-0 bottom-0 z-50 grid grid-cols-5 border-t px-1 pb-[max(env(safe-area-inset-bottom),4px)] pt-1 lg:hidden"
      style={{ background: "var(--ui-surface-1)", borderColor: "var(--ui-border)" }}
      aria-label={locale === "zh" ? "移动端导航" : "Mobile navigation"}
    >
      {MOBILE_ITEMS.map(({ group, item }) => {
        const nav = NAVIGATION[group].items[item];
        const Icon = nav.icon;
        const active = isActive(location.pathname, nav.path);
        return (
          <Link key={nav.id} to={nav.path} className="flex min-h-12 flex-col items-center justify-center gap-0.5 rounded-md text-[10px]" style={{ color: active ? "var(--ui-accent-strong)" : "var(--ui-text-subtle)" }}>
            <Icon size={17} />
            <span className="max-w-full truncate">{navLabel(locale, nav.label)}</span>
          </Link>
        );
      })}
    </nav>
  );
}
