import { useParams, Link } from "react-router";
import { Archive, ArrowLeft, FileText, ShieldCheck, LockKeyhole } from "lucide-react";
import { loadCustomerProjectReport, persistCustomerProjectReportArtifact, useLiveData, type CustomerProjectReportPayload } from "../../data/liveApi";
import { usePreferences } from "../../context/PreferencesContext";
import { useState } from "react";

function renderMarkdownLine(line: string, index: number) {
  if (line.startsWith("# ")) {
    return <h1 key={index} className="text-xl font-semibold" style={{ color: "var(--mis-text)" }}>{line.slice(2)}</h1>;
  }
  if (line.startsWith("## ")) {
    return <h2 key={index} className="mt-5 text-sm font-semibold" style={{ color: "var(--mis-text)" }}>{line.slice(3)}</h2>;
  }
  if (line.startsWith("### ")) {
    return <h3 key={index} className="mt-4 text-xs font-semibold" style={{ color: "var(--mis-cyan)" }}>{line.slice(4)}</h3>;
  }
  if (line.startsWith("- ")) {
    return <div key={index} className="pl-4 leading-relaxed" style={{ color: "var(--mis-dim)" }}>- {line.slice(2).replaceAll("`", "")}</div>;
  }
  if (!line.trim()) {
    return <div key={index} className="h-2" />;
  }
  return <p key={index} className="leading-relaxed" style={{ color: "var(--mis-dim)" }}>{line.replaceAll("`", "")}</p>;
}

function metricValue(report: CustomerProjectReportPayload | null, key: keyof CustomerProjectReportPayload["counts"]) {
  return report?.counts?.[key] ?? 0;
}

export function CustomerProjectReport() {
  const { projectId = "" } = useParams();
  const { locale } = usePreferences();
  const zh = locale === "zh";
  const data = useLiveData(() => loadCustomerProjectReport(projectId), [projectId]);
  const [archiveBusy, setArchiveBusy] = useState(false);
  const [archiveError, setArchiveError] = useState<string | null>(null);

  const archiveReport = async () => {
    if (!projectId) return;
    setArchiveBusy(true);
    setArchiveError(null);
    try {
      await persistCustomerProjectReportArtifact(projectId);
      await data.refresh();
    } catch (err) {
      setArchiveError(err instanceof Error ? err.message : String(err));
    } finally {
      setArchiveBusy(false);
    }
  };

  const report = data.data;
  const markdownLines = (report?.markdown || "").split("\n");
  const internalEvidence = report?.internal_evidence || {};
  const evidenceCounts = internalEvidence.counts || {};

  if (data.loading) {
    return <div className="p-6 text-sm" style={{ color: "var(--mis-dim)" }}>{zh ? "正在加载交付报告..." : "Loading delivery report..."}</div>;
  }
  if (data.error || !report || report.error) {
    return (
      <div className="p-6">
        <Link to="/workspace/pixel-office" className="inline-flex items-center gap-2 text-xs" style={{ color: "var(--mis-cyan)" }}>
          <ArrowLeft size={14} /> {zh ? "返回 Pixel Office" : "Back to Pixel Office"}
        </Link>
        <div className="mt-4 rounded-lg p-4 text-sm" style={{ background: "rgba(248,113,113,0.10)", color: "#FCA5A5", border: "1px solid rgba(248,113,113,0.22)" }}>
          {data.error || report?.error || (zh ? "报告不存在" : "Report not found")}
        </div>
      </div>
    );
  }

  const metrics = [
    [zh ? "任务" : "Tasks", metricValue(report, "tasks")],
    [zh ? "运行" : "Runs", metricValue(report, "runs")],
    [zh ? "完成运行" : "Completed runs", metricValue(report, "completed_runs")],
    [zh ? "待审批" : "Pending approvals", metricValue(report, "pending_approvals")],
    [zh ? "评估" : "Evaluations", metricValue(report, "evaluations")],
    [zh ? "交付物" : "Artifacts", metricValue(report, "artifacts")],
  ];

  return (
    <div className="p-5 md:p-6 max-w-6xl">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to="/workspace/pixel-office" className="inline-flex items-center gap-2 text-xs" style={{ color: "var(--mis-cyan)" }}>
            <ArrowLeft size={14} /> {zh ? "返回 Pixel Office" : "Back to Pixel Office"}
          </Link>
          <div className="mt-3 inline-flex items-center gap-1.5 rounded px-2 py-1 text-[10px] uppercase tracking-wide" style={{ background: "rgba(34,211,238,0.10)", color: "var(--mis-cyan)", border: "1px solid rgba(34,211,238,0.22)" }}>
            <FileText size={12} />
            {zh ? "客户项目交付报告" : "Customer project delivery report"}
          </div>
          <h1 className="mt-2 text-xl font-semibold" style={{ color: "var(--mis-text)" }}>
            {zh ? "AI 知识库 / 问答机器人交付报告" : "AI Knowledge Base / Q&A Bot Delivery Report"}
          </h1>
          <p className="mt-1 text-xs" style={{ color: "var(--mis-dim)" }}>
            {zh ? "项目 ID：" : "Project ID: "}<span style={{ color: "var(--mis-text)" }}>{report.project_id}</span>
          </p>
        </div>
        <button
          type="button"
          onClick={archiveReport}
          disabled={archiveBusy}
          className="inline-flex items-center gap-2 rounded px-3 py-2 text-xs disabled:opacity-60"
          style={{ background: "rgba(42,157,143,0.12)", color: "var(--mis-success)", border: "1px solid rgba(42,157,143,0.25)" }}
        >
          <Archive size={14} />
          {archiveBusy ? (zh ? "归档中..." : "Archiving...") : report.report_artifact_id ? (zh ? "刷新报告归档" : "Refresh report artifact") : (zh ? "归档报告到账本" : "Archive report to ledger")}
        </button>
      </div>

      <div className="mt-5 grid grid-cols-2 lg:grid-cols-6 gap-2">
        {metrics.map(([label, value]) => (
          <div key={label} className="rounded-lg p-3" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
            <div className="text-[10px] uppercase tracking-wide" style={{ color: "var(--mis-muted)" }}>{label}</div>
            <div className="mt-1 text-lg font-semibold" style={{ color: "var(--mis-text)" }}>{value}</div>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-1 lg:grid-cols-3 gap-3">
        <div className="rounded-lg p-4" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
            <ShieldCheck size={14} />
            {zh ? "安全边界" : "Safety boundary"}
          </div>
          <div className="mt-3 space-y-1 text-[11px]" style={{ color: "var(--mis-dim)" }}>
            <div>{zh ? "外部上传：" : "External upload: "}{report.safe_defaults?.external_upload_performed === false ? "false" : "unknown"}</div>
            <div>{zh ? "保存凭证：" : "Credentials stored: "}{report.safe_defaults?.credentials_stored === false ? "false" : "unknown"}</div>
            <div>{zh ? "保存原始资料：" : "Raw documents stored: "}{report.safe_defaults?.raw_documents_stored === false ? "false" : "unknown"}</div>
            <div>{zh ? "保存原始提示词：" : "Raw prompts stored: "}{report.safe_defaults?.raw_prompts_stored === false ? "false" : "unknown"}</div>
            <div>{zh ? "私聊 transcript：" : "Private transcripts: "}{report.safe_defaults?.private_transcripts_stored === false ? "false" : "unknown"}</div>
            <div>{zh ? "摘要/hash 模式：" : "Summary/hash mode: "}{report.safe_defaults?.summary_hash_only === true ? "true" : "unknown"}</div>
            <div>{zh ? "客户报告包含内部证据：" : "Internal evidence in customer report: "}{report.report_boundary?.customer_markdown_excludes_internal_evidence === true ? "false" : "unknown"}</div>
            <div>{zh ? "包含原始 prompt/响应：" : "Raw prompts/responses included: "}{report.report_boundary?.raw_prompts_omitted === true && report.report_boundary?.raw_model_responses_omitted === true ? "false" : "unknown"}</div>
          </div>
        </div>
        <div className="rounded-lg p-4 lg:col-span-2" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
          <div className="text-xs font-semibold" style={{ color: "var(--mis-text)" }}>{zh ? "客户交付摘要" : "Customer delivery summary"}</div>
          <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]">
            <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "状态：" : "Status: "}</span>{report.status}</div>
            <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "报告归档：" : "Report archive: "}</span>{report.report_artifact_id ? (zh ? "已归档" : "archived") : (zh ? "未归档" : "not archived")}</div>
            <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "客户正文排除内部证据：" : "Customer body excludes internal evidence: "}</span>{report.report_boundary?.customer_markdown_excludes_internal_evidence ? "true" : "unknown"}</div>
            <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "内部证据已分离：" : "Internal evidence separated: "}</span>{report.report_boundary?.internal_evidence_separated ? "true" : "unknown"}</div>
          </div>
          {archiveError && <div className="mt-3 text-[11px]" style={{ color: "#FCA5A5" }}>{archiveError}</div>}
        </div>
      </div>

      <article className="mt-4 rounded-lg p-4 text-xs" style={{ background: "var(--mis-surface)", border: "1px solid var(--mis-border)" }}>
        {markdownLines.map(renderMarkdownLine)}
      </article>

      <section
        data-testid="internal-evidence-index"
        className="mt-4 rounded-lg p-4"
        style={{ background: "rgba(122,90,248,0.08)", border: "1px solid rgba(122,90,248,0.22)" }}
      >
        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--mis-text)" }}>
              <LockKeyhole size={14} />
              {zh ? "内部证据索引，不属于客户报告正文" : "Internal evidence index, not part of the customer report body"}
            </div>
            <p className="mt-1 text-[11px] max-w-3xl" style={{ color: "var(--mis-muted)" }}>
              {zh
                ? "这里给操作员追溯 run、tool、approval、audit 和 artifact 证据；客户交付正文只展示摘要、安全边界和交付结果。"
                : "Operators use this to trace run, tool, approval, audit and artifact evidence; the customer body shows only summary, safety boundary and delivery result."}
            </p>
          </div>
          <div className="rounded px-2 py-1 text-[10px]" style={{ color: "var(--mis-purple)", background: "rgba(122,90,248,0.10)", border: "1px solid rgba(122,90,248,0.20)" }}>
            {internalEvidence.visibility || "internal_operator"}
          </div>
        </div>
        <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-2">
          {[
            [zh ? "工具调用" : "Tool calls", evidenceCounts.tool_calls ?? 0],
            [zh ? "审批" : "Approvals", evidenceCounts.approvals ?? 0],
            [zh ? "审计" : "Audit logs", evidenceCounts.audit_logs ?? 0],
            [zh ? "记忆候选" : "Memory candidates", evidenceCounts.memories ?? 0],
          ].map(([label, value]) => (
            <div key={String(label)} className="rounded px-3 py-2" style={{ background: "var(--mis-bg)", border: "1px solid var(--mis-border)" }}>
              <div className="text-[10px]" style={{ color: "var(--mis-muted)" }}>{label}</div>
              <div className="text-sm font-semibold mt-1" style={{ color: "var(--mis-text)" }}>{value}</div>
            </div>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2 text-[11px]" style={{ color: "var(--mis-dim)" }}>
          <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "交付物 ID：" : "Delivery artifact ID: "}</span>{internalEvidence.delivery_artifact_id || report.artifact_id || "none"}</div>
          <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "报告 artifact：" : "Report artifact: "}</span>{internalEvidence.report_artifact_id || report.report_artifact_id || (zh ? "未归档" : "not archived")}</div>
          <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "Run 数：" : "Run IDs: "}</span>{internalEvidence.run_ids?.length || 0}</div>
          <div><span style={{ color: "var(--mis-muted)" }}>{zh ? "审批数：" : "Approval IDs: "}</span>{internalEvidence.approval_ids?.length || report.approval_ids?.length || 0}</div>
        </div>
      </section>
    </div>
  );
}
