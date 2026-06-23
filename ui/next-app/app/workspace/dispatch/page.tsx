import { DispatchParityPage } from "@/components/DispatchPage";
import { loadServerCommercialEntitlements, loadServerCustomerTaskTemplates } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function DispatchPage({ searchParams }: PageProps) {
  const [entitlements, templates, params] = await Promise.all([
    loadServerCommercialEntitlements(),
    loadServerCustomerTaskTemplates(),
    searchParams || Promise.resolve({} as SearchParams),
  ]);
  return (
    <DispatchParityPage
      entitlements={entitlements.data}
      entitlementsError={entitlements.error}
      templates={templates.data}
      templatesError={templates.error}
      feedback={{
        status: one(params.run_status),
        capability: one(params.capability),
        requiredEdition: one(params.required_edition),
        currentEdition: one(params.current_edition),
        projectId: one(params.project_id),
        error: one(params.error),
        customerWorkerStatus: one(params.customer_worker_status),
        customerWorkerAdapter: one(params.customer_worker_adapter),
        customerWorkerTaskId: one(params.customer_worker_task_id),
        customerWorkerRunId: one(params.customer_worker_run_id),
        customerWorkerArtifactId: one(params.customer_worker_artifact_id),
        customerWorkerManifestId: one(params.customer_worker_manifest_id),
        customerWorkerApprovalId: one(params.customer_worker_approval_id),
        customerWorkerError: one(params.customer_worker_error),
      }}
    />
  );
}
