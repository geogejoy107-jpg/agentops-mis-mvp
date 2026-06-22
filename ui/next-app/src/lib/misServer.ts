import type {
  ApprovalSummary,
  CustomerDeliveryBoardPayload,
  CustomerProjectIndexPayload,
  CustomerProjectReportPayload,
  MemorySummary,
} from "./mis";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";

export type ServerLoadResult<T> = {
  data: T;
  error: string | null;
};

async function serverMisJson<T>(path: string): Promise<T> {
  const response = await fetch(`${TARGET_BASE.replace(/\/$/, "")}${path}`, {
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}: ${await response.text()}`);
  }
  return response.json() as Promise<T>;
}

export async function loadServerApprovals(): Promise<ServerLoadResult<ApprovalSummary[]>> {
  try {
    return { data: await serverMisJson<ApprovalSummary[]>("/approvals"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerMemories(): Promise<ServerLoadResult<MemorySummary[]>> {
  try {
    return { data: await serverMisJson<MemorySummary[]>("/memories"), error: null };
  } catch (err) {
    return { data: [], error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerProjects(limit = 25): Promise<ServerLoadResult<CustomerProjectIndexPayload>> {
  try {
    return { data: await serverMisJson<CustomerProjectIndexPayload>(`/workflows/customer-projects?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return { data: { projects: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerDeliveryBoard(limit = 12): Promise<ServerLoadResult<CustomerDeliveryBoardPayload>> {
  try {
    return { data: await serverMisJson<CustomerDeliveryBoardPayload>(`/workflows/customer-delivery-board?limit=${encodeURIComponent(String(limit))}`), error: null };
  } catch (err) {
    return { data: { deliveries: [] }, error: err instanceof Error ? err.message : String(err) };
  }
}

export async function loadServerCustomerProjectReport(projectId: string): Promise<ServerLoadResult<CustomerProjectReportPayload | null>> {
  try {
    return { data: await serverMisJson<CustomerProjectReportPayload>(`/workflows/customer-projects/${encodeURIComponent(projectId)}/report`), error: null };
  } catch (err) {
    return { data: null, error: err instanceof Error ? err.message : String(err) };
  }
}
