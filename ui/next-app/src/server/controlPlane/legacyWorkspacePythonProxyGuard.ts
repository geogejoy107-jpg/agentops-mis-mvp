import { NextResponse } from "next/server";

import { legacyPythonProxyAllowed } from "./config";

function sameOriginBrowserMutation(request: Request) {
  const origin = String(request.headers.get("origin") || "").trim();
  const fetchSite = String(request.headers.get("sec-fetch-site") || "").trim().toLowerCase();
  if (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") return false;
  if (!origin) return false;
  try {
    const requestUrl = new URL(request.url);
    const requestHost = String(request.headers.get("host") || requestUrl.host).trim();
    const requestOrigin = new URL(`${requestUrl.protocol}//${requestHost}`).origin;
    return new URL(origin).origin === requestOrigin;
  } catch {
    return false;
  }
}

export function legacyWorkspacePythonProxyGuard(request: Request) {
  let proxyAllowed = false;
  try {
    proxyAllowed = legacyPythonProxyAllowed();
  } catch {
    // Unknown deployment modes fail closed at the route boundary.
  }

  if (proxyAllowed) {
    if (sameOriginBrowserMutation(request)) return null;
    return NextResponse.json(
      {
        ok: false,
        error: "csrf_validation_failed",
        message: "Legacy Free Local workspace writes require a same-origin browser request.",
        python_proxy_performed: false,
        token_omitted: true,
      },
      {
        status: 403,
        headers: {
          "Cache-Control": "no-store",
          Vary: "Origin, Sec-Fetch-Site",
        },
      },
    );
  }

  return NextResponse.json(
    {
      ok: false,
      error: "typescript_route_owner_required",
      message: "Commercial production requires a TypeScript-owned workspace route.",
      python_proxy_performed: false,
      token_omitted: true,
    },
    { status: 503, headers: { "Cache-Control": "no-store" } },
  );
}
