import type { PixelMetrics, PixelZoneId } from "../components/pixel/pixelModel";
import { PIXEL_ZONES } from "../components/pixel/pixelModel";
import type { LocalizedText, SpatialAuthorityKind } from "./contracts";

export type ResearchDistrictInteraction = "navigate" | "inspect" | "operate";
export type ResearchDistrictAuthorityClass =
  | "workspace"
  | "agent-registry"
  | "task-ledger"
  | "run-ledger"
  | "tool-call-ledger"
  | "approval-wall"
  | "memory-review"
  | "evaluation-gate"
  | "audit-log"
  | "runtime-connector"
  | "external-base"
  | "template-package"
  | "incident-review";

export interface ResearchDistrictSemanticObject {
  id: string;
  zoneId: PixelZoneId;
  label: LocalizedText;
  description: LocalizedText;
  authorityClass: ResearchDistrictAuthorityClass;
  authorityKind: SpatialAuthorityKind;
  formalRoute: string;
  metricKey: keyof PixelMetrics;
  interaction: ResearchDistrictInteraction;
  routeAuthority: "agentops-mis";
  visualAuthority: "spatial-map-is-not-ledger";
}

const t = (en: string, zh: string): LocalizedText => ({ en, zh });

const semanticObject = (
  zoneId: PixelZoneId,
  authorityClass: ResearchDistrictAuthorityClass,
  authorityKind: SpatialAuthorityKind,
  metricKey: keyof PixelMetrics,
  interaction: ResearchDistrictInteraction,
  label: LocalizedText,
  description: LocalizedText,
): ResearchDistrictSemanticObject => {
  const zone = PIXEL_ZONES.find((item) => item.id === zoneId);
  if (!zone) throw new Error(`[ResearchDistrictSemanticContract] unknown zone ${zoneId}`);
  return {
    id: `research-district.${zoneId}`,
    zoneId,
    label,
    description,
    authorityClass,
    authorityKind,
    formalRoute: zone.route,
    metricKey,
    interaction,
    routeAuthority: "agentops-mis",
    visualAuthority: "spatial-map-is-not-ledger",
  };
};

export const RESEARCH_DISTRICT_SEMANTIC_OBJECTS: readonly ResearchDistrictSemanticObject[] = [
  semanticObject(
    "control_tower",
    "workspace",
    "workspace",
    "activeRuns",
    "inspect",
    t("Control Tower", "控制塔"),
    t("Read operational health, risk and active work from the formal MIS console.", "从正式 MIS 控制台读取健康、风险和活动工作。"),
  ),
  semanticObject(
    "agent_lobby",
    "agent-registry",
    "agent",
    "totalAgents",
    "navigate",
    t("Agent Lobby", "代理大厅"),
    t("Agent identity, role, scope and runtime status come from the Agent registry.", "Agent 身份、角色、权限和运行时状态来自 Agent 注册表。"),
  ),
  semanticObject(
    "task_hall",
    "task-ledger",
    "task",
    "blockedTasks",
    "operate",
    t("Task Hall", "派活大厅"),
    t("Task intake, priority, risk and acceptance pointers stay in the task ledger.", "任务接收、优先级、风险和验收入口仍在任务账本中。"),
  ),
  semanticObject(
    "run_stream",
    "run-ledger",
    "run",
    "totalRuns",
    "navigate",
    t("Run Stream", "运行流水"),
    t("Run history, delegation and execution evidence remain bound to the Run ledger.", "运行历史、委派链和执行证据继续绑定 Run 账本。"),
  ),
  semanticObject(
    "runtime_lab",
    "runtime-connector",
    "route",
    "runtimeHealth",
    "inspect",
    t("Runtime Lab", "运行时实验室"),
    t("Connector trust, capability and health are read through the formal runtime console.", "连接器信任、能力和健康状态通过正式运行时控制台读取。"),
  ),
  semanticObject(
    "tool_workshop",
    "tool-call-ledger",
    "route",
    "activeRuns",
    "inspect",
    t("Tool Workshop", "工具工坊"),
    t("Tool-call evidence and prepared-action hashes stay in the tool-call ledger.", "工具调用证据和 Prepared Action 哈希保留在工具调用账本。"),
  ),
  semanticObject(
    "approval_gate",
    "approval-wall",
    "approval",
    "pendingApprovals",
    "operate",
    t("Approval Gate", "审批闸口"),
    t("High-risk actions must pass the Approval Wall before exact resume.", "高风险动作必须经过审批墙后才能精确恢复。"),
  ),
  semanticObject(
    "evaluation_room",
    "evaluation-gate",
    "evaluation",
    "failedQualityGates",
    "inspect",
    t("Evaluation Room", "质量评估室"),
    t("Quality gates, scores and remediation loops are formal evaluation records.", "质量门、评分和修复闭环都是正式评估记录。"),
  ),
  semanticObject(
    "memory_archive",
    "memory-review",
    "memory",
    "memoryCandidates",
    "operate",
    t("Memory Archive", "记忆档案馆"),
    t("Candidate memories need review before promotion to durable project memory.", "候选记忆需要审核后才能晋升为持久项目记忆。"),
  ),
  semanticObject(
    "external_base_dock",
    "external-base",
    "route",
    "externalSyncState",
    "inspect",
    t("External Base Dock", "外部库码头"),
    t("External bases are connector projections; MIS remains the execution ledger.", "外部库是连接器投影；MIS 仍是执行账本。"),
  ),
  semanticObject(
    "audit_vault",
    "audit-log",
    "audit",
    "auditEvents",
    "inspect",
    t("Audit Vault", "审计保险库"),
    t("Append-only audit evidence is inspected here without creating a second ledger.", "在这里查看追加式审计证据，但不创建第二套账本。"),
  ),
  semanticObject(
    "incident_corner",
    "incident-review",
    "run",
    "failedRuns",
    "inspect",
    t("Incident Corner", "故障角"),
    t("Failures, blocked work and recovery pointers route back to formal runs.", "失败、阻塞工作和恢复线索都回到正式运行记录。"),
  ),
  semanticObject(
    "template_market",
    "template-package",
    "template",
    "externalSyncState",
    "navigate",
    t("Template Market", "模板市场"),
    t("Templates create initial AI workforce defaults but do not own runtime evidence.", "模板创建初始 AI 团队默认值，但不拥有运行证据。"),
  ),
];

export const RESEARCH_DISTRICT_SEMANTIC_BY_ZONE = new Map(
  RESEARCH_DISTRICT_SEMANTIC_OBJECTS.map((item) => [item.zoneId, item] as const),
);
