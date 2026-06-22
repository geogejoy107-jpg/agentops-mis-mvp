import { RunDetailPage } from "@/components/LedgerDetailPages";
import { loadServerRunDetail } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ runId: string }>;
};

export default async function RunPage({ params }: PageProps) {
  const { runId } = await params;
  const snapshot = await loadServerRunDetail(runId);
  return <RunDetailPage runId={runId} snapshot={snapshot.data} error={snapshot.error} />;
}
