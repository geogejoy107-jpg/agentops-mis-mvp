import Link from "next/link";
import { Clock3, LockKeyhole, Play, ShieldCheck, Workflow } from "lucide-react";
import { AppFrame } from "./AppFrame";
import type { CommercialEntitlementStatus, CustomerTaskTemplateListPayload, CustomerWorkerPreparedAction, CustomerWorkerPreparedActionListPayload, WorkflowJobListPayload } from "@/lib/mis";

type DispatchFeedback = {
  status?: string;
  capability?: string;
  requiredEdition?: string;
  currentEdition?: string;
  projectId?: string;
  error?: string;
  customerWorkerStatus?: string;
  customerWorkerAdapter?: string;
  customerWorkerTaskId?: string;
  customerWorkerRunId?: string;
  customerWorkerArtifactId?: string;
  customerWorkerManifestId?: string;
  customerWorkerApprovalId?: string;
  customerWorkerPreparedActionId?: string;
  customerWorkerPreparedStatus?: string;
  customerWorkerRequestHash?: string;
  customerWorkerError?: string;
  customerWorkerJobStatus?: string;
  customerWorkerJobId?: string;
  customerWorkerJobPreparedActionId?: string;
  customerWorkerJobPreparedStatus?: string;
  customerWorkerJobRequestHash?: string;
  customerWorkerJobApprovalId?: string;
};

function boolText(value: unknown) {
  if (value === true) return "true";
  if (value === false) return "false";
  return "unknown";
}

function gateFor(entitlements: CommercialEntitlementStatus, capability: string) {
  return (entitlements.gates || []).find((gate) => gate.capability === capability);
}

function shortId(value?: string) {
  if (!value) return "none";
  return value.length > 18 ? `${value.slice(0, 18)}...` : value;
}

function workerDefaults(action: CustomerWorkerPreparedAction) {
  if (action.async_job) {
    return {
      route: "/workspace/dispatch/customer-worker-job",
      title: action.resume_form?.title || "Next async customer worker job",
      workerAgentId: action.resume_form?.worker_agent_id || action.requested_by_agent_id || "agt_next_customer_worker_async",
      description: action.resume_form?.description || "Next.js submits one safe async customer-worker job and reads job status back through the MIS proxy.",
      acceptance: action.resume_form?.acceptance_criteria || "Workflow job must complete with run, artifact, delivery approval, and verified plan evidence without token leakage.",
      label: "Resume job",
    };
  }
  return {
    route: "/workspace/dispatch/customer-worker",
    title: action.resume_form?.title || "Next customer worker dispatch",
    workerAgentId: action.resume_form?.worker_agent_id || action.requested_by_agent_id || "agt_next_customer_worker",
    description: action.resume_form?.description || "Next.js dispatches one safe mock customer-worker task and reads back ledger evidence.",
    acceptance: action.resume_form?.acceptance_criteria || "Worker must write run, tool, evaluation, audit, artifact, memory, approval, and verified plan evidence.",
    label: "Resume worker",
  };
}

export function DispatchParityPage({
  entitlements,
  entitlementsError,
  templates,
  templatesError,
  workflowJobs,
  workflowJobsError,
  preparedActions,
  preparedActionsError,
  feedback,
}: Readonly<{
  entitlements: CommercialEntitlementStatus;
  entitlementsError?: string | null;
  templates: CustomerTaskTemplateListPayload;
  templatesError?: string | null;
  workflowJobs: WorkflowJobListPayload;
  workflowJobsError?: string | null;
  preparedActions: CustomerWorkerPreparedActionListPayload;
  preparedActionsError?: string | null;
  feedback?: DispatchFeedback;
}>) {
  const reportTemplateGate = gateFor(entitlements, "report_templates");
  const reportTemplatesEnabled = Boolean(entitlements.capabilities?.report_templates);
  const rows = templates.templates || [];
  const jobs = workflowJobs.jobs || [];
  const preparedQueue = preparedActions.prepared_actions || [];

  return (
    <AppFrame>
      <header className="topbar">
        <div>
          <p className="eyebrow">Customer dispatch parity route</p>
          <h1>Dispatch</h1>
          <p className="subtle">Template-backed customer work entry with commercial fail-closed gates</p>
        </div>
        <Link className="miniButton" href="/workspace/reports">Reports</Link>
      </header>

      {entitlementsError ? <div className="banner error">Entitlements unavailable: {entitlementsError}</div> : null}
      {templatesError ? <div className="banner error">Templates unavailable: {templatesError}</div> : null}
      {workflowJobsError ? <div className="banner error">Workflow jobs unavailable: {workflowJobsError}</div> : null}
      {preparedActionsError ? <div className="banner error">Prepared actions unavailable: {preparedActionsError}</div> : null}
      {feedback?.status === "blocked" ? (
        <div className="banner warn">
          <strong>Entitlement required:</strong> {feedback.capability || "report_templates"} requires {feedback.requiredEdition || "pro_workspace"}; current edition is {feedback.currentEdition || entitlements.edition || "free_local"}.
        </div>
      ) : null}
      {feedback?.status === "started" && feedback.projectId ? (
        <div className="banner success">
          Customer project started: <Link href={`/workspace/customer-projects/${encodeURIComponent(feedback.projectId)}/report`}>{feedback.projectId}</Link>
        </div>
      ) : null}
      {feedback?.customerWorkerStatus === "blocked" ? (
        <div className="banner warn">
          <strong>Worker dispatch blocked:</strong> {feedback.customerWorkerError || "adapter_invalid"} · adapter {feedback.customerWorkerAdapter || "unknown"}
        </div>
      ) : null}
      {feedback?.customerWorkerStatus === "waiting_approval" && feedback.customerWorkerPreparedActionId ? (
        <div className="banner warn">
          <strong>Worker dispatch prepared:</strong> approval {feedback.customerWorkerApprovalId || "pending"} must be approved before exact resume · action {shortId(feedback.customerWorkerPreparedActionId)}
        </div>
      ) : null}
      {feedback?.customerWorkerStatus === "started" && feedback.customerWorkerTaskId ? (
        <div className="banner success">
          Customer worker dispatched: <Link href={`/workspace/tasks/${encodeURIComponent(feedback.customerWorkerTaskId)}`}>{feedback.customerWorkerTaskId}</Link>
        </div>
      ) : null}
      {feedback?.customerWorkerStatus === "failed" ? <div className="banner error">Customer worker failed: {feedback.customerWorkerError || "unknown"}</div> : null}
      {feedback?.customerWorkerJobStatus === "blocked" ? (
        <div className="banner warn">
          <strong>Async worker job blocked:</strong> {feedback.customerWorkerError || "adapter_invalid"} · adapter {feedback.customerWorkerAdapter || "unknown"}
        </div>
      ) : null}
      {feedback?.customerWorkerJobStatus === "waiting_approval" && feedback.customerWorkerJobPreparedActionId ? (
        <div className="banner warn">
          <strong>Async worker job prepared:</strong> approval {feedback.customerWorkerJobApprovalId || "pending"} must be approved before exact resume · action {shortId(feedback.customerWorkerJobPreparedActionId)}
        </div>
      ) : null}
      {feedback?.customerWorkerJobStatus === "submitted" && feedback.customerWorkerJobId ? (
        <div className="banner success">Async customer worker job submitted: {feedback.customerWorkerJobId}</div>
      ) : null}
      {feedback?.customerWorkerJobStatus === "failed" ? <div className="banner error">Async worker job failed: {feedback.customerWorkerError || "unknown"}</div> : null}
      {feedback?.error ? <div className="banner error">Dispatch failed: {feedback.error}</div> : null}

      <section className="grid">
        <div className="panel">
          <div className="panelHeader">
            <h2><ShieldCheck size={14} /> Edition gate</h2>
            <span>{entitlements.edition_label || entitlements.edition || "Free Local"}</span>
          </div>
          <div className="proofStrip">
            <span>report_templates {boolText(reportTemplatesEnabled)}</span>
            <span>required {reportTemplateGate?.required_edition || "pro_workspace"}</span>
            <span>billing call {boolText(entitlements.safety?.billing_call_performed)}</span>
            <span>token omitted {boolText(entitlements.token_omitted)}</span>
          </div>
        </div>
        <div className="panel">
          <div className="panelHeader">
            <h2><LockKeyhole size={14} /> Safety contract</h2>
            <span>{reportTemplatesEnabled ? "enabled" : "fail-closed"}</span>
          </div>
          <p className="subtle">
            Free Local can inspect templates and reports, but template execution is blocked until the report_templates capability is enabled.
          </p>
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Workflow size={14} /> Customer task templates</h2>
          <span>{rows.length} templates</span>
        </div>
        <div className="list">
          {rows.length ? rows.map((template) => (
            <article className="row tall" key={template.template_id}>
              <div>
                <strong>{template.name_en || template.name || template.template_id}</strong>
                <span>{template.template_id} · {template.workflow || "workflow"} · {template.status || "status unknown"}</span>
                <p>{template.description || template.default_description || "No template description loaded."}</p>
              </div>
              <div className="rowActions">
                <span className="metaPill">risk {template.risk_level || "medium"}</span>
                <span className="metaPill">approvals {(template.required_approvals || []).length}</span>
                <form method="post" action="/workspace/dispatch/template-run">
                  <input type="hidden" name="template_id" value={template.template_id} />
                  <button className={`miniButton ${reportTemplatesEnabled ? "good" : ""}`} type="submit">
                    <Play size={13} /> Start template
                  </button>
                </form>
              </div>
            </article>
          )) : <p className="empty">No customer task templates loaded.</p>}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Workflow size={14} /> Customer worker dispatch</h2>
          <span>prepared-action gated</span>
        </div>
        <div className="proofStrip">
          <span>adapter {feedback?.customerWorkerAdapter || "mock"}</span>
          <span>task {feedback?.customerWorkerTaskId ? <Link href={`/workspace/tasks/${encodeURIComponent(feedback.customerWorkerTaskId)}`}>{feedback.customerWorkerTaskId}</Link> : "none"}</span>
          <span>run {feedback?.customerWorkerRunId ? <Link href={`/workspace/runs/${encodeURIComponent(feedback.customerWorkerRunId)}`}>{feedback.customerWorkerRunId}</Link> : "none"}</span>
          <span>artifact {feedback?.customerWorkerArtifactId || "none"}</span>
          <span>manifest {feedback?.customerWorkerManifestId ? <Link href={`/workspace/evidence/${encodeURIComponent(feedback.customerWorkerManifestId)}`}>{feedback.customerWorkerManifestId}</Link> : "none"}</span>
          <span>approval {feedback?.customerWorkerApprovalId || "none"}</span>
          <span>prepared {shortId(feedback?.customerWorkerPreparedActionId)}</span>
          <span>request {shortId(feedback?.customerWorkerRequestHash)}</span>
          <span>prepared status {feedback?.customerWorkerPreparedStatus || "none"}</span>
        </div>
        <form className="formGrid" method="post" action="/workspace/dispatch/customer-worker">
          <label className="field">
            <span>Title</span>
            <input name="title" defaultValue="Next customer worker dispatch" />
          </label>
          <label className="field">
            <span>Adapter</span>
            <select name="adapter" defaultValue="mock">
              <option value="mock">mock</option>
              <option value="hermes">hermes</option>
              <option value="openclaw">openclaw</option>
            </select>
          </label>
          <label className="field">
            <span>Worker agent</span>
            <input name="worker_agent_id" defaultValue="agt_next_customer_worker" />
          </label>
          <label className="field wideField">
            <span>Description</span>
            <textarea name="description" defaultValue="Next.js dispatches one safe mock customer-worker task and reads back ledger evidence." />
          </label>
          <label className="field wideField">
            <span>Acceptance</span>
            <textarea name="acceptance_criteria" defaultValue="Worker must write run, tool, evaluation, audit, artifact, memory, approval, and verified plan evidence." />
          </label>
          <button className="miniButton good" type="submit"><Play size={13} /> Dispatch worker</button>
        </form>
        {feedback?.customerWorkerStatus === "waiting_approval" && feedback.customerWorkerPreparedActionId && feedback.customerWorkerRequestHash ? (
          <form className="formGrid" method="post" action="/workspace/dispatch/customer-worker">
            <input type="hidden" name="adapter" value={feedback.customerWorkerAdapter || "openclaw"} />
            <input type="hidden" name="prepared_action_id" value={feedback.customerWorkerPreparedActionId} />
            <input type="hidden" name="request_hash" value={feedback.customerWorkerRequestHash} />
            <input type="hidden" name="title" value="Next customer worker dispatch" />
            <input type="hidden" name="worker_agent_id" value="agt_next_customer_worker" />
            <input type="hidden" name="description" value="Next.js dispatches one safe mock customer-worker task and reads back ledger evidence." />
            <input type="hidden" name="acceptance_criteria" value="Worker must write run, tool, evaluation, audit, artifact, memory, approval, and verified plan evidence." />
            <button className="miniButton" type="submit"><ShieldCheck size={13} /> Resume approved worker</button>
          </form>
        ) : null}
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><ShieldCheck size={14} /> Prepared worker actions</h2>
          <span>{preparedQueue.length} resumable checks</span>
        </div>
        <div className="proofStrip">
          <span>workflow {preparedActions.workflow || "customer_worker_task"}</span>
          <span>raw request omitted {boolText(preparedActions.raw_request_omitted)}</span>
          <span>raw result omitted {boolText(preparedActions.raw_result_omitted)}</span>
          <span>token omitted {boolText(preparedActions.token_omitted)}</span>
        </div>
        <div className="list" data-smoke="customer-worker-prepared-actions">
          {preparedQueue.length ? preparedQueue.map((action) => {
            const defaults = workerDefaults(action);
            return (
              <article className="row tall" key={action.prepared_action_id}>
                <div>
                  <strong>{action.async_job ? "Async worker prepared action" : "Worker prepared action"}</strong>
                  <span>{shortId(action.prepared_action_id)} · {action.status || "status unknown"} · approval {action.approval_decision || "unknown"}</span>
                  <p>request {shortId(action.request_hash || action.request_hash_short || "")} · adapter {action.adapter || "unknown"} · target {action.target_resource || "agentops://workflow/customer-worker-task"}</p>
                </div>
                <div className="rowActions">
                  <span className="metaPill">raw omitted {boolText(action.raw_request_omitted)}</span>
                  <span className="metaPill">resume {boolText(action.can_resume)}</span>
                  {action.task_id ? <Link className="miniButton" href={`/workspace/tasks/${encodeURIComponent(action.task_id)}`}>Task</Link> : null}
                  {action.run_id ? <Link className="miniButton" href={`/workspace/runs/${encodeURIComponent(action.run_id)}`}>Run</Link> : null}
                  {action.can_resume && action.request_hash ? (
                    <form method="post" action={defaults.route}>
                      <input type="hidden" name="adapter" value={action.adapter || "openclaw"} />
                      <input type="hidden" name="prepared_action_id" value={action.prepared_action_id} />
                      <input type="hidden" name="request_hash" value={action.request_hash} />
                      <input type="hidden" name="title" value={defaults.title} />
                      <input type="hidden" name="worker_agent_id" value={defaults.workerAgentId} />
                      <input type="hidden" name="description" value={defaults.description} />
                      <input type="hidden" name="acceptance_criteria" value={defaults.acceptance} />
                      <input type="hidden" name="priority" value={action.resume_form?.priority || "high"} />
                      <input type="hidden" name="risk_level" value={action.resume_form?.risk_level || "medium"} />
                      <button className="miniButton" type="submit"><ShieldCheck size={13} /> {defaults.label}</button>
                    </form>
                  ) : null}
                  {action.waiting_for_approval ? <Link className="miniButton" href="/workspace/approvals">Approvals</Link> : null}
                </div>
              </article>
            );
          }) : <p className="empty">No prepared customer-worker actions loaded.</p>}
        </div>
      </section>

      <section className="panel wide">
        <div className="panelHeader">
          <h2><Clock3 size={14} /> Async worker jobs</h2>
          <span>{jobs.length} recent</span>
        </div>
        <div className="proofStrip">
          <span>submit prepared-action gated</span>
          <span>token omitted {boolText(workflowJobs.token_omitted)}</span>
          <span>last job {feedback?.customerWorkerJobId || jobs[0]?.job_id || "none"}</span>
          <span>prepared {shortId(feedback?.customerWorkerJobPreparedActionId)}</span>
          <span>request {shortId(feedback?.customerWorkerJobRequestHash)}</span>
          <span>prepared status {feedback?.customerWorkerJobPreparedStatus || "none"}</span>
        </div>
        <form className="formGrid" method="post" action="/workspace/dispatch/customer-worker-job">
          <label className="field">
            <span>Title</span>
            <input name="title" defaultValue="Next async customer worker job" />
          </label>
          <label className="field">
            <span>Adapter</span>
            <select name="adapter" defaultValue="mock">
              <option value="mock">mock</option>
              <option value="hermes">hermes</option>
              <option value="openclaw">openclaw</option>
            </select>
          </label>
          <label className="field">
            <span>Worker agent</span>
            <input name="worker_agent_id" defaultValue="agt_next_customer_worker_async" />
          </label>
          <label className="field wideField">
            <span>Description</span>
            <textarea name="description" defaultValue="Next.js submits one safe async customer-worker job and reads job status back through the MIS proxy." />
          </label>
          <label className="field wideField">
            <span>Acceptance</span>
            <textarea name="acceptance_criteria" defaultValue="Workflow job must complete with run, artifact, delivery approval, and verified plan evidence without token leakage." />
          </label>
          <button className="miniButton good" type="submit"><Clock3 size={13} /> Submit async job</button>
        </form>
        {feedback?.customerWorkerJobStatus === "waiting_approval" && feedback.customerWorkerJobPreparedActionId && feedback.customerWorkerJobRequestHash ? (
          <form className="formGrid" method="post" action="/workspace/dispatch/customer-worker-job">
            <input type="hidden" name="adapter" value={feedback.customerWorkerAdapter || "hermes"} />
            <input type="hidden" name="prepared_action_id" value={feedback.customerWorkerJobPreparedActionId} />
            <input type="hidden" name="request_hash" value={feedback.customerWorkerJobRequestHash} />
            <input type="hidden" name="title" value="Next async customer worker job" />
            <input type="hidden" name="worker_agent_id" value="agt_next_customer_worker_async" />
            <input type="hidden" name="description" value="Next.js submits one safe async customer-worker job and reads job status back through the MIS proxy." />
            <input type="hidden" name="acceptance_criteria" value="Workflow job must complete with run, artifact, delivery approval, and verified plan evidence without token leakage." />
            <button className="miniButton" type="submit"><ShieldCheck size={13} /> Resume approved job</button>
          </form>
        ) : null}
        <div className="list">
          {jobs.length ? jobs.map((job) => (
            <article className="row tall" key={job.job_id}>
              <div>
                <strong>{job.title || job.job_id}</strong>
                <span>{job.job_id} · {job.workflow_type || "workflow"} · {job.status || "status unknown"}</span>
                <p>{job.input_summary || job.error_message || "No job summary loaded."}</p>
              </div>
              <div className="rowActions">
                <span className="metaPill">adapter {job.adapter || "mock"}</span>
                <span className="metaPill">raw omitted {boolText(job.raw_request_omitted)}</span>
                {job.result_task_id ? <Link className="miniButton" href={`/workspace/tasks/${encodeURIComponent(job.result_task_id)}`}>Task</Link> : null}
                {job.result_run_id ? <Link className="miniButton" href={`/workspace/runs/${encodeURIComponent(job.result_run_id)}`}>Run</Link> : null}
                {job.result?.plan_evidence_manifest_id ? <Link className="miniButton" href={`/workspace/evidence/${encodeURIComponent(job.result.plan_evidence_manifest_id)}`}>Evidence</Link> : null}
              </div>
            </article>
          )) : <p className="empty">No workflow jobs loaded.</p>}
        </div>
      </section>
    </AppFrame>
  );
}
