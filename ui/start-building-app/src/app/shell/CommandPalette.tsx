import { useEffect, useMemo, useState } from "react";
import { Search, X } from "lucide-react";
import { useNavigate } from "react-router";
import { usePreferences } from "../context/PreferencesContext";
import { FLAT_NAVIGATION, navLabel } from "./navigation";

export function useCommandPaletteShortcut(onOpen: () => void) {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        onOpen();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onOpen]);
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { locale } = usePreferences();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return FLAT_NAVIGATION.slice(0, 12);
    return FLAT_NAVIGATION.filter((item) => [item.label.en, item.label.zh, item.path, ...(item.keywords || [])].join(" ").toLowerCase().includes(needle)).slice(0, 12);
  }, [query]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
    }
  }, [open]);

  useEffect(() => {
    if (active >= results.length) setActive(Math.max(0, results.length - 1));
  }, [active, results.length]);

  if (!open) return null;
  const choose = (path: string) => {
    navigate(path);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center bg-slate-950/50 px-4 pt-[12vh]" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <div className="w-full max-w-2xl overflow-hidden rounded-xl border shadow-2xl" style={{ background: "var(--ui-surface-raised)", borderColor: "var(--ui-border)", color: "var(--ui-text)" }} role="dialog" aria-modal="true" aria-label={locale === "zh" ? "命令面板" : "Command palette"}>
        <div className="flex items-center gap-3 border-b px-4" style={{ borderColor: "var(--ui-border)" }}>
          <Search size={17} style={{ color: "var(--ui-text-subtle)" }} />
          <input
            autoFocus
            value={query}
            onChange={(event) => { setQuery(event.target.value); setActive(0); }}
            onKeyDown={(event) => {
              if (event.key === "Escape") onClose();
              if (event.key === "ArrowDown") { event.preventDefault(); setActive((value) => Math.min(value + 1, Math.max(0, results.length - 1))); }
              if (event.key === "ArrowUp") { event.preventDefault(); setActive((value) => Math.max(value - 1, 0)); }
              if (event.key === "Enter" && results[active]) { event.preventDefault(); choose(results[active].path); }
            }}
            className="h-[52px] flex-1 bg-transparent py-4 text-sm outline-none"
            placeholder={locale === "zh" ? "搜索页面和操作…" : "Search pages and operational entries…"}
            aria-label={locale === "zh" ? "搜索命令" : "Search commands"}
          />
          <button type="button" onClick={onClose} className="rounded p-1.5" aria-label={locale === "zh" ? "关闭" : "Close"}><X size={16} /></button>
        </div>
        <div className="max-h-[56vh] overflow-y-auto p-2">
          {results.length === 0 && <div className="px-3 py-8 text-center text-sm" style={{ color: "var(--ui-text-muted)" }}>{locale === "zh" ? "没有匹配的入口" : "No matching command"}</div>}
          {results.map((item, index) => {
            const Icon = item.icon;
            return (
              <button key={item.id} type="button" onMouseEnter={() => setActive(index)} onClick={() => choose(item.path)} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left" style={{ background: active === index ? "var(--ui-surface-2)" : "transparent", color: "var(--ui-text)" }}>
                <span className="flex h-8 w-8 items-center justify-center rounded-md border" style={{ borderColor: "var(--ui-border)", color: "var(--ui-accent-strong)" }}><Icon size={15} /></span>
                <span className="min-w-0 flex-1"><strong className="block truncate text-sm font-medium">{navLabel(locale, item.label)}</strong><span className="block truncate text-[11px]" style={{ color: "var(--ui-text-subtle)" }}>{item.path}</span></span>
                <kbd className="rounded border px-1.5 py-0.5 text-[10px]" style={{ borderColor: "var(--ui-border)", color: "var(--ui-text-subtle)" }}>Enter</kbd>
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-4 border-t px-4 py-2 text-[10px]" style={{ borderColor: "var(--ui-border)", color: "var(--ui-text-subtle)" }}>
          <span>↑↓ {locale === "zh" ? "选择" : "select"}</span><span>Enter {locale === "zh" ? "打开" : "open"}</span><span>Esc {locale === "zh" ? "关闭" : "close"}</span>
        </div>
      </div>
    </div>
  );
}
