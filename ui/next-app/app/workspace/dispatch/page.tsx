import { DispatchParityPage } from "@/components/DispatchPage";
import { loadServerAgents, loadServerCommercialEntitlements, loadServerCustomerTaskTemplates, loadServerCustomerWorkerPreparedActions, loadServerWorkflowJobs } from "@/lib/misServer";

export const dynamic = "force-dynamic";

type PageProps = {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
};

type SearchParams = Record<string, string | string[] | undefined>;

function one(value: string | string[] | undefined) {
  return Array.isArray(value) ? value[0] : value;
}

export default async function DispatchPage({ searchParams }: PageProps) {
  const [entitlements, agents, templates, workflowJobs, preparedActions, params] = await Promise.all([
    loadServerCommercialEntitlements(),
    loadServerAgents(),
    loadServerCustomerTaskTemplates(),
    loadServerWorkflowJobs(),
    loadServerCustomerWorkerPreparedActions(),
    searchParams || Promise.resolve({} as SearchParams),
  ]);
  return (
    <DispatchParityPage
      entitlements={entitlements.data}
      entitlementsError={entitlements.error}
      agents={agents.data}
      agentsError={agents.error}
      templates={templates.data}
      templatesError={templates.error}
      workflowJobs={workflowJobs.data}
      workflowJobsError={workflowJobs.error}
      preparedActions={preparedActions.data}
      preparedActionsError={preparedActions.error}
      feedback={{
        status: one(params.run_status),
        capability: one(params.capability),
        requiredEdition: one(params.required_edition),
        currentEdition: one(params.current_edition),
        projectId: one(params.project_id),
        error: one(params.error),
        customerTaskStatus: one(params.customer_task_status),
        customerTaskId: one(params.customer_task_id),
        customerTaskRunId: one(params.customer_task_run_id),
        customerTaskPromptHash: one(params.customer_task_prompt_hash),
        customerTaskError: one(params.customer_task_error),
        templateJobStatus: one(params.template_job_status),
        templateJobId: one(params.template_job_id),
        templateJobError: one(params.template_job_error),
        customerWorkerStatus: one(params.customer_worker_status),
        customerWorkerAdapter: one(params.customer_worker_adapter),
        customerWorkerTaskId: one(params.customer_worker_task_id),
        customerWorkerRunId: one(params.customer_worker_run_id),
        customerWorkerArtifactId: one(params.customer_worker_artifact_id),
        customerWorkerManifestId: one(params.customer_worker_manifest_id),
        customerWorkerApprovalId: one(params.customer_worker_approval_id),
        customerWorkerPreparedActionId: one(params.customer_worker_prepared_action_id),
        customerWorkerPreparedStatus: one(params.customer_worker_prepared_status),
        customerWorkerRequestHash: one(params.customer_worker_request_hash),
        customerWorkerError: one(params.customer_worker_error),
        customerWorkerJobStatus: one(params.customer_worker_job_status),
        customerWorkerJobId: one(params.customer_worker_job_id),
        customerWorkerJobPreparedActionId: one(params.customer_worker_job_prepared_action_id),
        customerWorkerJobPreparedStatus: one(params.customer_worker_job_prepared_status),
        customerWorkerJobRequestHash: one(params.customer_worker_job_request_hash),
        customerWorkerJobApprovalId: one(params.customer_worker_job_approval_id),
      }}
    />
  );
}
