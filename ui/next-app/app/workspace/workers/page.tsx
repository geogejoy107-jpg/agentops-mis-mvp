import { WorkerConsolePage } from "@/components/WorkerConsolePage";
import {
  loadServerGatewaySessions,
  loadServerLocalReadiness,
  loadServerWorkerAdapterReadiness,
  loadServerWorkerFleet,
  loadServerWorkerFleetHygiene,
  loadServerWorkerStatus,
} from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function WorkersPage() {
  const [workerStatus, workerFleet, workerHygiene, adapterReadiness, sessions, localReadiness] = await Promise.all([
    loadServerWorkerStatus(),
    loadServerWorkerFleet(),
    loadServerWorkerFleetHygiene(8),
    loadServerWorkerAdapterReadiness(),
    loadServerGatewaySessions(),
    loadServerLocalReadiness(),
  ]);

  return (
    <WorkerConsolePage
      adapterReadiness={adapterReadiness}
      localReadiness={localReadiness}
      sessions={sessions}
      workerFleet={workerFleet}
      workerHygiene={workerHygiene}
      workerStatus={workerStatus}
    />
  );
}
