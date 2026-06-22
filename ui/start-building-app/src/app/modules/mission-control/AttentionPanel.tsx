import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import { EmptyState } from "../../design-system/States";
import { StatusPill } from "../../design-system/Pills";
import { SectionHeader } from "../../design-system/PageHeader";
import type { AttentionView, SectionCopy } from "./types";

export function AttentionPanel({ copy, items }: { copy: SectionCopy; items: AttentionView[] }) {
  return (
    <section className="ui-v2-card p-4 sm:p-5">
      <SectionHeader
        title={copy.title}
        description={copy.description}
        action={<Link to="/human-review" className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--ui-accent-strong)" }}>{copy.open}<ArrowRight size={13} /></Link>}
      />
      {items.length === 0 ? (
        <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />
      ) : (
        <div className="divide-y" style={{ borderColor: "var(--ui-border)" }}>
          {items.map((item) => (
            <Link key={item.id} to={item.route} className="ui-v2-interactive flex items-start gap-3 py-3 text-left first:pt-1 last:pb-1">
              <StatusPill status={item.severity} />
              <span className="min-w-0 flex-1">
                <strong className="block truncate text-sm font-medium" style={{ color: "var(--ui-text)" }}>{item.title}</strong>
                <span className="mt-0.5 block text-xs leading-relaxed" style={{ color: "var(--ui-text-muted)" }}>{item.summary}</span>
              </span>
              <span className="hidden shrink-0 text-[11px] sm:block" style={{ color: "var(--ui-text-subtle)" }}>{item.source}</span>
              <ArrowRight size={14} className="mt-1 shrink-0" style={{ color: "var(--ui-text-subtle)" }} />
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
