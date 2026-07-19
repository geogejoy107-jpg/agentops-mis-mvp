import { PixelOfficeLivePage } from "@/components/PixelOfficePage";

export const dynamic = "force-dynamic";

type SearchParams = Record<string, string | string[] | undefined>;
type PageProps = {
  searchParams?: Promise<SearchParams>;
};

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function PixelOfficePage({ searchParams }: PageProps) {
  const params = await (searchParams || Promise.resolve({} as SearchParams));

  return (
    <PixelOfficeLivePage
      feedback={{
        localBriefStatus: one(params.local_brief_status),
        localBriefError: one(params.local_brief_error),
        localBriefPromptHash: one(params.local_brief_prompt_hash),
        localBriefStateHash: one(params.local_brief_state_hash),
        localBriefAgentsTotal: one(params.local_brief_agents_total),
        localBriefPendingApprovals: one(params.local_brief_pending_approvals),
        localBriefRecentRealRuns: one(params.local_brief_recent_real_runs),
        localBriefPreparedActionId: one(params.local_brief_prepared_action_id),
        localBriefApprovalId: one(params.local_brief_approval_id),
        localBriefPreparedStatus: one(params.local_brief_prepared_status),
        localBriefRunId: one(params.local_brief_run_id),
        localBriefArtifactId: one(params.local_brief_artifact_id),
      }}
    />
  );
}
