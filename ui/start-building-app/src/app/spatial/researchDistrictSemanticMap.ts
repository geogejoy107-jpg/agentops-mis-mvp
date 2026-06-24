import type { PixelMetrics, PixelZoneId } from "../components/pixel/pixelModel";

export type SpatialSemanticLevel = 0 | 1 | 2 | 3;
export type SpatialInteraction = "navigate" | "inspect" | "operate";
export type SpatialAuthorityKind =
  | "agent"
  | "task"
  | "plan"
  | "run"
  | "tool_call"
  | "approval"
  | "artifact"
  | "memory"
  | "evaluation"
  | "runtime"
  | "audit"
  | "delivery"
  | "template"
  | "control";

export type SpatialVisualType =
  | "district"
  | "hall"
  | "board"
  | "forge"
  | "workshop"
  | "gate"
  | "archive"
  | "orchard"
  | "greenhouse"
  | "dock"
  | "bell"
  | "post"
  | "table"
  | "terminal"
  | "shelf"
  | "desk"
  | "bench"
  | "cabinet"
  | "lamp"
  | "tray"
  | "gauge"
  | "clock"
  | "folio"
  | "drawer"
  | "envelope"
  | "nameplate";

export interface SpatialLocalizedText {
  en: string;
  zh: string;
}

export interface SpatialBounds {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ResearchDistrictSemanticObject {
  id: string;
  level: SpatialSemanticLevel;
  visual: SpatialVisualType;
  label: SpatialLocalizedText;
  description: SpatialLocalizedText;
  authorityKind: SpatialAuthorityKind;
  formalRoute: string;
  metricKey: keyof PixelMetrics;
  metricLabel: SpatialLocalizedText;
  interaction: SpatialInteraction;
  bounds: SpatialBounds;
  walkAnchor: { x: number; y: number };
  targetZone?: PixelZoneId;
}

const t = (en: string, zh: string): SpatialLocalizedText => ({ en, zh });

const semanticObject = (
  id: string,
  level: SpatialSemanticLevel,
  visual: SpatialVisualType,
  label: SpatialLocalizedText,
  description: SpatialLocalizedText,
  authorityKind: SpatialAuthorityKind,
  formalRoute: string,
  metricKey: keyof PixelMetrics,
  metricLabel: SpatialLocalizedText,
  interaction: SpatialInteraction,
  bounds: SpatialBounds,
  targetZone?: PixelZoneId,
): ResearchDistrictSemanticObject => ({
  id,
  level,
  visual,
  label,
  description,
  authorityKind,
  formalRoute,
  metricKey,
  metricLabel,
  interaction,
  bounds,
  walkAnchor: { x: bounds.x + bounds.w / 2, y: bounds.y + bounds.h + 2 },
  targetZone,
});

export const RESEARCH_DISTRICT_SEMANTIC_OBJECTS: readonly ResearchDistrictSemanticObject[] = [
  // L0 — the world is a portfolio of governed operational districts.
  semanticObject(
    "world-research-district", 0, "district", t("Research District", "研究城区"),
    t("Agents investigate, compare and turn sources into reviewable evidence.", "Agent 在这里调研、比较，并把来源转化为可审核证据。"),
    "agent", "/workspace/agents", "totalAgents", t("registered Agents", "已注册 Agent"), "navigate",
    { x: 7, y: 13, w: 25, h: 27 }, "agent_lobby",
  ),
  semanticObject(
    "world-project-works", 0, "district", t("Project Works", "项目工场"),
    t("Tasks, plans and delivery checkpoints are coordinated here.", "任务、计划和交付检查点在这里协同。"),
    "task", "/workspace/tasks", "activeRuns", t("active work", "活动工作"), "navigate",
    { x: 38, y: 10, w: 25, h: 29 }, "task_hall",
  ),
  semanticObject(
    "world-memory-orchard", 0, "orchard", t("Memory Orchard", "记忆果园"),
    t("Only reviewed candidates become durable organizational memory.", "只有经过审核的候选内容才会成为持久组织记忆。"),
    "memory", "/workspace/memory", "memoryCandidates", t("review candidates", "待审候选"), "navigate",
    { x: 69, y: 13, w: 23, h: 25 }, "memory_archive",
  ),
  semanticObject(
    "world-mission-control", 0, "hall", t("Mission Control", "任务控制中心"),
    t("Read-only operational overview for health, risk and next actions.", "用于查看健康度、风险和下一动作的只读运营总览。"),
    "control", "/admin", "activeRuns", t("active runs", "活动运行"), "inspect",
    { x: 22, y: 57, w: 25, h: 25 }, "control_tower",
  ),
  semanticObject(
    "world-audit-observatory", 0, "bell", t("Audit Observatory", "审计观测站"),
    t("The evidence chain is inspected without turning the map into a second ledger.", "在不把地图变成第二套账本的前提下检查证据链。"),
    "audit", "/admin/audit", "auditEvents", t("audit events", "审计事件"), "inspect",
    { x: 56, y: 55, w: 25, h: 27 }, "audit_vault",
  ),

  // L1 — Research District facilities. Every operational landmark projects a formal MIS object.
  semanticObject(
    "district-agent-hall", 1, "hall", t("Agent Hall", "Agent 大厅"),
    t("Identity, role, runtime and ownership projection from the Agent registry.", "从 Agent 注册表投影身份、角色、运行时与负责人。"),
    "agent", "/workspace/agents", "totalAgents", t("Agents", "Agent"), "navigate",
    { x: 6, y: 9, w: 18, h: 20 }, "agent_lobby",
  ),
  semanticObject(
    "district-task-board", 1, "board", t("Task Noticeboard", "任务公告板"),
    t("Queue, priority, owner, risk and acceptance pointers from the Task ledger.", "投影任务账本中的队列、优先级、负责人、风险和验收入口。"),
    "task", "/workspace/tasks", "blockedTasks", t("blocked tasks", "阻塞任务"), "navigate",
    { x: 29, y: 11, w: 12, h: 15 }, "task_hall",
  ),
  semanticObject(
    "district-run-forge", 1, "forge", t("Run Forge", "运行工坊"),
    t("Active and historical execution records from the Run ledger.", "投影运行账本中的活动执行和历史执行记录。"),
    "run", "/admin/runs", "totalRuns", t("runs", "运行"), "navigate",
    { x: 47, y: 7, w: 19, h: 22 }, "run_stream",
  ),
  semanticObject(
    "district-tool-workshop", 1, "workshop", t("Tool Workshop", "工具工坊"),
    t("Tool-call evidence and prepared-action entry points; not an execution authority.", "工具调用证据与 Prepared Action 入口；场景本身不拥有执行权。"),
    "tool_call", "/admin/toolcalls", "activeRuns", t("active tool work", "活动工具工作"), "navigate",
    { x: 73, y: 10, w: 18, h: 19 }, "tool_workshop",
  ),
  semanticObject(
    "district-approval-gate", 1, "gate", t("Approval Gate", "审批闸口"),
    t("Pending review and exact-resume checkpoints for approval-gated prepared actions.", "投影待审核事项和需要精确恢复的 Prepared Action 检查点。"),
    "approval", "/workspace/approvals", "pendingApprovals", t("pending approvals", "待审批"), "operate",
    { x: 9, y: 43, w: 16, h: 17 }, "approval_gate",
  ),
  semanticObject(
    "district-evidence-archive", 1, "archive", t("Evidence Archive", "证据档案馆"),
    t("Artifacts, hashes and delivery evidence remain linked to formal runs.", "Artifact、哈希与交付证据继续绑定正式运行记录。"),
    "artifact", "/workspace/reports", "auditEvents", t("evidence records", "证据记录"), "inspect",
    { x: 31, y: 39, w: 18, h: 23 }, "external_base_dock",
  ),
  semanticObject(
    "district-memory-orchard", 1, "orchard", t("Memory Orchard", "记忆果园"),
    t("Candidate memories wait for review before promotion.", "候选记忆在晋升前等待人工审核。"),
    "memory", "/workspace/memory", "memoryCandidates", t("memory candidates", "记忆候选"), "navigate",
    { x: 55, y: 42, w: 17, h: 19 }, "memory_archive",
  ),
  semanticObject(
    "district-evaluation-greenhouse", 1, "greenhouse", t("Evaluation Greenhouse", "评估温室"),
    t("Quality gates, scores and remediation loops are cultivated here.", "质量门、评分和修复闭环在这里被持续培育。"),
    "evaluation", "/admin/evaluations", "failedQualityGates", t("failed gates", "失败质量门"), "navigate",
    { x: 77, y: 41, w: 16, h: 20 }, "evaluation_room",
  ),
  semanticObject(
    "district-runtime-dock", 1, "dock", t("Runtime Dock", "运行时码头"),
    t("Connector readiness and runtime capability manifests.", "投影连接器就绪情况与运行时能力清单。"),
    "runtime", "/admin/connectors", "runtimeHealth", t("runtime health", "运行时健康"), "navigate",
    { x: 8, y: 72, w: 19, h: 16 }, "runtime_lab",
  ),
  semanticObject(
    "district-audit-bell", 1, "bell", t("Audit Bell", "审计钟楼"),
    t("Visible evidence pulse for append-only audit events.", "为追加式审计事件提供可见证据脉冲。"),
    "audit", "/admin/audit", "auditEvents", t("audit events", "审计事件"), "inspect",
    { x: 41, y: 71, w: 15, h: 18 }, "audit_vault",
  ),
  semanticObject(
    "district-delivery-post", 1, "post", t("Delivery Post", "交付站"),
    t("Reports and customer-facing evidence leave only after formal review.", "报告和客户交付证据仅在正式审核后离开。"),
    "delivery", "/workspace/reports", "failedQualityGates", t("delivery gaps", "交付缺口"), "navigate",
    { x: 68, y: 72, w: 22, h: 16 }, "template_market",
  ),

  // L2 — the AI Papers House interior.
  semanticObject(
    "facility-paper-intake", 2, "desk", t("Paper Intake", "论文接收台"),
    t("Incoming task references and source provenance are registered for review.", "登记待审核的任务引用和来源证据。"),
    "task", "/workspace/tasks", "blockedTasks", t("intake exceptions", "接收异常"), "inspect",
    { x: 6, y: 12, w: 15, h: 18 }, "task_hall",
  ),
  semanticObject(
    "facility-plan-table", 2, "table", t("Plan Table", "计划桌"),
    t("Verified Agent Plan and task binding; the room cannot approve the plan itself.", "投影已验证 Agent Plan 与任务绑定；房间本身不能批准计划。"),
    "plan", "/workspace/tasks", "activeRuns", t("bound plans", "已绑定计划"), "inspect",
    { x: 27, y: 10, w: 18, h: 19 }, "task_hall",
  ),
  semanticObject(
    "facility-search-terminal", 2, "terminal", t("Search Terminal", "检索终端"),
    t("Knowledge retrieval evidence and source hashes, without raw private prompts.", "投影知识检索证据和来源哈希，不展示原始私密 Prompt。"),
    "tool_call", "/admin/toolcalls", "activeRuns", t("retrieval work", "检索工作"), "operate",
    { x: 52, y: 11, w: 14, h: 18 }, "tool_workshop",
  ),
  semanticObject(
    "facility-run-console", 2, "terminal", t("Run Console", "运行控制台"),
    t("Run status, plan binding and execution evidence readback.", "读取运行状态、计划绑定与执行证据。"),
    "run", "/admin/runs", "activeRuns", t("active runs", "活动运行"), "navigate",
    { x: 74, y: 9, w: 17, h: 21 }, "run_stream",
  ),
  semanticObject(
    "facility-tool-bench", 2, "bench", t("Tool Bench", "工具工作台"),
    t("Tool-call records, action hashes and provider result reconciliation.", "投影工具调用记录、动作哈希和 Provider 结果对账。"),
    "tool_call", "/admin/toolcalls", "totalRuns", t("run-linked tools", "运行关联工具"), "inspect",
    { x: 7, y: 43, w: 17, h: 18 }, "tool_workshop",
  ),
  semanticObject(
    "facility-approval-desk", 2, "desk", t("Approval Desk", "审批桌"),
    t("Human decision surface for pending approvals and consume-once resume evidence.", "用于待审批事项和一次性恢复证据的人类决策界面。"),
    "approval", "/workspace/approvals", "pendingApprovals", t("pending approvals", "待审批"), "operate",
    { x: 30, y: 42, w: 15, h: 19 }, "approval_gate",
  ),
  semanticObject(
    "facility-evidence-shelves", 2, "shelf", t("Evidence Shelves", "证据书架"),
    t("Artifacts and compact evidence packets indexed by formal IDs.", "按正式 ID 索引 Artifact 和紧凑证据包。"),
    "artifact", "/workspace/reports", "auditEvents", t("indexed evidence", "已索引证据"), "inspect",
    { x: 51, y: 40, w: 16, h: 22 }, "external_base_dock",
  ),
  semanticObject(
    "facility-memory-cabinet", 2, "cabinet", t("Memory Cabinet", "记忆柜"),
    t("Reviewed memory and candidates remain visibly distinct.", "已审核记忆与候选记忆保持清晰区分。"),
    "memory", "/workspace/memory", "memoryCandidates", t("candidates", "候选"), "navigate",
    { x: 74, y: 42, w: 16, h: 20 }, "memory_archive",
  ),
  semanticObject(
    "facility-evaluation-bench", 2, "bench", t("Evaluation Bench", "评估台"),
    t("Evaluator results, gate failures and remediation pointers.", "投影评估结果、质量门失败和修复入口。"),
    "evaluation", "/admin/evaluations", "failedQualityGates", t("failed gates", "失败质量门"), "navigate",
    { x: 9, y: 73, w: 17, h: 14 }, "evaluation_room",
  ),
  semanticObject(
    "facility-runtime-console", 2, "terminal", t("Runtime Console", "运行时控制台"),
    t("Capability, trust and readiness readback for connected runtimes.", "读取已连接运行时的能力、信任和就绪状态。"),
    "runtime", "/admin/connectors", "runtimeHealth", t("runtime health", "运行时健康"), "navigate",
    { x: 39, y: 72, w: 18, h: 15 }, "runtime_lab",
  ),
  semanticObject(
    "facility-audit-register", 2, "folio", t("Audit Register", "审计登记册"),
    t("Actor, action, entity and evidence references from the audit ledger.", "投影审计账本中的操作者、动作、实体和证据引用。"),
    "audit", "/admin/audit", "auditEvents", t("audit events", "审计事件"), "inspect",
    { x: 69, y: 72, w: 20, h: 15 }, "audit_vault",
  ),

  // L3 — one Agent evidence desk. Small props still have explicit authority meaning.
  semanticObject(
    "workspace-agent-nameplate", 3, "nameplate", t("Agent Nameplate", "Agent 名牌"),
    t("Stable Agent ID, role and runtime reference.", "稳定的 Agent ID、角色和运行时引用。"),
    "agent", "/workspace/agents", "totalAgents", t("Agents", "Agent"), "inspect",
    { x: 6, y: 9, w: 17, h: 10 }, "agent_lobby",
  ),
  semanticObject(
    "workspace-task-folio", 3, "folio", t("Task Folio", "任务册"),
    t("Current task ID, scope, risk and acceptance pointer.", "当前任务 ID、范围、风险和验收入口。"),
    "task", "/workspace/tasks", "blockedTasks", t("blocked tasks", "阻塞任务"), "inspect",
    { x: 28, y: 8, w: 14, h: 12 }, "task_hall",
  ),
  semanticObject(
    "workspace-plan-folio", 3, "folio", t("Plan Folio", "计划册"),
    t("Verified plan hash and immutable task binding.", "已验证计划哈希与不可变任务绑定。"),
    "plan", "/workspace/tasks", "activeRuns", t("active work", "活动工作"), "inspect",
    { x: 47, y: 8, w: 14, h: 12 }, "task_hall",
  ),
  semanticObject(
    "workspace-knowledge-drawer", 3, "drawer", t("Knowledge Drawer", "知识抽屉"),
    t("Retrieved paths, source hashes and quality metrics.", "检索路径、来源哈希和质量指标。"),
    "tool_call", "/admin/toolcalls", "activeRuns", t("retrieval work", "检索工作"), "inspect",
    { x: 67, y: 8, w: 17, h: 12 }, "tool_workshop",
  ),
  semanticObject(
    "workspace-context-slate", 3, "board", t("Context Hash Slate", "上下文哈希板"),
    t("Compact hashes and retrieval IDs only; raw private prompts are outside the default store.", "仅显示紧凑哈希和检索 ID；默认不存储原始私密 Prompt。"),
    "audit", "/admin/audit", "auditEvents", t("evidence links", "证据链接"), "inspect",
    { x: 86, y: 9, w: 9, h: 18 }, "audit_vault",
  ),
  semanticObject(
    "workspace-run-terminal", 3, "terminal", t("Run Terminal", "运行终端"),
    t("Current Run, status and plan-evidence binding.", "当前 Run、状态和计划证据绑定。"),
    "run", "/admin/runs", "activeRuns", t("active runs", "活动运行"), "operate",
    { x: 7, y: 34, w: 18, h: 18 }, "run_stream",
  ),
  semanticObject(
    "workspace-tool-tray", 3, "tray", t("Tool Tray", "工具托盘"),
    t("Tool-call IDs and prepared-action checkpoints.", "工具调用 ID 与 Prepared Action 检查点。"),
    "tool_call", "/admin/toolcalls", "totalRuns", t("run-linked calls", "运行关联调用"), "inspect",
    { x: 30, y: 35, w: 13, h: 15 }, "tool_workshop",
  ),
  semanticObject(
    "workspace-approval-lamp", 3, "lamp", t("Approval Lamp", "审批灯"),
    t("Amber means human review is required; it never grants approval automatically.", "琥珀色表示需要人工审核；灯本身绝不会自动批准。"),
    "approval", "/workspace/approvals", "pendingApprovals", t("pending approvals", "待审批"), "operate",
    { x: 48, y: 34, w: 10, h: 16 }, "approval_gate",
  ),
  semanticObject(
    "workspace-evidence-tray", 3, "tray", t("Evidence Tray", "证据托盘"),
    t("Artifacts, hashes and delivery-ready references.", "Artifact、哈希和可交付引用。"),
    "artifact", "/workspace/reports", "auditEvents", t("evidence records", "证据记录"), "inspect",
    { x: 63, y: 34, w: 14, h: 16 }, "external_base_dock",
  ),
  semanticObject(
    "workspace-evaluation-gauge", 3, "gauge", t("Evaluation Gauge", "评估仪表"),
    t("Quality-gate outcome and remediation status.", "质量门结果与修复状态。"),
    "evaluation", "/admin/evaluations", "failedQualityGates", t("failed gates", "失败质量门"), "inspect",
    { x: 82, y: 34, w: 13, h: 16 }, "evaluation_room",
  ),
  semanticObject(
    "workspace-memory-box", 3, "cabinet", t("Memory Candidate Box", "记忆候选箱"),
    t("A candidate remains non-authoritative until reviewed.", "候选内容在审核前始终不具备权威性。"),
    "memory", "/workspace/memory", "memoryCandidates", t("candidates", "候选"), "navigate",
    { x: 9, y: 67, w: 16, h: 16 }, "memory_archive",
  ),
  semanticObject(
    "workspace-audit-clock", 3, "clock", t("Audit Clock", "审计时钟"),
    t("Visible timing cue for append-only audit evidence.", "追加式审计证据的可见时间提示。"),
    "audit", "/admin/audit", "auditEvents", t("audit events", "审计事件"), "inspect",
    { x: 39, y: 67, w: 13, h: 15 }, "audit_vault",
  ),
  semanticObject(
    "workspace-delivery-envelope", 3, "envelope", t("Delivery Envelope", "交付信封"),
    t("Customer-facing output remains gated by evaluation and review evidence.", "面向客户的输出继续受评估与审核证据约束。"),
    "delivery", "/workspace/reports", "failedQualityGates", t("delivery gaps", "交付缺口"), "navigate",
    { x: 69, y: 67, w: 20, h: 15 }, "template_market",
  ),
] as const;

export const RESEARCH_DISTRICT_OBJECT_BY_ID = new Map(
  RESEARCH_DISTRICT_SEMANTIC_OBJECTS.map((object) => [object.id, object] as const),
);

export const RESEARCH_DISTRICT_OBJECTS_BY_LEVEL: Readonly<Record<SpatialSemanticLevel, readonly ResearchDistrictSemanticObject[]>> = {
  0: RESEARCH_DISTRICT_SEMANTIC_OBJECTS.filter((object) => object.level === 0),
  1: RESEARCH_DISTRICT_SEMANTIC_OBJECTS.filter((object) => object.level === 1),
  2: RESEARCH_DISTRICT_SEMANTIC_OBJECTS.filter((object) => object.level === 2),
  3: RESEARCH_DISTRICT_SEMANTIC_OBJECTS.filter((object) => object.level === 3),
};

export const RESEARCH_DISTRICT_LEVEL_COPY: Readonly<Record<SpatialSemanticLevel, {
  label: SpatialLocalizedText;
  subtitle: SpatialLocalizedText;
  queryScope: string;
  interactionDepth: string;
}>> = {
  0: {
    label: t("World Atlas", "世界总览"),
    subtitle: t("Portfolio-level districts and authority boundaries", "项目组合级城区与权威边界"),
    queryScope: "workspace portfolio",
    interactionDepth: "orient",
  },
  1: {
    label: t("Research District", "研究城区"),
    subtitle: t("Operational facilities and live MIS signals", "运营设施与实时 MIS 信号"),
    queryScope: "research district",
    interactionDepth: "navigate",
  },
  2: {
    label: t("AI Papers House", "AI 论文研究馆"),
    subtitle: t("Facility workflow and evidence stations", "设施级工作流与证据站点"),
    queryScope: "research facility",
    interactionDepth: "inspect",
  },
  3: {
    label: t("Agent Evidence Desk", "Agent 证据工作台"),
    subtitle: t("One Agent, one task, one governed evidence chain", "一个 Agent、一个任务、一条受治理证据链"),
    queryScope: "single Agent workspace",
    interactionDepth: "operate",
  },
};

export const AGENT_TARGET_OBJECT_BY_ZONE: Readonly<Partial<Record<PixelZoneId, string>>> = {
  control_tower: "district-agent-hall",
  agent_lobby: "district-agent-hall",
  task_hall: "district-task-board",
  run_stream: "district-run-forge",
  runtime_lab: "district-runtime-dock",
  tool_workshop: "district-tool-workshop",
  approval_gate: "district-approval-gate",
  evaluation_room: "district-evaluation-greenhouse",
  memory_archive: "district-memory-orchard",
  audit_vault: "district-audit-bell",
  external_base_dock: "district-evidence-archive",
  incident_corner: "district-evaluation-greenhouse",
  template_market: "district-delivery-post",
};

export function localizedSpatialText(text: SpatialLocalizedText, locale: "en" | "zh"): string {
  return text[locale];
}

export function spatialMetricValue(object: ResearchDistrictSemanticObject, metrics: PixelMetrics): string {
  const value = metrics[object.metricKey];
  return typeof value === "number" ? String(value) : value;
}
