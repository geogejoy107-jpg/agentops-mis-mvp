import { CommercialParityPage } from "@/components/CommercialPage";
import { loadServerCommercialEntitlements } from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function CommercialPage() {
  const entitlements = await loadServerCommercialEntitlements();
  return <CommercialParityPage entitlements={entitlements.data} error={entitlements.error} />;
}
