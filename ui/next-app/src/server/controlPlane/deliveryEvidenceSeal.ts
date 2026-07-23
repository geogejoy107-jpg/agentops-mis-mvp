import type { PoolClient } from "pg";

import { ControlPlaneHttpError } from "./http";

export async function assertCustomerDeliveryEvidenceMutable(
  client: PoolClient,
  workspaceId: string,
  taskId: string,
  runId: string,
) {
  const result = await client.query<{ approval_id: string }>(
    `SELECT approval.approval_id
    FROM approvals approval
    JOIN tasks task ON task.task_id=approval.task_id AND task.workspace_id=$1
    JOIN runs run ON run.run_id=approval.run_id
      AND run.task_id=task.task_id AND run.workspace_id=$1
    WHERE approval.task_id=$2 AND approval.run_id=$3
      AND approval.approval_kind='customer_delivery'
      AND approval.decision<>'pending'
    ORDER BY approval.decided_at DESC,approval.approval_id DESC
    LIMIT 1`,
    [workspaceId, taskId, runId],
  );
  if (result.rows[0]) {
    throw new ControlPlaneHttpError(
      409,
      "customer_delivery_evidence_sealed",
      "Decided customer-delivery evidence is immutable; create a new run for revised evidence.",
    );
  }
}
