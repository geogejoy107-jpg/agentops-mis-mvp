import { RunDetailClientPage } from "@/components/LedgerDetailPages";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ runId: string }>;
};

export default async function RunPage({ params }: PageProps) {
  const { runId } = await params;
  return <RunDetailClientPage runId={runId} />;
}
