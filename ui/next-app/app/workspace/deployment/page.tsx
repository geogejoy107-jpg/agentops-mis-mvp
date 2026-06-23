import { DeploymentParityPage } from "@/components/DeploymentPage";
import {
  loadServerAudit,
  loadServerAuditRetentionControls,
  loadServerAuditRetentionPolicy,
  loadServerCommercialEntitlements,
  loadServerDeploymentReadiness,
  loadServerLocalReadiness,
  loadServerSecurityProductionReadiness,
  loadServerStorageBackendStatus,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function DeploymentPage() {
  const [deployment, retentionPolicy, retentionControls, local, security, entitlements, storage, audit] = await Promise.all([
    loadServerDeploymentReadiness(),
    loadServerAuditRetentionPolicy(),
    loadServerAuditRetentionControls(),
    loadServerLocalReadiness(),
    loadServerSecurityProductionReadiness(),
    loadServerCommercialEntitlements(),
    loadServerStorageBackendStatus(),
    loadServerAudit(80),
  ]);
  return (
    <DeploymentParityPage
      deployment={deployment.data}
      retentionPolicy={retentionPolicy.data}
      retentionControls={retentionControls.data}
      local={local.data}
      security={security.data}
      entitlements={entitlements.data}
      storage={storage.data}
      audit={audit.data}
      errors={[deployment.error, retentionPolicy.error, retentionControls.error, local.error, security.error, entitlements.error, storage.error, audit.error].filter(Boolean) as string[]}
    />
  );
}
