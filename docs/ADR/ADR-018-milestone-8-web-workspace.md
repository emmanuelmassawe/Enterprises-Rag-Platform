# ADR-018: Milestone 8 web workspace and BFF

- Status: Implemented; owner approval pending.
- Date: 2026-11-17.
- Deciders: Project owner (approval pending), implementation team.

## Context

Milestone 8 adds the user-facing RAG workspace without putting API credentials in the browser. The existing API uses tenant-scoped API keys and roles, while the web identity is a Google OIDC user. Each admitted email therefore needs an explicit server-side mapping to one API key and role; there is no inferred tenant membership. API authorization remains authoritative when the BFF also applies role gates.

## Decisions

1. Use Next.js App Router, strict TypeScript, Tailwind CSS 4 semantic tokens, Radix Dialog primitives, TanStack Query for in-memory server state, Zod for boundary validation, and `react-markdown` without raw HTML support. Model Markdown images are omitted; links are limited to HTTP(S), rendered with `noopener noreferrer`, and show their destination.
2. Use Auth.js Google OIDC with verified email and an allowlisted `WEB_IDENTITY_DIRECTORY_JSON` mapping held by the server. The browser gets only the Auth.js session cookie and a non-secret email/role context. The mapping contains per-user API keys and role labels and must be provisioned as a protected secret; absent or duplicate mappings fail closed.
3. Proxy RAG API calls through same-origin `/api/rag/*`. The BFF attaches API credentials on the server, checks session and role, limits upstream duration, preserves SSE streaming, restricts forwarded headers, and checks `Origin` on unsafe methods. Do not expose a permissive CORS policy.
4. Set a per-request nonce CSP and standard response security headers in Next.js `proxy.ts`; keep runtime collector configuration server-delivered and configure Faro without console capture or user/message attributes.
5. Deploy the Next.js standalone image as a separate Render web service. Keep OAuth, Auth.js, identity mapping and API credentials in sensitive Terraform variables. The web service does not link the API/worker environment group, which contains provider and storage secrets.
6. Conversation ownership is associated with the mapped API key because the backend principal is API-key scoped. This gives an explicitly provisioned Google identity a stable workspace; a future user-to-tenant membership model requires an approved schema/API change.

## Consequences and known gaps

- The operator must provision and rotate one API key per Google identity and keep identity directory JSON current. There is no self-service account enrollment.
- Google OAuth client details, public origins, per-environment identity mappings, and custom domain/TLS are deployment inputs; no real credentials are committed.
- The UI exposes the current API contract. Original source-file links are not available because the contract has no authorized document download endpoint. The query stream's done event does not expose a LangSmith run reference, so the UI does not claim trace correlation at the user layer.
- CI runs lint, strict TypeScript checking and a production build. Playwright, axe, Lighthouse and visual screenshots remain release gates until run with an approved non-production identity and deployment configuration.
- Usage cost is labelled unavailable when provider pricing is not configured; it is not fabricated from token totals.

## Official documentation checked (2026-11-17)

- Next.js App Router, routing and server/client component guidance: [Next.js App Router](https://nextjs.org/docs/app).
- Next.js proxy file convention and request handling: [Next.js proxy](https://nextjs.org/docs/app/api-reference/file-conventions/proxy).
- Next.js security headers and CSP guidance: [Next.js headers](https://nextjs.org/docs/app/api-reference/config/next-config-js/headers).
- Next.js BFF guidance: [Backend for Frontend](https://nextjs.org/docs/app/guides/backend-for-frontend).
- Render Terraform provider 1.9.1 [`render_web_service`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/web_service) schema, specifically Docker context relative to repository root and Dockerfile path relative to repository root.
- Auth.js setup and Google provider configuration: [Auth.js getting started](https://authjs.dev/getting-started), [Google provider](https://authjs.dev/getting-started/providers/google).
- Tailwind CSS framework integration: [Tailwind CSS with Next.js](https://tailwindcss.com/docs/installation/framework-guides/nextjs).
- Radix-based Next.js component setup: [shadcn/ui Next.js installation](https://ui.shadcn.com/docs/installation/next).
- Faro browser instrumentation and privacy controls: [Grafana Faro getting started](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/frontend-observability/get-started/).

The deployment resource schema is implemented using the provider and Render service decisions recorded in [ADR-017](ADR-017-m7-render-grafana-infrastructure.md). Current Terraform validation is required before merge; no provider apply is part of this milestone.

## Alternatives considered

- Sending the RAG API key to browser code: rejected because browser storage and network requests make a secret unrecoverable once exposed.
- Trusting the role supplied by the browser: rejected; role is derived on the server and checked by the API as well.
- Sharing the API environment group with the web service: rejected because it would expose embedding, blob-store and tracing credentials to the web process.
- Storing bearer tokens or conversation state in localStorage: rejected; only theme/locale preferences may persist client-side.
