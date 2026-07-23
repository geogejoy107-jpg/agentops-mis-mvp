import { TaskDetailClientPage } from "@/components/LedgerDetailPages";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ taskId: string }>;
};

export default async function TaskPage({ params }: PageProps) {
  const { taskId } = await params;
  return <TaskDetailClientPage taskId={taskId} />;
}
