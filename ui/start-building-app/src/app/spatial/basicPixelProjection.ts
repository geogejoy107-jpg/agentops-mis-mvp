import type { PixelAgent, PixelMetrics, PixelTaskCard } from "../components/pixel/pixelModel";
import type {
  SpatialEntity,
  SpatialEntityStatus,
  SpatialProjectionAdapter,
  SpatialWorldSnapshot,
} from "./contracts";
import { SPATIAL_OS_FOUNDATION } from "./catalog";
import { deriveSpatialAgentIdentity } from "./agentIdentity";

export interface BasicPixelProjectionInput {
  agents: PixelAgent[];
  taskCards: PixelTaskCard[];
  metrics: PixelMetrics;
  source?: SpatialWorldSnapshot["source"];
}

function statusFrom(value: string): SpatialEntityStatus {
  const status = value.toLowerCase();
  if (/failed|error|timeout/.test(status)) return "failed";
  if (/blocked/.test(status)) return "blocked";
  if (/waiting|pending|approval|review/.test(status)) return "waiting";
  if (/completed|done|success|passed/.test(status)) return "completed";
  if (/running|active|executing|syncing|auditing/.test(status)) return "active";
  if (/idle|ready|new|planned/.test(status)) return "idle";
  return "unknown";
}

function agentNode(agent: PixelAgent): string {
  const searchable = `${agent.role} ${agent.taskTitle || ""} ${agent.status}`.toLowerCase();
  if (/approval|waiting|review/.test(searchable)) return "facility.ai-papers-house";
  if (/research|paper|knowledge|memory|browser|read/.test(searchable)) return "workspace.claude-research-desk";
  return "workspace.shared-paper-table";
}

function projectAgent(agent: PixelAgent): SpatialEntity {
  return {
    id: `agent.${agent.id}`,
    kind: "agent",
    label: agent.name,
    status: statusFrom(agent.status),
    risk: agent.risk,
    nodeId: agentNode(agent),
    authorityRef: {
      authority: "agentops-mis",
      kind: "agent",
      id: agent.id,
      route: agent.routeToDetail || `/admin/agents/${encodeURIComponent(agent.id)}`,
      provenance: "Basic Pixel Agent projection",
    },
    visualIdentity: deriveSpatialAgentIdentity({
      id: agent.id,
      name: agent.name,
      role: agent.role,
      runtime: agent.runtime,
    }),
    activity: agent.taskTitle || agent.status,
    metadata: {
      role: agent.role,
      runtime: agent.runtime,
      approvalState: agent.approvalState || null,
      isDemo: Boolean(agent.isDemo),
    },
  };
}

function projectTask(task: PixelTaskCard): SpatialEntity {
  return {
    id: `task.${task.id}`,
    kind: "task",
    label: task.title,
    status: statusFrom(task.status),
    risk: task.risk,
    nodeId: task.group === "Running" ? "workspace.claude-research-desk" : "workspace.shared-paper-table",
    authorityRef: {
      authority: "agentops-mis",
      kind: "task",
      id: task.id,
      route: task.route,
      provenance: "Basic Pixel Task projection",
    },
    activity: task.group,
    metadata: {
      assignedAgent: task.assignedAgent,
      group: task.group,
    },
  };
}

export const basicPixelProjectionAdapter: SpatialProjectionAdapter<BasicPixelProjectionInput> = {
  id: "basic-pixel-projection-v0",
  project(input) {
    return {
      schemaVersion: "spatial-snapshot/v0",
      worldId: SPATIAL_OS_FOUNDATION.world.id,
      generatedAt: new Date().toISOString(),
      source: input.source || "mixed",
      entities: [
        ...input.agents.map(projectAgent),
        ...input.taskCards.map(projectTask),
      ],
      metrics: {
        activeAgents: input.agents.filter((agent) => statusFrom(agent.status) === "active").length,
        activeRuns: input.metrics.activeRuns,
        pendingApprovals: input.metrics.pendingApprovals,
        blockedTasks: input.metrics.blockedTasks,
        failedRuns: input.metrics.failedRuns,
        memoryCandidates: input.metrics.memoryCandidates,
        auditEvents: input.metrics.auditEvents,
      },
    };
  },
};
