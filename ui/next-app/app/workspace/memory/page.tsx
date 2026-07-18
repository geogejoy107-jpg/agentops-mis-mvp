import { MemoryParityPage } from "@/components/GovernancePages";
import { loadServerMemories } from "@/lib/misServer";
import { controlPlaneMode, isProductionDeployment } from "@/server/controlPlane/config";

export const dynamic = "force-dynamic";

export default async function MemoryPage() {
  if (isProductionDeployment() || controlPlaneMode() === "postgres") {
    return <MemoryParityPage />;
  }
  const initial = await loadServerMemories();
  return <MemoryParityPage initialMemories={initial.data} initialError={initial.error} initialLoaded />;
}
