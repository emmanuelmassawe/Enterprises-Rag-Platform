import { auth } from "@/auth";
import { identityForEmail } from "@/lib/server/identity-directory";

type RouteContext = { params: Promise<{ path: string[] }> };
const forwardedHeaders = ["accept", "content-type", "idempotency-key", "if-match", "traceparent", "x-request-id"];

function originAllowed(request: Request): boolean {
  const origin = request.headers.get("origin");
  const expected = process.env.APP_ORIGIN;
  return Boolean(origin && expected && new URL(origin).origin === new URL(expected).origin);
}

async function forward(request: Request, context: RouteContext): Promise<Response> {
  const method = request.method.toUpperCase();
  if (!new Set(["GET", "POST", "PATCH", "DELETE"]).has(method)) return Response.json({ code: "method_not_allowed" }, { status: 405 });
  if (method !== "GET" && !originAllowed(request)) return Response.json({ code: "csrf_origin_rejected" }, { status: 403 });
  const session = await auth();
  const email = session?.user?.email;
  if (!email) return Response.json({ code: "authentication_required" }, { status: 401 });
  const { path } = await context.params;
  if (!path.length || path.some((part) => part === "." || part === "..")) return Response.json({ code: "not_found" }, { status: 404 });
  const identity = identityForEmail(email);
  if (!identity) return Response.json({ code: "authentication_required" }, { status: 401 });
  const adminRoute = path[0] === "v1" && path[1] === "admin";
  const editorWrite = method !== "GET" && path[0] === "v1" && ["collections", "documents", "jobs"].includes(path[1] ?? "");
  if ((adminRoute && identity.role !== "admin") || (editorWrite && !["editor", "admin"].includes(identity.role))) {
    return Response.json({ code: "permission_denied" }, { status: 403 });
  }
  const base = process.env.RAG_API_URL;
  if (!base) return Response.json({ code: "dependency_unavailable" }, { status: 503 });
  const suffix = path.map(encodeURIComponent).join("/");
  const target = new URL(`${suffix}${new URL(request.url).search}`, base.endsWith("/") ? base : `${base}/`);
  const headers = new Headers({ authorization: `Bearer ${identity.api_key}` });
  for (const name of forwardedHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const init: RequestInit & { duplex?: "half" } = {
    method,
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(method === "POST" && path.at(-1) === "query" ? 70_000 : 15_000),
  };
  if (method !== "GET" && method !== "DELETE" && request.body) {
    init.body = request.body;
    init.duplex = "half";
  }
  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return Response.json({ code: "dependency_unavailable" }, { status: 503 });
  }
  const responseHeaders = new Headers();
  for (const name of ["content-type", "x-request-id", "x-trace-id", "retry-after", "ratelimit-limit", "ratelimit-remaining", "ratelimit-reset"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }
  responseHeaders.set("cache-control", "no-store, no-transform");
  responseHeaders.set("x-accel-buffering", "no");
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export const GET = forward;
export const POST = forward;
export const PATCH = forward;
export const DELETE = forward;
