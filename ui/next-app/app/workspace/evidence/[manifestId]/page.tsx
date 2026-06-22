import { EvidenceDrilldownPage } from "@/components/EvidencePage";
import { loadServerEvidenceDrilldown } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ manifestId: string }>;
};

export default async function EvidencePage({ params }: PageProps) {
  const { manifestId } = await params;
  const evidence = await loadServerEvidenceDrilldown(manifestId);
  return <EvidenceDrilldownPage manifestId={manifestId} evidence={evidence.data} error={evidence.error} />;
}
