import { redirect } from "next/navigation";

type PageProps = {
  params: Promise<{ taskId: string }>;
};

export default async function LegacyTaskDetailRedirect({ params }: PageProps) {
  const { taskId } = await params;
  redirect(`/workspace/tasks/${encodeURIComponent(taskId)}`);
}
