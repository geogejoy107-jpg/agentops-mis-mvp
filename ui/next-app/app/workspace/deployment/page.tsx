import { DeploymentParityPage } from "@/components/DeploymentPage";
import {
  loadServerAudit,
  loadServerCommercialEntitlements,
  loadServerDeploymentReadiness,
  loadServerLocalReadiness,
  loadServerSecurityProductionReadiness,
  loadServerStorageBackendStatus,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function DeploymentPage() {
  const [deployment, local, security, entitlements, storage, audit] = await Promise.all([
    loadServerDeploymentReadiness(),
    loadServerLocalReadiness(),
    loadServerSecurityProductionReadiness(),
    loadServerCommercialEntitlements(),
    loadServerStorageBackendStatus(),
    loadServerAudit(80),
  ]);
  return (
    <DeploymentParityPage
      deployment={deployment.data}
      local={local.data}
      security={security.data}
      entitlements={entitlements.data}
      storage={storage.data}
      audit={audit.data}
      errors={[deployment.error, local.error, security.error, entitlements.error, storage.error, audit.error].filter(Boolean) as string[]}
    />
  );
}
