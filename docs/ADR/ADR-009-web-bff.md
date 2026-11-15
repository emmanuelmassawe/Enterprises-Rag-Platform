# ADR-009: Next.js BFF and Google sign-in

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

The browser must not receive provider/API keys. The UI is in scope and the owner specified Google-only login, while details of Google Workspace restrictions and user provisioning are open.

## Decision

Use Next.js App Router as a same-origin BFF, TypeScript strict, and server-side Google OIDC login (OIDC/Auth.js implementation to be verified at implementation). Browser receives only a Secure, HttpOnly, SameSite session cookie. BFF enforces CSRF/origin checks and role mapping; API re-authorizes server-issued identity. UI localizes English and Swahili and renders model output through a safe allowlist renderer.

## Evidence checked

- Exact Auth.js/Google SDK configuration, cookie options and supported releases are implementation-specific and have not been verified here. Check current official Auth.js and Google Identity docs before coding.
- Security properties are project requirements from BRIEF §10A; must be proven with browser and XSS tests.

## Consequences

- Secrets stay server-side and browser requests are same-origin.
- BFF adds a deployable service and requires secure session rotation, CSRF and logout invalidation.
- Google Workspace domain restrictions and tenant provisioning remain owner questions.

