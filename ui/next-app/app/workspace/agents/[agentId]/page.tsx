import { AgentDetailParityPage } from "@/components/AgentDetailPage";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ agentId: string }>;
};

export default async function AgentDetailRoute({ params }: PageProps) {
  const { agentId } = await params;
  return <AgentDetailParityPage agentId={agentId} />;
}
