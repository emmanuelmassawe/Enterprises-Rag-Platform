import { randomBytes } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";

export function proxy(request: NextRequest): NextResponse {
  const nonce = randomBytes(18).toString("base64");
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  const faro = process.env.FARO_COLLECTOR_URL;
  const collectorOrigin = faro ? new URL(faro).origin : "'self'";
  const production = process.env.NODE_ENV === "production";
  const directives = ["default-src 'self'", `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`, "style-src 'self'", "img-src 'self' data: blob:", "font-src 'self' data:", `connect-src 'self' ${collectorOrigin}`, "object-src 'none'", "base-uri 'self'", "form-action 'self'", "frame-ancestors 'none'", ...(production ? ["upgrade-insecure-requests"] : [])].join("; ");
  const response = NextResponse.next({ request: { headers: requestHeaders } });
  response.headers.set("Content-Security-Policy", directives);
  response.headers.set("X-Content-Type-Options", "nosniff");
  response.headers.set("Referrer-Policy", "strict-origin-when-cross-origin");
  response.headers.set("X-Frame-Options", "DENY");
  response.headers.set("Permissions-Policy", "camera=(), microphone=(), geolocation=()");
  if (production) response.headers.set("Strict-Transport-Security", "max-age=31536000; includeSubDomains");
  return response;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)"] };
