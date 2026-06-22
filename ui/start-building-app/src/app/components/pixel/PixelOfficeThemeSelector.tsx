import { Palette } from "lucide-react";
import type { PixelLocale } from "./pixelModel";
import { PIXEL_OFFICE_THEME_LIST, type PixelOfficeThemeId } from "./pixelOfficeTheme";

interface PixelOfficeThemeSelectorProps {
  themeId: PixelOfficeThemeId;
  onChange: (themeId: PixelOfficeThemeId) => void;
  locale?: PixelLocale;
}

export function PixelOfficeThemeSelector({ themeId, onChange, locale = "en" }: PixelOfficeThemeSelectorProps) {
  const zh = locale === "zh";

  return (
    <section
      className="rounded-lg p-3"
      style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      aria-labelledby="pixel-office-theme-title"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div id="pixel-office-theme-title" className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
            <Palette size={15} style={{ color: "var(--mis-purple)" }} />
            {zh ? "办公室美术模板" : "Office art templates"}
          </div>
          <p className="mt-1 text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {zh
              ? "模板只改变场景、材质和像素角色外观；任务、运行、审批与审计仍来自同一套 MIS 账本。"
              : "Templates change scene materials and pixel characters only. Tasks, runs, approvals and audit remain on the same MIS ledger."}
          </p>
        </div>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={zh ? "选择办公室美术模板" : "Choose office art template"}>
          {PIXEL_OFFICE_THEME_LIST.map((theme) => {
            const selected = theme.id === themeId;
            return (
              <button
                key={theme.id}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => onChange(theme.id)}
                className="min-w-[132px] rounded-md px-2.5 py-2 text-left transition-opacity hover:opacity-90"
                style={{
                  background: selected ? "rgba(34,211,238,.1)" : "var(--mis-surface2)",
                  border: selected ? "1px solid var(--mis-cyan)" : "1px solid rgba(148,163,184,.16)",
                  boxShadow: selected ? "0 0 0 2px rgba(34,211,238,.08)" : "none",
                }}
              >
                <span className="flex gap-1" aria-hidden="true">
                  {theme.swatches.map((swatch) => (
                    <span key={swatch} className="h-3 flex-1 rounded-sm" style={{ background: swatch }} />
                  ))}
                </span>
                <span className="mt-1.5 block text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>
                  {theme.label[locale]}
                </span>
                <span className="mt-0.5 block text-[9px] leading-snug" style={{ color: "var(--mis-muted)" }}>
                  {theme.description[locale]}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}