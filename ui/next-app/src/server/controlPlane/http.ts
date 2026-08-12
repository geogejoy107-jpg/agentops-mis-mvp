export class ControlPlaneHttpError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly commitTransaction = false,
  ) {
    super(message);
  }
}

export function errorPayload(error: unknown) {
  if (error instanceof ControlPlaneHttpError) {
    return {
      status: error.status,
      body: { ok: false, error: error.code, message: error.message, token_omitted: true },
    };
  }
  const databaseError = error && typeof error === "object"
    ? error as { code?: unknown; message?: unknown }
    : {};
  if (
    databaseError.code === "23514"
    && databaseError.message === "customer_delivery_evidence_sealed"
  ) {
    return {
      status: 409,
      body: {
        ok: false,
        error: "customer_delivery_evidence_sealed",
        message: "Approved customer-delivery evidence is immutable.",
        token_omitted: true,
      },
    };
  }
  return {
    status: 503,
    body: {
      ok: false,
      error: "typescript_control_plane_unavailable",
      message: "The TypeScript Postgres control plane could not complete the request.",
      token_omitted: true,
    },
  };
}
