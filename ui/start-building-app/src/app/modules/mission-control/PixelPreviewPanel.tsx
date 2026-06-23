import { Link } from "react-router";
import { ArrowRight } from "lucide-react";
import type { PixelAgent, PixelMetrics, PixelTaskCard } from "../../components/pixel/pixelModel";
import { PixelOperatingMap } from "../../components/pixel/PixelOperatingMap";
import { SectionHeader } from "../../design-system/PageHeader";
import type { SectionCopy } from "./types";

export function PixelPreviewPanel(props: {
  copy: SectionCopy;
  agents: PixelAgent[];
  taskCards: PixelTaskCard[];
  metrics: PixelMetrics;
  locale: "en" | "zh";
  onOpenRoute: (route: string) => void;
}) {
  const { copy, agents, taskCards, metrics, locale, onOpenRoute } = props;
  return (
    <section className="ui-v2-card overflow-hidden p-4 sm:p-5 xl:col-span-7">
      <SectionHeader
        title={copy.title}
        description={copy.description}
        action={<Link to="/pixel-office" className="inline-flex items-center gap-1 text-xs" style={{ color: "var(--ui-accent-strong)" }}>{copy.open}<ArrowRight size={13} /></Link>}
      />
      <div className="overflow-hidden rounded-lg">
        <PixelOperatingMap compact agents={agents} taskCards={taskCards} metrics={metrics} onOpenRoute={onOpenRoute} locale={locale} />
      </div>
    </section>
  );
}
