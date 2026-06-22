import { redirect } from "next/navigation";

type PageProps = {
  params: Promise<{ runId: string }>;
};

export default async function LegacyRunDetailRedirect({ params }: PageProps) {
  const { runId } = await params;
  redirect(`/workspace/runs/${encodeURIComponent(runId)}`);
}
