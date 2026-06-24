import { CommercialParityPage } from "@/components/CommercialPage";
import { loadServerCommercialEntitlements, loadServerCommercialReleaseStatus } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

function queryFlag(value: string | string[] | undefined) {
  const candidate = String(one(value) || "").trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(candidate);
}

export default async function CommercialPage({ searchParams }: PageProps) {
  const params = await (searchParams || Promise.resolve({} as SearchParams));
  const [entitlements, releaseStatus] = await Promise.all([
    loadServerCommercialEntitlements(),
    loadServerCommercialReleaseStatus({
      includeExternalCi: queryFlag(params.exact_head_ci) || queryFlag(params.include_external_ci_evidence),
      externalCiRunId: one(params.external_ci_run_id),
    }),
  ]);
  return (
    <CommercialParityPage
      entitlements={entitlements.data}
      error={entitlements.error}
      releaseStatus={releaseStatus.data}
      releaseError={releaseStatus.error}
    />
  );
}
