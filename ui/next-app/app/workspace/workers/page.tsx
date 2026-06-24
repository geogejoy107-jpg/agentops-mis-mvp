import { WorkerConsolePage } from "@/components/WorkerConsolePage";
import {
  loadServerGatewaySessions,
  loadServerLocalReadiness,
  loadServerOperatorExecutionMode,
  loadServerWorkerAdapterReadiness,
  loadServerWorkerFleet,
  loadServerWorkerFleetHygiene,
  loadServerWorkerStatus,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function WorkersPage() {
  const [workerStatus, workerFleet, workerHygiene, adapterReadiness, sessions, localReadiness, executionMode] = await Promise.all([
    loadServerWorkerStatus(),
    loadServerWorkerFleet(),
    loadServerWorkerFleetHygiene(8),
    loadServerWorkerAdapterReadiness(),
    loadServerGatewaySessions(),
    loadServerLocalReadiness(),
    loadServerOperatorExecutionMode(),
  ]);

  return (
    <WorkerConsolePage
      adapterReadiness={adapterReadiness}
      executionMode={executionMode}
      localReadiness={localReadiness}
      sessions={sessions}
      workerFleet={workerFleet}
      workerHygiene={workerHygiene}
      workerStatus={workerStatus}
    />
  );
}
