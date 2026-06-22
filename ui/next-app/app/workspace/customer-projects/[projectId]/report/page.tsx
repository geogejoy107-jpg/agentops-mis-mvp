import { CustomerProjectReportParityPage } from "@/components/DeliveryPages";
import { loadServerCustomerProjectReport } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ projectId: string }>;
};

export default async function CustomerProjectReportPage({ params }: PageProps) {
  const { projectId } = await params;
  const report = await loadServerCustomerProjectReport(projectId);
  return <CustomerProjectReportParityPage projectId={projectId} report={report.data} error={report.error} />;
}
