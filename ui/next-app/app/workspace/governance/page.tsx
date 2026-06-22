import { GovernanceParityPage } from "@/components/GovernancePage";
import {
  loadServerAudit,
  loadServerCommercialEntitlements,
  loadServerGatewaySessions,
  loadServerSecurityProductionReadiness,
  loadServerWorkerStatus,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function GovernancePage() {
  const [security, entitlements, worker, sessions, audit] = await Promise.all([
    loadServerSecurityProductionReadiness(),
    loadServerCommercialEntitlements(),
    loadServerWorkerStatus(),
    loadServerGatewaySessions(),
    loadServerAudit(80),
  ]);
  return (
    <GovernanceParityPage
      security={security.data}
      entitlements={entitlements.data}
      worker={worker.data}
      sessions={sessions.data}
      audit={audit.data}
      errors={[security.error, entitlements.error, worker.error, sessions.error, audit.error].filter(Boolean) as string[]}
    />
  );
}
