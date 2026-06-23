import { Link } from "react-router";
import { Activity, ArrowRight } from "lucide-react";
import { EmptyState } from "../../design-system/States";
import { StatusPill } from "../../design-system/Pills";
import { SectionHeader } from "../../design-system/PageHeader";
import type { ActivityView, SectionCopy } from "./types";

export function ActivityPanel({ copy, items }: { copy: SectionCopy; items: ActivityView[] }) {
  return (
    <section className="ui-v2-card p-4 sm:p-5 xl:col-span-5">
      <SectionHeader
        title={copy.title}
        description={copy.description}
        action={<Link to="/observe/incidents" className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--ui-accent-strong)" }}>{copy.open}<ArrowRight size={13} /></Link>}
      />
      {items.length === 0 ? (
        <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />
      ) : (
        <div className="space-y-2">
          {items.slice(0, 8).map((item) => (
            <Link key={item.id} to={item.route} className="ui-v2-interactive flex items-center gap-3 rounded-md border px-3 py-2.5" style={{ borderColor: "var(--ui-border)" }}>
              <Activity size={14} style={{ color: "var(--ui-text-subtle)" }} />
              <span className="min-w-0 flex-1"><strong className="block truncate text-xs font-medium" style={{ color: "var(--ui-text)" }}>{item.title}</strong><span className="block truncate text-[11px]" style={{ color: "var(--ui-text-subtle)" }}>{item.meta || "—"}</span></span>
              <StatusPill status={item.status} />
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
