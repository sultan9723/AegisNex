import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HOP_BY_HOP_REQUEST_HEADERS = [
  "connection",
  "content-length",
  "host",
  "transfer-encoding",
];
const HOP_BY_HOP_RESPONSE_HEADERS = ["connection", "content-length", "transfer-encoding"];

function backendBaseUrl(): string | null {
  const configured = process.env.BACKEND_INTERNAL_URL?.trim();
  if (!configured) return null;

  try {
    const url = new URL(configured);
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    return configured.replace(/\/+$/, "");
  } catch {
    return null;
  }
}

function copyResponseHeaders(response: Response): Headers {
  const headers = new Headers();
  response.headers.forEach((value, key) => {
    if (key !== "set-cookie" && !HOP_BY_HOP_RESPONSE_HEADERS.includes(key)) {
      headers.set(key, value);
    }
  });

  const responseHeaders = response.headers as Headers & {
    getSetCookie?: () => string[];
  };
  const cookies = responseHeaders.getSetCookie?.() ?? [];
  if (cookies.length > 0) {
    for (const cookie of cookies) headers.append("set-cookie", cookie);
  } else {
    const cookie = response.headers.get("set-cookie");
    if (cookie) headers.set("set-cookie", cookie);
  }

  return headers;
}

async function proxyApiRequest(
  request: NextRequest,
  context: { params: Promise<{ path: string[] }> },
): Promise<Response> {
  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return Response.json({ detail: "Backend proxy is not configured" }, { status: 503 });
  }

  const { path } = await context.params;
  const encodedPath = path.map((segment) => encodeURIComponent(segment)).join("/");
  const requestUrl = new URL(request.url);
  const targetUrl = `${baseUrl}/api/${encodedPath}${requestUrl.search}`;
  const headers = new Headers(request.headers);

  for (const header of HOP_BY_HOP_REQUEST_HEADERS) headers.delete(header);

  const body = request.method === "GET" || request.method === "HEAD"
    ? undefined
    : await request.arrayBuffer();

  const response = await fetch(targetUrl, {
    method: request.method,
    headers,
    body,
    redirect: "manual",
  });

  const responseBody = [204, 205, 304].includes(response.status) || request.method === "HEAD"
    ? null
    : response.body;

  return new Response(responseBody, {
    status: response.status,
    statusText: response.statusText,
    headers: copyResponseHeaders(response),
  });
}

export const GET = proxyApiRequest;
export const HEAD = proxyApiRequest;
export const POST = proxyApiRequest;
export const PUT = proxyApiRequest;
export const PATCH = proxyApiRequest;
export const DELETE = proxyApiRequest;
export const OPTIONS = proxyApiRequest;
