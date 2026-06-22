import { ReportsParityPage } from "@/components/DeliveryPages";
import { loadServerCustomerDeliveryBoard, loadServerCustomerProjects } from "@/lib/misServer";

export const dynamic = "force-dynamic";

export default async function ReportsPage() {
  const [projects, deliveryBoard] = await Promise.all([
    loadServerCustomerProjects(25),
    loadServerCustomerDeliveryBoard(12),
  ]);

  return (
    <ReportsParityPage
      projects={projects.data}
      projectsError={projects.error}
      deliveryBoard={deliveryBoard.data}
      deliveryBoardError={deliveryBoard.error}
    />
  );
}
