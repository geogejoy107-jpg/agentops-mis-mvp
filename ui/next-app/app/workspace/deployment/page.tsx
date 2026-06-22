import { DeploymentParityPage } from "@/components/DeploymentPage";
import {
  loadServerAudit,
  loadServerCommercialEntitlements,
  loadServerLocalReadiness,
  loadServerSecurityProductionReadiness,
  loadServerStorageBackendStatus,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function DeploymentPage() {
  const [local, security, entitlements, storage, audit] = await Promise.all([
    loadServerLocalReadiness(),
    loadServerSecurityProductionReadiness(),
    loadServerCommercialEntitlements(),
    loadServerStorageBackendStatus(),
    loadServerAudit(80),
  ]);
  return (
    <DeploymentParityPage
      local={local.data}
      security={security.data}
      entitlements={entitlements.data}
      storage={storage.data}
      audit={audit.data}
      errors={[local.error, security.error, entitlements.error, storage.error, audit.error].filter(Boolean) as string[]}
    />
  );
}
