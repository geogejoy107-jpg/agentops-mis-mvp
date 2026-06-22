import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Archive, CheckCircle2, ClipboardCheck, Clock3, Loader2, Play, RefreshCw, ShieldCheck } from "lucide-react";
import type { Agent } from "../../data/mockData";
import {
  loadWorkflowJobs,
  loadCustomerTaskTemplates,
  persistCustomerProjectReportArtifact,
  runCustomerTaskTemplateWorkflow,
  runCustomerTaskWorkflow,
  runCustomerWorkerTaskWorkflow,
  submitCustomerWorkerTaskJob,
  submitCustomerTaskTemplateJob,
  type CustomerTaskTemplate,
  type CustomerProjectReportArtifactResult,
  type CustomerTaskWorkflowResult,
  type KbBotProjectWorkflowResult,
  type WorkflowJob,
} from "../../data/liveApi";
import type { PixelLocale } from "./pixelModel";

interface CustomerDispatchPanelProps {
  agents: Agent[];
  locale: PixelLocale;
  onRefresh: () => void;
}

const riskOptions = ["low", "medium", "high"] as const;
const workerAdapters = ["mock", "hermes", "openclaw"] as const;

function evidenceLine(evidence?: CustomerTaskWorkflowResult["evidence"]) {
  if (!evidence) return null;
  return `tool ${evidence.tool_calls || 0} · eval ${evidence.evaluations || 0} · audit ${evidence.audit_logs || 0} · artifact ${evidence.artifacts || 0} · approval ${evidence.approvals || 0}`;
}

function workflowLabel(job: WorkflowJob, zh: boolean) {
  if (job.workflow_type === "customer_worker_task") return zh ? "客户 Worker Job" : "Customer worker job";
  if (job.workflow_type === "customer_task_template") return zh ? "模板项目 Job" : "Template project job";
  return job.workflow_type || (zh ? "Workflow Job" : "Workflow job");
}

const DEFAULT_COPY = {
  en: {
    title: "Build a formal AI knowledge base / Q&A bot",
    description: "Customer task: clean source material into Markdown/PDF/DOCX, choose Dify or OpenAI File Search or AnythingLLM, design chunking, embeddings, vector storage, source citations and the assistant workflow.",
    acceptance: "MIS must create task decomposition, run ledger, tool calls, approval for external upload, memory candidates, evaluation and audit evidence. Do not store credentials, full private chats or raw documents.",
  },
  zh: {
    title: "搭建正式 AI 知识库 / 问答机器人",
    description: "客户任务：把原始资料清洗成 Markdown / PDF / DOCX，选择 Dify、OpenAI File Search 或 AnythingLLM，设计分块、Embedding、向量库、来源引用和 AI 问答工作流。",
    acceptance: "MIS 必须生成任务拆解、运行账本、工具调用、外部上传审批、记忆候选、质量评估和审计证据；不能保存凭证、完整私聊或原始资料全文。",
  },
};

export function CustomerDispatchPanel({ agents, locale, onRefresh }: CustomerDispatchPanelProps) {
  const zh = locale === "zh";
  const runnableAgents = useMemo(
    () => agents.filter((agent) => ["openclaw", "hermes", "codex", "claude_code", "mock"].includes(agent.runtime_type)).slice(0, 8),
    [agents],
  );
  const defaultSelected = useMemo(
    () => runnableAgents.filter((agent) => ["openclaw", "hermes"].includes(agent.runtime_type)).slice(0, 3).map((agent) => agent.agent_id),
    [runnableAgents],
  );
  const initialCopy = DEFAULT_COPY[locale];
  const [title, setTitle] = useState(initialCopy.title);
  const [description, setDescription] = useState(initialCopy.description);
  const [acceptance, setAcceptance] = useState(initialCopy.acceptance);
  const [risk, setRisk] = useState<(typeof riskOptions)[number]>("medium");
  const [selected, setSelected] = useState<string[]>(defaultSelected);
  const [busy, setBusy] = useState(false);
  const [workerBusy, setWorkerBusy] = useState(false);
  const [kbBusy, setKbBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [jobBusy, setJobBusy] = useState(false);
  const [templateJobBusy, setTemplateJobBusy] = useState(false);
  const [result, setResult] = useState<CustomerTaskWorkflowResult | null>(null);
  const [kbResult, setKbResult] = useState<KbBotProjectWorkflowResult | null>(null);
  const [reportArtifact, setReportArtifact] = useState<CustomerProjectReportArtifactResult | null>(null);
  const [workflowJobs, setWorkflowJobs] = useState<WorkflowJob[]>([]);
  const [templates, setTemplates] = useState<CustomerTaskTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("tpl_customer_kb_qa_bot");
  const [workerAdapter, setWorkerAdapter] = useState<(typeof workerAdapters)[number]>("hermes");
  const [liveRuntimeConfirmed, setLiveRuntimeConfirmed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const liveAdapterConfirmMissing = workerAdapter !== "mock" && !liveRuntimeConfirmed;
  const customerDispatchMode = workerAdapter === "mock"
    ? {
      key: "mock_ledger_write",
      label: zh ? "Mock 真写账本" : "Mock ledger write",
      body: zh
        ? "不会调用 Hermes/OpenClaw，但会创建真实任务、run、tool/eval/audit 证据。"
        : "Does not call Hermes/OpenClaw, but creates real task, run, tool/eval/audit evidence.",
      tone: "success",
    }
    : liveRuntimeConfirmed
      ? {
        key: "real_runtime_confirmed",
        label: zh ? "真实 runtime 已确认" : "Real runtime confirmed",
        body: zh
          ? "下一次确认操作会调用本地 Hermes/OpenClaw adapter，并把摘要、hash 和证据写回 MIS。"
          : "The next confirmed action will call the local Hermes/OpenClaw adapter and write summary, hash and evidence back to MIS.",
        tone: "live",
      }
      : {
        key: "real_runtime_gated",
        label: zh ? "真实 runtime 锁定中" : "Real runtime gated",
        body: zh
          ? "Hermes/OpenClaw 需要先勾选显式确认；未确认前只能安全预演或 mock 写账本。"
          : "Hermes/OpenClaw require the explicit confirmation checkbox; until then use dry-run or mock ledger writes.",
        tone: "warning",
      };
  const safeDryRunLabel = zh ? "safe_dry_run：只做安全预演" : "safe_dry_run: preview only";
  const approvalPreparedActionLabel = zh ? "approval_prepared_action：外部写入需审批后精确恢复" : "approval_prepared_action: external writes require approval before exact resume";
  const resultLedgerState = result?.dry_run
    ? safeDryRunLabel
    : (result?.reason || "").includes("prepared_action") || (result?.evidence?.approvals || 0) > 0
      ? approvalPreparedActionLabel
      : workerAdapter === "mock"
        ? (zh ? "mock_ledger_write：已写入本地账本证据" : "mock_ledger_write: local ledger evidence written")
        : (zh ? "real_runtime_confirmed：真实 adapter 结果已入账" : "real_runtime_confirmed: real adapter result entered ledger");

  useEffect(() => {
    const next = DEFAULT_COPY[locale];
    const other = DEFAULT_COPY[locale === "zh" ? "en" : "zh"];
    setTitle((current) => current === other.title || current === "" ? next.title : current);
    setDescription((current) => current === other.description || current === "" ? next.description : current);
    setAcceptance((current) => current === other.acceptance || current === "" ? next.acceptance : current);
  }, [locale]);

  useEffect(() => {
    let cancelled = false;
    loadCustomerTaskTemplates()
      .then((payload) => {
        if (!cancelled) {
          setTemplates(payload.templates);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setTemplates([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const refreshWorkflowJobs = async () => {
    const payload = await loadWorkflowJobs(6);
    setWorkflowJobs(payload.jobs || []);
  };

  useEffect(() => {
    void refreshWorkflowJobs().catch(() => setWorkflowJobs([]));
  }, []);

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.template_id === selectedTemplateId),
    [templates, selectedTemplateId],
  );
  const kbFinalStep = useMemo(
    () => kbResult?.results?.[kbResult.results.length - 1],
    [kbResult],
  );
  const selectedAgentNames = useMemo(
    () => selected
      .map((agentId) => runnableAgents.find((agent) => agent.agent_id === agentId)?.name || agentId)
      .slice(0, 3)
      .join(", "),
    [runnableAgents, selected],
  );

  const applyTemplate = (template: CustomerTaskTemplate) => {
    setSelectedTemplateId(template.template_id);
    setTitle(template.default_title);
    setDescription(template.default_description);
    setAcceptance(template.default_acceptance);
    if (riskOptions.includes(template.risk_level as (typeof riskOptions)[number])) {
      setRisk(template.risk_level as (typeof riskOptions)[number]);
    }
  };

  const toggleAgent = (agentId: string) => {
    setSelected((current) =>
      current.includes(agentId) ? current.filter((id) => id !== agentId) : [...current, agentId],
    );
  };

  const submit = async (confirmRun: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const next = await runCustomerTaskWorkflow({
        title,
        description,
        acceptance_criteria: acceptance,
        priority: "high",
        risk_level: risk,
        owner_agent_id: selected[0],
        selected_agent_ids: selected,
        template_id: "tpl_ai_knowledge_base_bot",
        workflow_kind: "knowledge_base_bot",
        confirm_run: confirmRun,
      });
      setResult(next);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const runKbProject = async () => {
    setKbBusy(true);
    setError(null);
    try {
      const next = await runCustomerTaskTemplateWorkflow({
        template_id: selectedTemplateId,
        selected_agent_ids: selected,
        owner_agent_id: selected[0],
      });
      setKbResult(next);
      setReportArtifact(null);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setKbBusy(false);
    }
  };

  const runWorkerTask = async (confirmRun: boolean) => {
    setWorkerBusy(true);
    setError(null);
    try {
      const next = await runCustomerWorkerTaskWorkflow({
        title,
        description,
        acceptance_criteria: acceptance,
        priority: "high",
        risk_level: risk,
        owner_agent_id: selected[0],
        selected_agent_ids: selected,
        template_id: selectedTemplateId,
        workflow_kind: "customer_worker_task",
        adapter: workerAdapter,
        confirm_run: confirmRun,
      });
      setResult(next);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setWorkerBusy(false);
    }
  };

  const submitAsyncWorkerJob = async () => {
    setJobBusy(true);
    setError(null);
    try {
      const next = await submitCustomerWorkerTaskJob({
        template_id: selectedTemplateId,
        adapter: workerAdapter,
        confirm_run: true,
        selected_agent_ids: selected,
        owner_agent_id: selected[0],
        title,
        description,
        acceptance_criteria: acceptance,
        priority: "high",
        risk_level: risk,
      });
      setWorkflowJobs((current) => [next.job, ...current.filter((job) => job.job_id !== next.job_id)].slice(0, 6));
      await onRefresh();
      await refreshWorkflowJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setJobBusy(false);
    }
  };

  const submitAsyncTemplateJob = async () => {
    setTemplateJobBusy(true);
    setError(null);
    try {
      const next = await submitCustomerTaskTemplateJob({
        template_id: selectedTemplateId,
        adapter: workerAdapter,
        confirm_run: true,
        selected_agent_ids: selected,
        owner_agent_id: selected[0],
        title,
        description,
        acceptance_criteria: acceptance,
        priority: "high",
        risk_level: risk,
      });
      setWorkflowJobs((current) => [next.job, ...current.filter((job) => job.job_id !== next.job_id)].slice(0, 6));
      await onRefresh();
      await refreshWorkflowJobs();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setTemplateJobBusy(false);
    }
  };

  const persistReportArtifact = async () => {
    if (!kbResult?.project_id) return;
    setReportBusy(true);
    setError(null);
    try {
      const next = await persistCustomerProjectReportArtifact(kbResult.project_id);
      setReportArtifact(next);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setReportBusy(false);
    }
  };

  return (
    <section className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.25)" }}>
            <ShieldCheck size={12} />
            {zh ? "客户可用派活入口" : "Customer dispatch entry"}
          </div>
          <h2 className="mt-2 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>
            {zh ? "把任务交给 AI 团队，并让 MIS 自动记账" : "Give work to an AI team and let MIS record the ledger"}
          </h2>
          <p className="mt-1 max-w-3xl text-[11px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>
            {zh
              ? "顾客只需要写目标、验收标准和选择代理。安全预演会创建任务和计划事件；确认真实运行会调用本地 Agnesfallback。外部 Dify/OpenAI/AnythingLLM 写入必须进入审批。"
              : "Customers only write the goal, acceptance criteria and choose agents. Dry-run creates the task and planned event; confirmed live run calls local Agnesfallback. External Dify/OpenAI/AnythingLLM writes must enter approval."}
          </p>
        </div>
        {result?.task_id && (
          <div className="flex flex-wrap gap-2 text-[11px]">
            <Link className="rounded px-2.5 py-1.5" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }} to={`/admin/tasks/${result.task_id}`}>
              {zh ? "打开任务" : "Open task"}
            </Link>
            {result.run_id && (
              <Link className="rounded px-2.5 py-1.5" style={{ background: "rgba(168,85,247,0.12)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,0.26)" }} to={`/admin/runs/${result.run_id}`}>
                {zh ? "打开运行账本" : "Open run"}
              </Link>
            )}
          </div>
        )}
        {(kbResult?.task_id || kbFinalStep?.task_id) && (
          <div className="flex flex-wrap gap-2 text-[11px]">
            <Link className="rounded px-2.5 py-1.5" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }} to={`/admin/tasks/${kbResult.task_id || kbFinalStep?.task_id}`}>
              {zh ? "打开项目交付任务" : "Open project delivery task"}
            </Link>
            {(kbResult.run_id || kbFinalStep?.run_id) && (
              <Link className="rounded px-2.5 py-1.5" style={{ background: "rgba(168,85,247,0.12)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,0.26)" }} to={`/admin/runs/${kbResult.run_id || kbFinalStep?.run_id}`}>
                {zh ? "打开最终运行" : "Open final run"}
              </Link>
            )}
          </div>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-2">
        {[
          {
            title: zh ? "1. 创建任务" : "1. Create task",
            body: title.trim() || (zh ? "填写标题、说明和验收标准。" : "Fill title, brief and acceptance criteria."),
          },
          {
            title: zh ? "2. 选择团队" : "2. Choose team",
            body: selected.length ? `${selected.length} ${zh ? "个代理" : "agent(s)"} · ${selectedAgentNames || workerAdapter}` : (zh ? "选择 AI worker/team。" : "Select AI worker/team."),
          },
          {
            title: zh ? "3. 异步 Job" : "3. Async job",
            body: workflowJobs[0] ? `${workflowJobs[0].job_id} · ${workflowJobs[0].status}` : (zh ? "长任务提交后轮询账本结果。" : "Submit long work and poll ledger results."),
          },
          {
            title: zh ? "4. 证据" : "4. Evidence",
            body: evidenceLine(result?.evidence) || evidenceLine(workflowJobs[0]?.result?.evidence) || (zh ? "等待 run / artifact / eval / audit。" : "Waiting for run / artifact / eval / audit."),
          },
          {
            title: zh ? "5. 审批" : "5. Approval",
            body: result?.evidence?.approvals || kbResult?.approval_ids?.length || workflowJobs[0]?.result?.approval_ids?.length
              ? (zh ? "已有待处理交付审批。" : "Delivery approval is pending.")
              : (zh ? "外部上传和交付需审批。" : "External upload and delivery require approval."),
          },
          {
            title: zh ? "6. 报告" : "6. Report",
            body: kbResult?.project_id
              ? `${zh ? "项目报告" : "Project report"} ${kbResult.project_id}`
              : (zh ? "项目模板完成后打开交付报告。" : "Open delivery report after project completion."),
          },
        ].map((step) => (
          <div key={step.title} className="rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,0.14)" }}>
            <div className="flex items-center gap-2 text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>
              <ClipboardCheck size={13} style={{ color: "var(--mis-cyan)" }} />
              {step.title}
            </div>
            <p className="mt-1 text-[10px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{step.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 xl:grid-cols-3 gap-3">
        <label className="xl:col-span-1 text-[11px]" style={{ color: "var(--mis-muted)" }}>
          {zh ? "任务标题" : "Task title"}
          <input
            className="mt-1 w-full rounded px-3 py-2 text-xs outline-none"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <label className="xl:col-span-2 text-[11px]" style={{ color: "var(--mis-muted)" }}>
          {zh ? "任务说明" : "Task brief"}
          <textarea
            className="mt-1 h-20 w-full resize-none rounded px-3 py-2 text-xs outline-none"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
          />
        </label>
        <label className="xl:col-span-2 text-[11px]" style={{ color: "var(--mis-muted)" }}>
          {zh ? "验收标准" : "Acceptance criteria"}
          <textarea
            className="mt-1 h-16 w-full resize-none rounded px-3 py-2 text-xs outline-none"
            style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
            value={acceptance}
            onChange={(event) => setAcceptance(event.target.value)}
          />
        </label>
        <div className="text-[11px]" style={{ color: "var(--mis-muted)" }}>
          {zh ? "风险等级" : "Risk level"}
          <div className="mt-1 grid grid-cols-3 gap-1.5">
            {riskOptions.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => setRisk(item)}
                className="rounded px-2 py-2 text-[11px] capitalize"
                style={{
                  background: risk === item ? "rgba(34,211,238,0.12)" : "var(--mis-surface2)",
                  color: risk === item ? "var(--mis-cyan)" : "var(--mis-muted)",
                  border: risk === item ? "1px solid rgba(34,211,238,0.28)" : "1px solid var(--mis-border)",
                }}
              >
                {zh ? ({ low: "低", medium: "中", high: "高" }[item]) : item}
              </button>
            ))}
          </div>
        </div>
      </div>

      {templates.length > 0 && (
        <div className="mt-4">
          <div className="mb-2 text-[11px]" style={{ color: "var(--mis-muted)" }}>
            {zh ? "客户任务模板" : "Customer task templates"}
          </div>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-2">
            {templates.map((template) => {
              const active = selectedTemplateId === template.template_id;
              return (
                <button
                  key={template.template_id}
                  type="button"
                  onClick={() => applyTemplate(template)}
                  className="rounded p-3 text-left"
                  style={{
                    background: active ? "rgba(42,157,143,0.12)" : "var(--mis-surface2)",
                    border: active ? "1px solid rgba(42,157,143,0.30)" : "1px solid rgba(148,163,184,0.14)",
                  }}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? template.name : template.name_en || template.name}</span>
                    {active && <CheckCircle2 size={12} style={{ color: "var(--mis-success)" }} />}
                  </div>
                  <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed" style={{ color: "var(--mis-muted)" }}>{template.description}</p>
                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="rounded px-1.5 py-0.5 text-[9px]" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)" }}>{template.workflow}</span>
                    <span className="rounded px-1.5 py-0.5 text-[9px]" style={{ background: "rgba(168,85,247,0.10)", color: "var(--mis-purple)" }}>{template.risk_level}</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="mt-4">
        <div className="mb-2 text-[11px]" style={{ color: "var(--mis-muted)" }}>
          {zh ? "选择代理团队" : "Choose agent team"}
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
          {runnableAgents.map((agent) => {
            const active = selected.includes(agent.agent_id);
            return (
              <button
                key={agent.agent_id}
                type="button"
                onClick={() => toggleAgent(agent.agent_id)}
                className="rounded p-2 text-left"
                style={{
                  background: active ? "rgba(34,211,238,0.10)" : "var(--mis-surface2)",
                  border: active ? "1px solid rgba(34,211,238,0.28)" : "1px solid rgba(148,163,184,0.14)",
                }}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[11px] font-medium" style={{ color: "var(--mis-text)" }}>{agent.name}</span>
                  {active && <CheckCircle2 size={12} style={{ color: "var(--mis-cyan)" }} />}
                </div>
                <div className="mt-1 truncate text-[10px]" style={{ color: "var(--mis-muted)" }}>{agent.runtime_type} · {agent.role}</div>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1 rounded px-1 py-1" style={{ background: "var(--mis-surface2)", border: "1px solid var(--mis-border)" }}>
          {workerAdapters.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setWorkerAdapter(item)}
              className="rounded px-2 py-1 text-[10px] capitalize"
              style={{
                background: workerAdapter === item ? "rgba(34,211,238,0.14)" : "transparent",
                color: workerAdapter === item ? "var(--mis-cyan)" : "var(--mis-muted)",
              }}
            >
              {item}
            </button>
          ))}
        </div>
        <label
          className="inline-flex items-center gap-2 rounded px-2 py-1 text-[10px]"
          style={{
            color: liveRuntimeConfirmed ? "var(--mis-success)" : "var(--mis-warning)",
            background: liveRuntimeConfirmed ? "rgba(42,157,143,0.10)" : "rgba(251,191,36,0.10)",
            border: liveRuntimeConfirmed ? "1px solid rgba(42,157,143,0.22)" : "1px solid rgba(251,191,36,0.25)",
          }}
        >
          <input
            type="checkbox"
            checked={liveRuntimeConfirmed}
            onChange={(event) => setLiveRuntimeConfirmed(event.target.checked)}
          />
          {zh ? "我确认将运行真实 Hermes/OpenClaw adapter 并写入账本证据" : "I confirm this may run a real Hermes/OpenClaw adapter and write ledger evidence"}
        </label>
        <div
          className="basis-full rounded p-2 text-[10px] leading-relaxed"
          style={{
            background: customerDispatchMode.tone === "warning"
              ? "rgba(251,191,36,0.10)"
              : customerDispatchMode.tone === "live"
                ? "rgba(34,211,238,0.10)"
                : "rgba(42,157,143,0.10)",
            color: "var(--mis-text)",
            border: customerDispatchMode.tone === "warning"
              ? "1px solid rgba(251,191,36,0.24)"
              : customerDispatchMode.tone === "live"
                ? "1px solid rgba(34,211,238,0.24)"
                : "1px solid rgba(42,157,143,0.24)",
          }}
        >
          <div className="font-semibold" style={{ color: customerDispatchMode.tone === "warning" ? "#FBBF24" : customerDispatchMode.tone === "live" ? "var(--mis-cyan)" : "var(--mis-success)" }}>
            {customerDispatchMode.key} · {customerDispatchMode.label}
          </div>
          <div className="mt-1" style={{ color: "var(--mis-muted)" }}>{customerDispatchMode.body}</div>
          <div className="mt-1" style={{ color: "var(--mis-dim)" }}>{safeDryRunLabel} · {approvalPreparedActionLabel}</div>
        </div>
        <button
          type="button"
          onClick={() => runWorkerTask(false)}
          disabled={workerBusy || !title.trim()}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "rgba(148,163,184,0.10)", color: "var(--mis-text)", border: "1px solid rgba(148,163,184,0.20)" }}
        >
          {workerBusy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          {zh ? "Worker 执行" : "Run worker task"}
        </button>
        <button
          type="button"
          onClick={() => runWorkerTask(true)}
          disabled={workerBusy || !title.trim() || liveAdapterConfirmMissing}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "rgba(34,211,238,0.14)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.30)" }}
        >
          {workerBusy ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
          {zh ? "确认 Worker 运行" : "Confirm worker run"}
        </button>
        <button
          type="button"
          onClick={() => submit(false)}
          disabled={busy || !title.trim()}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "var(--mis-surface2)", color: "var(--mis-text)", border: "1px solid var(--mis-border)" }}
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <ShieldCheck size={13} />}
          {zh ? "先安全预演" : "Dry-run first"}
        </button>
        <button
          type="button"
          onClick={runKbProject}
          disabled={busy || kbBusy}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "rgba(42,157,143,0.14)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.30)" }}
        >
          {kbBusy ? <Loader2 size={13} className="animate-spin" /> : <CheckCircle2 size={13} />}
          {zh ? "按模板生成项目" : "Generate from template"}
        </button>
        <button
          type="button"
          onClick={submitAsyncWorkerJob}
          disabled={jobBusy || !title.trim() || liveAdapterConfirmMissing}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "rgba(168,85,247,0.14)", color: "var(--mis-purple)", border: "1px solid rgba(168,85,247,0.30)" }}
        >
          {jobBusy ? <Loader2 size={13} className="animate-spin" /> : <Clock3 size={13} />}
          {zh ? "异步提交 Worker Job" : "Submit async worker job"}
        </button>
        <button
          type="button"
          onClick={submitAsyncTemplateJob}
          disabled={templateJobBusy || !selectedTemplateId || liveAdapterConfirmMissing}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.26)" }}
        >
          {templateJobBusy ? <Loader2 size={13} className="animate-spin" /> : <Archive size={13} />}
          {zh ? "异步提交项目 Job" : "Submit async project job"}
        </button>
        <button
          type="button"
          onClick={() => submit(true)}
          disabled={busy || !title.trim() || liveAdapterConfirmMissing}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "rgba(34,211,238,0.14)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.30)" }}
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          {zh ? "确认真实运行" : "Confirm real run"}
        </button>
        <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
          {zh ? "mock worker 会真实写入账本；Hermes/OpenClaw 需要显式确认。长任务建议用异步 Job。" : "Mock worker writes real ledger evidence; Hermes/OpenClaw require explicit confirmation. Use async jobs for long runs."}
        </span>
      </div>

      <div className="mt-4 rounded p-3" style={{ background: "var(--mis-surface2)", border: "1px solid rgba(148,163,184,0.14)" }}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-[11px] font-semibold" style={{ color: "var(--mis-text)" }}>
              <Clock3 size={13} style={{ color: "var(--mis-purple)" }} />
              {zh ? "异步 Workflow Jobs" : "Async workflow jobs"}
            </div>
            <p className="mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>
              {zh ? "长时间 Hermes/OpenClaw 任务先提交 job，再从账本轮询结果。" : "Long Hermes/OpenClaw runs submit a job first, then poll ledger-backed results."}
            </p>
          </div>
          <button
            type="button"
            onClick={() => refreshWorkflowJobs().catch((err) => setError(err instanceof Error ? err.message : String(err)))}
            className="inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[10px]"
            style={{ background: "rgba(148,163,184,0.10)", color: "var(--mis-text)", border: "1px solid rgba(148,163,184,0.18)" }}
          >
            <RefreshCw size={12} />
            {zh ? "刷新" : "Refresh"}
          </button>
        </div>
        <div className="mt-3 grid grid-cols-1 lg:grid-cols-2 gap-2">
          {workflowJobs.length === 0 ? (
            <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{zh ? "暂无异步任务。" : "No async jobs yet."}</div>
          ) : workflowJobs.map((job) => (
            <div key={job.job_id} className="rounded p-2" style={{ background: "var(--mis-surface)", border: "1px solid rgba(148,163,184,0.12)" }}>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate text-[11px] font-medium" style={{ color: "var(--mis-text)" }}>{job.title || job.template_id || job.job_id}</span>
                <span
                  className="rounded px-1.5 py-0.5 text-[9px]"
                  style={{
                    background: job.status === "completed" ? "rgba(42,157,143,0.12)" : job.status === "failed" ? "rgba(248,113,113,0.12)" : "rgba(251,191,36,0.12)",
                    color: job.status === "completed" ? "var(--mis-success)" : job.status === "failed" ? "#FCA5A5" : "#FBBF24",
                  }}
                >
                  {job.status}
                </span>
              </div>
              <div className="mt-1 text-[10px]" style={{ color: "var(--mis-muted)" }}>{workflowLabel(job, zh)} · {job.job_id} · {job.adapter || "default"} · {job.template_id || "custom"}</div>
              {job.input_summary && <p className="mt-1 line-clamp-2 text-[10px] leading-relaxed" style={{ color: "var(--mis-dim)" }}>{job.input_summary}</p>}
              {evidenceLine(job.result?.evidence) && (
                <div className="mt-1 text-[10px]" style={{ color: "var(--mis-dim)" }}>{evidenceLine(job.result?.evidence)}</div>
              )}
              <div className="mt-2 flex flex-wrap gap-2 text-[10px]">
                {job.result_task_id && <Link style={{ color: "var(--mis-cyan)" }} to={`/admin/tasks/${job.result_task_id}`}>{zh ? "任务" : "Task"}</Link>}
                {job.result_run_id && <Link style={{ color: "var(--mis-purple)" }} to={`/admin/runs/${job.result_run_id}`}>{zh ? "运行" : "Run"}</Link>}
                {job.result_artifact_id && <span style={{ color: "var(--mis-success)" }}>{job.result_artifact_id}</span>}
                {job.result?.approval_ids?.length ? <Link style={{ color: "#FBBF24" }} to="/workspace/approvals">{zh ? "审批" : "Approval"}</Link> : null}
                {job.result?.project_id && <Link style={{ color: "var(--mis-success)" }} to={`/workspace/customer-projects/${job.result.project_id}/report`}>{zh ? "报告" : "Report"}</Link>}
                {job.error_message && <span style={{ color: "#FCA5A5" }}>{job.error_message}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>

      {(result || error) && (
        <div className="mt-4 rounded p-3 text-[11px]" style={{ background: result?.dry_run ? "rgba(251,191,36,0.10)" : "rgba(42,157,143,0.10)", color: "var(--mis-text)", border: "1px solid rgba(148,163,184,0.18)" }}>
          {error ? (
            <div style={{ color: "#FCA5A5" }}>{error}</div>
          ) : result && (
            <div className="space-y-1">
              <div>
                <span style={{ color: "var(--mis-muted)" }}>{zh ? "结果：" : "Result: "}</span>
                {result.ok ? resultLedgerState : (zh ? "运行失败" : "Run failed")}
              </div>
              <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "任务：" : "Task: "}</span>{result.task_id}</div>
              {result.run_id && <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "运行：" : "Run: "}</span>{result.run_id}</div>}
              {result.artifact_id && <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "交付物：" : "Artifact: "}</span>{result.artifact_id}</div>}
              {result.evidence && (
                <div>
                  <span style={{ color: "var(--mis-muted)" }}>{zh ? "证据：" : "Evidence: "}</span>
                  {evidenceLine(result.evidence)}
                </div>
              )}
              {(result.evidence?.approvals || 0) > 0 && (
                <Link className="inline-flex pt-1" style={{ color: "#FBBF24" }} to="/workspace/approvals">{zh ? "处理交付审批" : "Review delivery approval"}</Link>
              )}
              {result.reason && <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "原因：" : "Reason: "}</span>{result.reason}</div>}
              {result.output_summary && <p className="pt-1 leading-relaxed" style={{ color: "var(--mis-dim)" }}>{result.output_summary}</p>}
            </div>
          )}
        </div>
      )}

      {kbResult && (
        <div className="mt-4 rounded p-3 text-[11px]" style={{ background: kbResult.ok ? "rgba(42,157,143,0.10)" : "rgba(248,113,113,0.10)", color: "var(--mis-text)", border: "1px solid rgba(148,163,184,0.18)" }}>
          {kbResult.ok ? (
            <div className="space-y-1">
              <div>
                <span style={{ color: "var(--mis-muted)" }}>{zh ? "知识库项目：" : "KB project: "}</span>
                {kbResult.project_id}
              </div>
              <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "任务数：" : "Tasks: "}</span>{kbResult.results?.length || 0}</div>
              {kbResult.approval_ids && kbResult.approval_ids.length > 0 && (
                <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "待审批：" : "Pending approval: "}</span>{kbResult.approval_ids[0]}</div>
              )}
              {kbResult.artifact_id && (
                <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "交付物：" : "Artifact: "}</span>{kbResult.artifact_id}</div>
              )}
              {kbResult.project_id && (
                <div className="flex flex-wrap gap-2 pt-1">
                  <Link
                    to={`/workspace/customer-projects/${kbResult.project_id}/report`}
                    className="inline-flex rounded px-2.5 py-1.5 text-[10px]"
                    style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
                  >
                    {zh ? "打开交付报告" : "Open delivery report"}
                  </Link>
                  <button
                    type="button"
                    onClick={persistReportArtifact}
                    disabled={reportBusy}
                    className="inline-flex items-center gap-1.5 rounded px-2.5 py-1.5 text-[10px] disabled:opacity-60"
                    style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.25)" }}
                  >
                    {reportBusy ? <Loader2 size={12} className="animate-spin" /> : <Archive size={12} />}
                    {zh ? "归档报告到账本" : "Archive report to ledger"}
                  </button>
                </div>
              )}
              {reportArtifact?.artifact?.artifact_id && (
                <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "报告归档：" : "Report artifact: "}</span>{reportArtifact.artifact.artifact_id}</div>
              )}
              <p className="pt-1 leading-relaxed" style={{ color: "var(--mis-dim)" }}>
                {zh
                  ? `已按模板创建客户项目闭环：${selectedTemplate?.name || "模板"}。任务、运行、工具调用、外部上传审批、评估、记忆候选、审计和交付摘要已进入 MIS。未上传原始资料或保存凭证。`
                  : `Created a template-backed customer project loop: ${selectedTemplate?.name_en || selectedTemplate?.name || "template"}. Tasks, runs, tool calls, external-upload approval, evaluations, memory candidates, audit and delivery summary entered MIS. No raw documents or credentials were uploaded.`}
              </p>
            </div>
          ) : (
            <div style={{ color: "#FCA5A5" }}>{kbResult.error || (zh ? "知识库项目生成失败" : "KB project generation failed")}</div>
          )}
        </div>
      )}
    </section>
  );
}
