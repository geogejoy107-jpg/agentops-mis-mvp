import { NextRequest, NextResponse } from "next/server";

const TARGET_BASE = process.env.AGENTOPS_API_BASE || "http://127.0.0.1:8765/api";
const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
]);

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

function proxyUrl(path: string[], search: string) {
  const cleanPath = path.map((part) => encodeURIComponent(part)).join("/");
  return `${TARGET_BASE.replace(/\/$/, "")}/${cleanPath}${search}`;
}

function forwardedHeaders(request: NextRequest) {
  const headers = new Headers();
  for (const [key, value] of request.headers.entries()) {
    const normalized = key.toLowerCase();
    if (!HOP_BY_HOP_HEADERS.has(normalized) && normalized !== "host") {
      headers.set(key, value);
    }
  }
  return headers;
}

async function proxy(request: NextRequest, context: RouteContext) {
  const { path = [] } = await context.params;
  const body = ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer();
  const response = await fetch(proxyUrl(path, request.nextUrl.search), {
    method: request.method,
    headers: forwardedHeaders(request),
    body,
    cache: "no-store",
  });
  const headers = new Headers(response.headers);
  for (const key of HOP_BY_HOP_HEADERS) {
    headers.delete(key);
  }
  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export const GET = proxy;
export const POST = proxy;
export const PUT = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
