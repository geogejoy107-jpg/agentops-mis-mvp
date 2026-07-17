import http from "node:http";
import https from "node:https";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { proxyBaseUrl } from "./config";

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

export async function proxyControlPlaneRequest(request: NextRequest, upstreamPath: string) {
  const body = ["GET", "HEAD"].includes(request.method)
    ? undefined
    : Buffer.from(await request.arrayBuffer());
  const path = upstreamPath.startsWith("/") ? upstreamPath : `/${upstreamPath}`;
  const url = new URL(`${proxyBaseUrl()}${path}${request.nextUrl.search}`);
  const headers: Record<string, string> = {};
  for (const [key, value] of request.headers.entries()) {
    const normalized = key.toLowerCase();
    if (!HOP_BY_HOP_HEADERS.has(normalized) && normalized !== "host" && normalized !== "content-length") {
      headers[key] = value;
    }
  }
  if (body) headers["content-length"] = String(body.byteLength);

  const upstream = await new Promise<{
    status: number;
    statusText: string;
    headers: Headers;
    body: Buffer;
  }>((resolve, reject) => {
    const client = url.protocol === "https:" ? https : http;
    const outgoing = client.request(url, { method: request.method, headers }, (response) => {
      const chunks: Buffer[] = [];
      response.on("data", (chunk: Buffer | string) => {
        chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
      });
      response.on("end", () => {
        const responseHeaders = new Headers();
        for (const [key, value] of Object.entries(response.headers)) {
          if (Array.isArray(value)) {
            for (const item of value) responseHeaders.append(key, item);
          } else if (value !== undefined) {
            responseHeaders.set(key, String(value));
          }
        }
        resolve({
          status: response.statusCode || 502,
          statusText: response.statusMessage || "",
          headers: responseHeaders,
          body: Buffer.concat(chunks),
        });
      });
    });
    outgoing.on("error", reject);
    if (body) outgoing.write(body);
    outgoing.end();
  });
  const responseHeaders = new Headers(upstream.headers);
  for (const key of HOP_BY_HOP_HEADERS) responseHeaders.delete(key);
  responseHeaders.delete("content-length");
  return new NextResponse(upstream.body.byteLength > 0 ? upstream.body : null, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  });
}
