import { DeploymentParityPage } from "@/components/DeploymentPage";
import {
  loadServerAudit,
  loadServerCommercialEntitlements,
  loadServerLocalReadiness,
  loadServerSecurityProductionReadiness,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function DeploymentPage() {
  const [local, security, entitlements, audit] = await Promise.all([
    loadServerLocalReadiness(),
    loadServerSecurityProductionReadiness(),
    loadServerCommercialEntitlements(),
    loadServerAudit(80),
  ]);
  return (
    <DeploymentParityPage
      local={local.data}
      security={security.data}
      entitlements={entitlements.data}
      audit={audit.data}
      errors={[local.error, security.error, entitlements.error, audit.error].filter(Boolean) as string[]}
    />
  );
}
