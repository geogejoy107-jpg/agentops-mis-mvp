import { useMemo } from "react";
import { useNavigate } from "react-router";
import { Bot, Boxes, ClipboardCheck, RefreshCw, Siren } from "lucide-react";
import { usePreferences } from "../../context/PreferencesContext";
import { derivePixelAgents, derivePixelMetrics, deriveTaskCards } from "../../components/pixel/pixelModel";
import { ErrorState, StaleDataBanner } from "../../design-system/States";
import { MetricCard } from "../../design-system/MetricCard";
import { PageHeader } from "../../design-system/PageHeader";
import { StatusPill } from "../../design-system/Pills";
import { AttentionPanel } from "./AttentionPanel";
import { WorkPackagesPanel } from "./WorkPackagesPanel";
import { WorkforcePanel } from "./WorkforcePanel";
import { ActivityPanel } from "./ActivityPanel";
import { PixelPreviewPanel } from "./PixelPreviewPanel";
import { missionControlCopy } from "./copy";
import { activityViews, attentionViews, incidentSummary, packageViews, workforceView } from "./model";
import { useMissionControlData } from "./useMissionControlData";

export function MissionControl() {
  const { locale } = usePreferences();
  const navigate = useNavigate();
  const copy = missionControlCopy(locale);
  const { data, loading, error, refresh } = useMissionControlData();

  const agents = data?.agents || [];
  const tasks = data?.tasks || [];
  const approvals = data?.approvals || [];
  const runs = data?.runs || [];
  const memories = data?.memories || [];
  const audit = data?.audit || [];

  const pixelMetrics = useMemo(
    () => derivePixelMetrics({ metrics: data?.metrics, tasks, approvals, runs, memories, audit }),
    [data?.metrics, tasks, approvals, runs, memories, audit],
  );
  const pixelAgents = useMemo(
    () => derivePixelAgents({ agents, tasks, approvals, runs, memories }),
    [agents, tasks, approvals, runs, memories],
  );
  const taskCards = useMemo(() => deriveTaskCards(tasks), [tasks]);

  if (error && !data) {
    return (
      <div className="ui-v2-page">
        <PageHeader eyebrow={copy.eyebrow} title={copy.title} description={copy.description} />
        <div className="mt-5"><ErrorState title={copy.unavailableMission} description={error} onRetry={refresh} /></div>
      </div>
    );
  }

  const attention = data ? attentionViews(data) : [];
  const packages = data ? packageViews(data, locale) : { available: false, visible: 0, items: [] };
  const workforce = data ? workforceView(data) : { available: false, status: "unavailable", laneCount: 0, localDaemons: 0, runningDaemons: 0, stuckWork: 0, lanes: [] };
  const incidents = data ? incidentSummary(data) : { runs: [], tasks: [] };
  const activity = data ? activityViews(data) : [];
  const reviewCount = data?.reviewQueue ? data.reviewQueue.summary.review_items_total : data?.metrics?.pending_approvals;

  return (
    <div className="ui-v2-page space-y-5">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.description}
        badges={<StatusPill status={loading ? "checking" : "ready"} label={loading ? copy.loading : copy.live} />}
        actions={
          <button type="button" onClick={refresh} className="ui-v2-interactive inline-flex min-h-9 items-center gap-2 rounded-md border px-3 text-xs font-medium" style={{ background: "var(--ui-surface-1)", borderColor: "var(--ui-border)", color: "var(--ui-text)" }}>
            <RefreshCw size={14} className={loading ? "animate-spin" : ""} />{copy.refresh}
          </button>
        }
      />

      {data?.partialErrors.length ? <StaleDataBanner message={`${copy.partial} (${data.partialErrors.length})`} checkedAt={data.checkedAt} /> : null}

      <AttentionPanel copy={copy.attention} items={attention} />

      <section className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <MetricCard label={copy.activePackages} value={packages.available ? packages.items.length : "—"} detail={packages.available ? `${packages.visible} ${copy.packagesVisible}` : copy.unavailablePackages} tone="info" icon={<Boxes size={17} />} />
        <MetricCard label={copy.runningAgents} value={data?.metrics ? data.metrics.agents_running : "—"} detail={data?.metrics ? `${data.metrics.agents_total} ${copy.agentsTotal}` : undefined} tone="success" icon={<Bot size={17} />} />
        <MetricCard label={copy.pendingReviews} value={reviewCount ?? "—"} detail={data?.reviewQueue ? `${data.reviewQueue.summary.pending_approvals} ${copy.approvals}` : undefined} tone="warning" icon={<ClipboardCheck size={17} />} />
        <MetricCard label={copy.incidents24} value={data ? incidents.runs.length : "—"} detail={`${incidents.tasks.length} ${copy.failedTasks}`} tone={incidents.runs.length ? "danger" : "neutral"} icon={<Siren size={17} />} />
      </section>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <WorkPackagesPanel copy={copy.packages} available={packages.available} items={packages.items} unavailableTitle={copy.unavailablePackages} unavailableDescription={copy.unavailablePackagesDescription} evidenceLabel={copy.evidence} />
        <WorkforcePanel copy={copy.workforce} workforce={workforce} unavailableTitle={copy.workforce.emptyTitle} daemonLabel={copy.daemons} stuckLabel={copy.stuck} lanesLabel={copy.lanes} />
      </div>

      <div className="grid grid-cols-1 gap-5 xl:grid-cols-12">
        <ActivityPanel copy={copy.activity} items={activity} />
        <PixelPreviewPanel copy={copy.pixel} agents={pixelAgents} taskCards={taskCards} metrics={pixelMetrics} locale={locale} onOpenRoute={(route) => navigate(route)} />
      </div>
    </div>
  );
}
