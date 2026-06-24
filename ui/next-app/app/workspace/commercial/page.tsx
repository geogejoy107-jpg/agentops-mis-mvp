import { CommercialParityPage } from "@/components/CommercialPage";
import { loadServerCommercialEntitlements, loadServerCommercialReleaseStatus } from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function CommercialPage() {
  const [entitlements, releaseStatus] = await Promise.all([
    loadServerCommercialEntitlements(),
    loadServerCommercialReleaseStatus(),
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
