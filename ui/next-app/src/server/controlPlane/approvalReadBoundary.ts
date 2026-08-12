import type { PoolClient } from "pg";

import type { HumanSessionIdentity } from "./humanSession";
import { ControlPlaneHttpError } from "./http";

const APPROVAL_READ_ROLES = new Set([
  "operator",
  "approver",
  "reviewer",
  "workspace-admin",
  "owner",
]);
const COMMERCIAL_EDITIONS = new Set([
  "pro_workspace",
  "team_governance",
  "enterprise_byoc",
]);
const KNOWN_INACTIVE_STATUSES = new Set([
  "inactive",
  "suspended",
  "expired",
]);
const SAFE_IDENTIFIER = /^[A-Za-z0-9._:-]{1,128}$/;
const SENSITIVE_RESPONSE_FIELDS = new Set([
  "reason",
  "target_resource",
  "provider_side_effect_id",
  "result_summary",
  "normalized_args_json",
  "checkpoint_json",
]);

type EntitlementRow = {
  edition: string;
  status: string;
  effective_at: Date | string;
  expires_at: Date | string | null;
};

function timestamp(value: Date | string | null) {
  if (value === null) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}

export function strictApprovalReadIdentifier(value: unknown, field: string) {
  if (typeof value !== "string" || !SAFE_IDENTIFIER.test(value)) {
    throw new ControlPlaneHttpError(
      400,
      `${field}_invalid`,
      `${field} must use 1-128 safe identifier characters.`,
    );
  }
  return value;
}

export function strictApprovalReadQuery(
  request: Request,
  allowed: readonly string[],
) {
  const parameters = new URL(request.url).searchParams;
  const allowedKeys = new Set(allowed);
  const keys = [...new Set(parameters.keys())];
  if (keys.some((key) => !allowedKeys.has(key))) {
    throw new ControlPlaneHttpError(
      400,
      "approval_read_query_unsupported",
      "The approval read received an unsupported query parameter.",
    );
  }
  for (const key of keys) {
    if (parameters.getAll(key).length !== 1) {
      throw new ControlPlaneHttpError(
        400,
        "approval_read_query_ambiguous",
        "Approval read query parameters must have exactly one value.",
      );
    }
    const value = parameters.get(key) ?? "";
    if (!value || value !== value.trim() || value.length > 256) {
      throw new ControlPlaneHttpError(
        400,
        "approval_read_query_invalid",
        "Approval read query parameters must contain one bounded canonical value.",
      );
    }
  }
  return Object.fromEntries(allowed.map((key) => [key, parameters.get(key)]));
}

export function assertApprovalReadRole(identity: HumanSessionIdentity) {
  const role = identity.membershipRole.trim().toLowerCase();
  if (!APPROVAL_READ_ROLES.has(role)) {
    throw new ControlPlaneHttpError(
      403,
      "human_approval_read_role_forbidden",
      "Approval reads require operator, approver, reviewer, workspace-admin, or owner authority.",
    );
  }
  return role;
}

export async function assertActiveApprovalReadEntitlement(
  client: PoolClient,
  workspaceId: string,
) {
  await client.query(
    "SELECT pg_advisory_xact_lock(hashtextextended($1,0))",
    [`agentops:workspace-entitlement:${workspaceId}`],
  );
  const evaluatedAt = timestamp((await client.query<{ evaluated_at: Date | string }>(
    "SELECT clock_timestamp() AS evaluated_at",
  )).rows[0]?.evaluated_at ?? "");
  const entitlement = (await client.query<EntitlementRow>(
    `SELECT edition,status,effective_at,expires_at
    FROM workspace_entitlements WHERE workspace_id=$1`,
    [workspaceId],
  )).rows[0];
  if (!entitlement) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_missing",
      "This workspace has no commercial entitlement.",
    );
  }
  const effectiveAt = timestamp(entitlement.effective_at);
  const expiresAt = timestamp(entitlement.expires_at);
  if (
    !evaluatedAt
    || !effectiveAt
    || (entitlement.expires_at !== null && !expiresAt)
  ) {
    throw new ControlPlaneHttpError(
      503,
      "workspace_entitlement_invalid",
      "The workspace entitlement state is invalid.",
    );
  }
  if (entitlement.status !== "active") {
    const known = KNOWN_INACTIVE_STATUSES.has(entitlement.status);
    throw new ControlPlaneHttpError(
      known ? 403 : 503,
      known
        ? `workspace_entitlement_${entitlement.status}`
        : "workspace_entitlement_invalid",
      "The workspace entitlement is not active.",
    );
  }
  if (effectiveAt.getTime() > evaluatedAt.getTime()) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_not_effective",
      "The workspace entitlement is not effective yet.",
    );
  }
  if (expiresAt && expiresAt.getTime() <= evaluatedAt.getTime()) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_expired",
      "The workspace entitlement has expired.",
    );
  }
  if (!COMMERCIAL_EDITIONS.has(entitlement.edition)) {
    throw new ControlPlaneHttpError(
      403,
      "workspace_entitlement_edition_forbidden",
      "Approval reads require a commercial workspace edition.",
    );
  }
  return entitlement.edition;
}

export function boundedApprovalReadText(
  value: unknown,
  field: string,
  maximum: number,
  nullable = false,
) {
  if (value === null && nullable) return null;
  if (
    typeof value !== "string"
    || value.length < 1
    || value.length > maximum
    || /[\0-\x08\x0B\x0C\x0E-\x1F\x7F]/.test(value)
  ) {
    throw new ControlPlaneHttpError(
      503,
      "approval_read_state_invalid",
      `Stored ${field} is outside the bounded approval read contract.`,
    );
  }
  return value;
}

export function boundedApprovalReadTimestamp(
  value: Date | string | null,
  field: string,
  nullable = false,
) {
  if (value === null && nullable) return null;
  const parsed = timestamp(value);
  if (!parsed) {
    throw new ControlPlaneHttpError(
      503,
      "approval_read_state_invalid",
      `Stored ${field} is outside the bounded approval read contract.`,
    );
  }
  return parsed.toISOString();
}

export function assertBoundedApprovalReceipt<T extends Record<string, unknown>>(
  body: T,
): T {
  const visit = (value: unknown, depth: number) => {
    if (depth > 8) throw new Error("approval_receipt_depth_invalid");
    if (typeof value === "string") {
      if (value.length > 2048 || /[\0-\x08\x0B\x0C\x0E-\x1F\x7F]/.test(value)) {
        throw new Error("approval_receipt_text_invalid");
      }
      return;
    }
    if (Array.isArray(value)) {
      if (value.length > 128) throw new Error("approval_receipt_array_invalid");
      value.forEach((item) => visit(item, depth + 1));
      return;
    }
    if (value && typeof value === "object") {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length > 64) throw new Error("approval_receipt_object_invalid");
      for (const [key, item] of entries) {
        if (SENSITIVE_RESPONSE_FIELDS.has(key)) {
          throw new Error("approval_receipt_sensitive_field_present");
        }
        visit(item, depth + 1);
      }
    }
  };
  try {
    visit(body, 0);
    if (Buffer.byteLength(JSON.stringify(body), "utf8") > 64 * 1024) {
      throw new Error("approval_receipt_size_invalid");
    }
  } catch {
    throw new ControlPlaneHttpError(
      503,
      "approval_read_state_invalid",
      "The approval receipt is outside the bounded safe projection.",
    );
  }
  return body;
}
