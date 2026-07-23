import { NextResponse } from "next/server";

import { legacyPythonProxyAllowed } from "./config";

const LOOPBACK_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);

type ExactOrigin = {
  host: string;
  isHttpLoopback: boolean;
  origin: string;
};

function parseExactOrigin(value: string): ExactOrigin | null {
  const supplied = String(value || "").trim();
  if (!supplied) return null;
  try {
    const parsed = new URL(supplied);
    const isLoopback = LOOPBACK_HOSTNAMES.has(parsed.hostname.toLowerCase());
    if (
      parsed.origin !== supplied
      || parsed.username
      || parsed.password
      || parsed.pathname !== "/"
      || parsed.search
      || parsed.hash
      || (parsed.protocol !== "https:" && !(parsed.protocol === "http:" && isLoopback))
    ) {
      return null;
    }
    return {
      host: parsed.host.toLowerCase(),
      isHttpLoopback: parsed.protocol === "http:" && isLoopback,
      origin: parsed.origin,
    };
  } catch {
    return null;
  }
}

function configuredAllowedOrigins() {
  const configured = String(process.env.AGENTOPS_ALLOWED_ORIGINS || "");
  const entries = configured.split(",").map((item) => item.trim()).filter(Boolean);
  if (!entries.length) return null;

  const allowed = new Map<string, string>();
  for (const entry of entries) {
    const parsed = parseExactOrigin(entry);
    if (!parsed) return null;
    allowed.set(parsed.origin, parsed.host);
  }
  return allowed;
}

function sameOriginBrowserMutation(request: Request) {
  const fetchSite = String(request.headers.get("sec-fetch-site") || "").trim().toLowerCase();
  if (fetchSite && fetchSite !== "same-origin" && fetchSite !== "none") return false;

  const origin = parseExactOrigin(String(request.headers.get("origin") || ""));
  const directHost = String(request.headers.get("host") || "").trim().toLowerCase();
  if (!origin || !directHost || origin.host !== directHost) return false;
  if (origin.isHttpLoopback) return true;

  const allowed = configuredAllowedOrigins();
  return allowed?.get(origin.origin) === directHost;
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
