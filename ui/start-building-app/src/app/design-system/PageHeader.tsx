import type { ReactNode } from "react";

export function PageHeader({ eyebrow, title, description, badges, actions }: { eyebrow?: string; title: string; description?: string; badges?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="flex flex-col gap-4 border-b pb-5 sm:flex-row sm:items-start sm:justify-between" style={{ borderColor: "var(--ui-border)" }}>
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-semibold uppercase tracking-[0.14em]" style={{ color: "var(--ui-accent-strong)" }}>{eyebrow}</div>}
        <div className="flex flex-wrap items-center gap-2"><h1 className="text-[22px] font-semibold leading-tight" style={{ color: "var(--ui-text)" }}>{title}</h1>{badges}</div>
        {description && <p className="mt-2 max-w-3xl text-sm leading-relaxed" style={{ color: "var(--ui-text-muted)" }}>{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function SectionHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return (
    <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
      <div><h2 className="text-sm font-semibold" style={{ color: "var(--ui-text)" }}>{title}</h2>{description && <p className="mt-0.5 text-xs" style={{ color: "var(--ui-text-muted)" }}>{description}</p>}</div>
      {action}
    </div>
  );
}
