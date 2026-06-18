import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { Archive, CheckCircle2, Loader2, Play, ShieldCheck } from "lucide-react";
import type { Agent } from "../../data/mockData";
import {
  loadCustomerTaskTemplates,
  persistCustomerProjectReportArtifact,
  runCustomerTaskTemplateWorkflow,
  runCustomerTaskWorkflow,
  type CustomerTaskTemplate,
  type CustomerProjectReportArtifactResult,
  type CustomerTaskWorkflowResult,
  type KbBotProjectWorkflowResult,
} from "../../data/liveApi";
import type { PixelLocale } from "./pixelModel";

interface CustomerDispatchPanelProps {
  agents: Agent[];
  locale: PixelLocale;
  onRefresh: () => void;
}

const riskOptions = ["low", "medium", "high"] as const;

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
  const [kbBusy, setKbBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState(false);
  const [result, setResult] = useState<CustomerTaskWorkflowResult | null>(null);
  const [kbResult, setKbResult] = useState<KbBotProjectWorkflowResult | null>(null);
  const [reportArtifact, setReportArtifact] = useState<CustomerProjectReportArtifactResult | null>(null);
  const [templates, setTemplates] = useState<CustomerTaskTemplate[]>([]);
  const [selectedTemplateId, setSelectedTemplateId] = useState("tpl_customer_kb_qa_bot");
  const [error, setError] = useState<string | null>(null);

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

  const selectedTemplate = useMemo(
    () => templates.find((template) => template.template_id === selectedTemplateId),
    [templates, selectedTemplateId],
  );
  const kbFinalStep = useMemo(
    () => kbResult?.results?.[kbResult.results.length - 1],
    [kbResult],
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
          onClick={() => submit(true)}
          disabled={busy || !title.trim()}
          className="inline-flex items-center gap-1.5 rounded px-3 py-2 text-xs disabled:opacity-50"
          style={{ background: "rgba(34,211,238,0.14)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.30)" }}
        >
          {busy ? <Loader2 size={13} className="animate-spin" /> : <Play size={13} />}
          {zh ? "确认真实运行" : "Confirm real run"}
        </button>
        <span className="text-[10px]" style={{ color: "var(--mis-muted)" }}>
          {zh ? "真实运行仍需服务端显式开启 HERMES_ALLOW_REAL_RUN。" : "Real run still requires server-side HERMES_ALLOW_REAL_RUN."}
        </span>
      </div>

      {(result || error) && (
        <div className="mt-4 rounded p-3 text-[11px]" style={{ background: result?.dry_run ? "rgba(251,191,36,0.10)" : "rgba(42,157,143,0.10)", color: "var(--mis-text)", border: "1px solid rgba(148,163,184,0.18)" }}>
          {error ? (
            <div style={{ color: "#FCA5A5" }}>{error}</div>
          ) : result && (
            <div className="space-y-1">
              <div>
                <span style={{ color: "var(--mis-muted)" }}>{zh ? "结果：" : "Result: "}</span>
                {result.dry_run ? (zh ? "安全预演已记录" : "Dry-run recorded") : result.ok ? (zh ? "真实运行完成" : "Real run completed") : (zh ? "运行失败" : "Run failed")}
              </div>
              <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "任务：" : "Task: "}</span>{result.task_id}</div>
              {result.run_id && <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "运行：" : "Run: "}</span>{result.run_id}</div>}
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
                  <a
                    href={kbResult.report_url ? kbResult.report_url.replace("/api/", "/mis-api/") : `/mis-api/workflows/customer-projects/${kbResult.project_id}/report`}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex rounded px-2.5 py-1.5 text-[10px]"
                    style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}
                  >
                    {zh ? "打开交付报告" : "Open delivery report"}
                  </a>
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
