import { ApprovalsParityPage } from "@/components/LedgerPages";
import { loadServerApprovals } from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function ApprovalsPage() {
  const initial = await loadServerApprovals();
  return <ApprovalsParityPage initialApprovals={initial.data} initialError={initial.error} initialLoaded />;
}
