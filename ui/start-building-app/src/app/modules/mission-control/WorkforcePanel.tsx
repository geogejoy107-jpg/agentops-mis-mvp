import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import { EmptyState } from "../../design-system/States";
import { StatusPill } from "../../design-system/Pills";
import { SectionHeader } from "../../design-system/PageHeader";
import type { SectionCopy, WorkforceView } from "./types";

export function WorkforcePanel(props: {
  copy: SectionCopy;
  workforce: WorkforceView;
  unavailableTitle: string;
  daemonLabel: string;
  stuckLabel: string;
  lanesLabel: string;
}) {
  const { copy, workforce, unavailableTitle, daemonLabel, stuckLabel, lanesLabel } = props;
  return (
    <section className="ui-v2-card p-4 sm:p-5 xl:col-span-4">
      <SectionHeader
        title={copy.title}
        description={copy.description}
        action={<Link to="/workforce/workers" className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--ui-accent-strong)" }}>{copy.open}<ArrowRight size={13} /></Link>}
      />
      {!workforce.available ? (
        <EmptyState title={unavailableTitle} />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between rounded-lg border p-3" style={{ borderColor: "var(--ui-border)", background: "var(--ui-surface-2)" }}>
            <div><div className="text-xs" style={{ color: "var(--ui-text-muted)" }}>{lanesLabel}</div><div className="mt-1 text-lg font-semibold">{workforce.laneCount}</div></div>
            <StatusPill status={workforce.status} />
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="rounded-md border p-2" style={{ borderColor: "var(--ui-border)" }}><span style={{ color: "var(--ui-text-muted)" }}>{daemonLabel}</span><strong className="mt-1 block text-base">{workforce.runningDaemons}/{workforce.localDaemons}</strong></div>
            <div className="rounded-md border p-2" style={{ borderColor: "var(--ui-border)" }}><span style={{ color: "var(--ui-text-muted)" }}>{stuckLabel}</span><strong className="mt-1 block text-base">{workforce.stuckWork}</strong></div>
          </div>
          {workforce.lanes.slice(0, 4).map((lane) => (
            <div key={lane.id} className="flex items-center justify-between gap-2 text-xs"><span className="truncate" style={{ color: "var(--ui-text-muted)" }}>{lane.name}</span><StatusPill status={lane.status} /></div>
          ))}
        </div>
      )}
    </section>
  );
}
