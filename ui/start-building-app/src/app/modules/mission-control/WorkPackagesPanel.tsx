import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import { EmptyState } from "../../design-system/States";
import { RiskPill, StatusPill } from "../../design-system/Pills";
import { SectionHeader } from "../../design-system/PageHeader";
import type { SectionCopy, WorkPackageView } from "./types";

export function WorkPackagesPanel(props: {
  copy: SectionCopy;
  available: boolean;
  items: WorkPackageView[];
  unavailableTitle: string;
  unavailableDescription: string;
  evidenceLabel: string;
}) {
  const { copy, available, items, unavailableTitle, unavailableDescription, evidenceLabel } = props;
  return (
    <section className="ui-v2-card p-4 sm:p-5 xl:col-span-8">
      <SectionHeader title={copy.title} description={copy.description} action={
        <Link to="/work-packages" className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--ui-accent-strong)" }}>
          {copy.open}<ArrowRight size={13} />
        </Link>
      } />
      {!available ? (
        <EmptyState title={unavailableTitle} description={unavailableDescription} />
      ) : items.length === 0 ? (
        <EmptyState title={copy.emptyTitle} description={copy.emptyDescription} />
      ) : (
        <div className="space-y-2">
          {items.slice(0, 6).map((item) => (
            <Link
              key={item.id}
              to={"/admin/tasks/" + item.taskId}
              className="ui-v2-interactive grid grid-cols-1 gap-3 rounded-lg border p-3 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center"
              style={{ borderColor: "var(--ui-border)", background: "var(--ui-surface-2)" }}
            >
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <strong className="truncate text-sm font-medium" style={{ color: "var(--ui-text)" }}>{item.title}</strong>
                  <StatusPill status={item.status} />
                </div>
                <div className="mt-1 truncate text-xs" style={{ color: "var(--ui-text-muted)" }}>{item.owner} · {item.project}</div>
              </div>
              <RiskPill risk={item.risk} />
              <div className="text-left text-[11px] sm:text-right" style={{ color: "var(--ui-text-subtle)" }}>{item.evidence} {evidenceLabel}</div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}
