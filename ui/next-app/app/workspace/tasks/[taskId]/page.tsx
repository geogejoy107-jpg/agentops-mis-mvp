import { TaskDetailPage } from "@/components/LedgerDetailPages";
import { loadServerTaskDetail } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ taskId: string }>;
};

export default async function TaskPage({ params }: PageProps) {
  const { taskId } = await params;
  const detail = await loadServerTaskDetail(taskId);
  return <TaskDetailPage taskId={taskId} detail={detail.data} error={detail.error} />;
}
