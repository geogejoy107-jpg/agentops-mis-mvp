import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import { Check, Palette } from "lucide-react";
import type { PixelLocale } from "./pixelModel";
import { PIXEL_OFFICE_THEME_LIST, type PixelOfficeThemeId } from "./pixelOfficeTheme";

interface PixelOfficeThemeSelectorProps {
  themeId: PixelOfficeThemeId;
  onChange: (themeId: PixelOfficeThemeId) => void;
  locale?: PixelLocale;
}

function themeButtonId(themeId: PixelOfficeThemeId) {
  return `pixel-office-theme-${themeId}`;
}

export function PixelOfficeThemeSelector({ themeId, onChange, locale = "en" }: PixelOfficeThemeSelectorProps) {
  const zh = locale === "zh";

  const selectIndex = (index: number) => {
    const theme = PIXEL_OFFICE_THEME_LIST[index];
    if (!theme) return;
    onChange(theme.id);
    window.requestAnimationFrame(() => document.getElementById(themeButtonId(theme.id))?.focus());
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLButtonElement>, index: number) => {
    let targetIndex: number | null = null;
    if (event.key === "ArrowRight" || event.key === "ArrowDown") {
      targetIndex = (index + 1) % PIXEL_OFFICE_THEME_LIST.length;
    } else if (event.key === "ArrowLeft" || event.key === "ArrowUp") {
      targetIndex = (index - 1 + PIXEL_OFFICE_THEME_LIST.length) % PIXEL_OFFICE_THEME_LIST.length;
    } else if (event.key === "Home") {
      targetIndex = 0;
    } else if (event.key === "End") {
      targetIndex = PIXEL_OFFICE_THEME_LIST.length - 1;
    }

    if (targetIndex !== null) {
      event.preventDefault();
      selectIndex(targetIndex);
    }
  };

  return (
    <section
      className="rounded-lg p-3"
      style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}
      aria-labelledby="pixel-office-theme-title"
      data-testid="pixel-office-theme-selector"
    >
      <div>
        <div id="pixel-office-theme-title" className="flex items-center gap-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
          <Palette size={15} style={{ color: "var(--mis-purple)" }} />
          {zh ? "办公室美术模板" : "Office art templates"}
          <span className="rounded-full px-1.5 py-0.5 text-[9px] font-mono" style={{ background: "var(--mis-surface2)", color: "var(--mis-muted)" }}>
            {PIXEL_OFFICE_THEME_LIST.length}
          </span>
        </div>
        <p className="mt-1 max-w-3xl text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
          {zh
            ? "模板只改变场景、材质和像素角色外观；任务、运行、审批与审计仍来自同一套 MIS 账本。方向键可快速切换模板。"
            : "Templates change scene materials and pixel characters only. Tasks, runs, approvals and audit remain on the same MIS ledger. Use arrow keys to switch styles."}
        </p>
      </div>

      <div
        className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5"
        role="radiogroup"
        aria-label={zh ? "选择办公室美术模板" : "Choose office art template"}
      >
        {PIXEL_OFFICE_THEME_LIST.map((theme, index) => {
          const selected = theme.id === themeId;
          const accent = theme.swatches[1] || theme.swatches[0];
          const descriptionId = `${themeButtonId(theme.id)}-description`;
          return (
            <button
              id={themeButtonId(theme.id)}
              key={theme.id}
              type="button"
              role="radio"
              aria-checked={selected}
              aria-describedby={descriptionId}
              tabIndex={selected ? 0 : -1}
              onClick={() => onChange(theme.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className="group relative min-h-[112px] rounded-md px-2.5 py-2 text-left transition-transform duration-150 hover:-translate-y-0.5"
              style={{
                background: selected ? `${accent}18` : "var(--mis-surface2)",
                border: selected ? `1px solid ${accent}` : "1px solid rgba(148,163,184,.16)",
                boxShadow: selected ? `0 0 0 2px ${accent}16, 0 8px 20px rgba(2,6,23,.16)` : "none",
              }}
              data-theme-id={theme.id}
            >
              {selected && (
                <span
                  className="absolute right-2 top-2 inline-flex h-5 w-5 items-center justify-center rounded-full"
                  style={{ background: accent, color: theme.swatches[0] }}
                  aria-hidden="true"
                >
                  <Check size={12} strokeWidth={3} />
                </span>
              )}
              <span className="flex gap-1 pr-7" aria-hidden="true">
                {theme.swatches.map((swatch) => (
                  <span key={swatch} className="h-4 flex-1 rounded-sm" style={{ background: swatch, border: "1px solid rgba(255,255,255,.08)" }} />
                ))}
              </span>
              <span className="mt-2 block text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>
                {theme.label[locale]}
              </span>
              <span id={descriptionId} className="mt-1 block text-[9px] leading-snug" style={{ color: "var(--mis-muted)" }}>
                {theme.description[locale]}
              </span>
            </button>
          );
        })}
      </div>
    </section>
  );
}
