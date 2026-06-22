import { MemoryParityPage } from "@/components/GovernancePages";
import { loadServerMemories } from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function MemoryPage() {
  const initial = await loadServerMemories();
  return <MemoryParityPage initialMemories={initial.data} initialError={initial.error} initialLoaded />;
}
