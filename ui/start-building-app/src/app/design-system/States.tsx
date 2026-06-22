import type { ReactNode } from "react";
import { AlertTriangle, Inbox, RefreshCw } from "lucide-react";

export function EmptyState({ title, description, action, icon }: { title: string; description?: string; action?: ReactNode; icon?: ReactNode }) {
  return <div className="flex min-h-40 flex-col items-center justify-center rounded-lg border border-dashed p-6 text-center" style={{ borderColor: "var(--ui-border)", background: "var(--ui-surface-2)" }}><div className="mb-3 flex h-9 w-9 items-center justify-center rounded-lg" style={{ background: "var(--ui-surface-1)", color: "var(--ui-text-subtle)" }}>{icon || <Inbox size={18} />}</div><h3 className="text-sm font-semibold" style={{ color: "var(--ui-text)" }}>{title}</h3>{description && <p className="mt-1 max-w-md text-xs leading-relaxed" style={{ color: "var(--ui-text-muted)" }}>{description}</p>}{action && <div className="mt-4">{action}</div>}</div>;
}

export function ErrorState({ title, description, onRetry }: { title: string; description?: string; onRetry?: () => void }) {
  return <div className="rounded-lg border p-5" style={{ borderColor: "rgba(239,68,68,.35)", background: "rgba(239,68,68,.07)" }} role="alert"><div className="flex items-start gap-3"><AlertTriangle size={18} className="mt-0.5 shrink-0" style={{ color: "var(--ui-danger)" }} /><div className="min-w-0 flex-1"><h3 className="text-sm font-semibold" style={{ color: "var(--ui-text)" }}>{title}</h3>{description && <p className="mt-1 break-words text-xs leading-relaxed" style={{ color: "var(--ui-text-muted)" }}>{description}</p>}{onRetry && <button type="button" onClick={onRetry} className="ui-v2-interactive mt-3 inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs" style={{ borderColor: "var(--ui-border)", background: "var(--ui-surface-1)", color: "var(--ui-text)" }}><RefreshCw size={13} /> Retry</button>}</div></div></div>;
}

export function StaleDataBanner({ message, checkedAt }: { message: string; checkedAt?: string }) {
  return <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-xs" style={{ borderColor: "rgba(245,158,11,.30)", background: "rgba(245,158,11,.07)", color: "var(--ui-text-muted)" }}><span>{message}</span>{checkedAt && <time dateTime={checkedAt} style={{ color: "var(--ui-text-subtle)" }}>{new Date(checkedAt).toLocaleString()}</time>}</div>;
}
