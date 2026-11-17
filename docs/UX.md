# UX outline

Status: Milestone 8 implementation design. The screens and flows below describe the current `web/` application; test, accessibility and staging evidence is tracked in [production readiness](PRODUCTION_READINESS.md). Requirements map to [REQUIREMENTS.md](REQUIREMENTS.md), and API authorization remains authoritative.

## Personas

| Persona | Need | Primary requirements |
|---|---|---|
| Knowledge user / viewer | Ask a question, trust the answer and inspect source passages | FR-QRY-001..003, FR-CIT-001..002, FR-CNV-001..002, FR-FBK-001, FR-UI-001/002 |
| Knowledge editor | Add, organize and remove PDF knowledge; understand processing failures | FR-ING-001..005, FR-KB-001, FR-UI-003 |
| Tenant administrator | Review quarantined material, manage access and understand usage | FR-ADM-001/002, FR-AUTH-001/003/004, FR-UI-004 |
| Platform operator | Monitor dependencies and investigate incidents with minimal data exposure | FR-STA-001/002, NFR-OBS-001, NFR-OPS-001 |

## Key flows

### Sign-in and session

1. User chooses “Continue with Google”.
2. Server validates OIDC state/nonce and maps approved identity to tenant/role.
3. BFF issues secure HttpOnly same-origin session; browser receives no provider credential.
4. On logout or expiry, BFF invalidates session and UI clears in-memory user data.

### Ask and verify an answer

```mermaid
flowchart TD
  A[Choose collection scope] --> B[Ask question]
  B --> C[Retrieving: status announced politely]
  C --> D{Evidence and policy}
  D -->|Supported| E[Stream provisional answer]
  E --> F[Show verified inline citations]
  F --> G[Open source panel with page and highlighted quote]
  G --> H[Optional feedback]
  D -->|Insufficient| I[Explain no reliable evidence; suggest next step]
  D -->|Guardrail/provider/network issue| J[Explain safe failure and retry/fallback state]
```

Requirements: FR-QRY-001..004, FR-CIT-001/002, FR-CNV-001/002, FR-FBK-001, FR-UI-001. A cancel action aborts the stream; token text is marked provisional until the terminal event. Empty evidence, rate limit, quota, retrieval-only fallback and offline states are distinct.

### Upload and maintain knowledge

1. Editor selects a collection and drops one or more PDFs.
2. UI checks known type/size locally; server remains authoritative and streams each upload.
3. Each file shows queued → processing → ready/failed, stage and safe error; retry only appears for retryable failures.
4. Document list supports search/filter/status; delete requires confirmation and displays cascade operation status.
5. Collection management allows create/rename/delete with impact confirmation.

Requirements: FR-ING-001..005, FR-KB-001, FR-UI-003. No UI claims completion until server job reports terminal state.

### Admin quarantine review

1. Admin opens tenant-scoped review queue.
2. Suspicious source appears as escaped plain text with document/page, reason codes and provenance.
3. Admin records approve/reject and reason; UI confirms decision and audit timestamp.

Requirements: FR-ING-003, FR-ADM-001, FR-UI-004. Plain-text display has no Markdown/HTML interpretation.

### Usage and settings

Admin selects bounded date range for estimated usage/cost, with clear estimate label and quota context. User settings include locale EN/SW, theme light/dark/system, session/logout, and retention information. No conversations, tokens or secrets are stored in localStorage; only non-sensitive preferences may persist.

Requirements: FR-ADM-002, FR-USG-001, FR-UI-002/004.

## Interaction principles and accessibility targets

- English and Swahili externalized strings from first UI milestone; localize dates/numbers and accommodate longer labels.
- Keyboard-first navigation, visible focus, semantic controls and labels; screen reader live region announces state changes and completed chunks politely, not every token.
- Contrast and status are not conveyed by color alone. Reduced-motion preference respected.
- Mobile-first responsive layout; citations panel becomes a bottom sheet on narrow screens; touch targets and composer remain usable with the on-screen keyboard.
- Light, dark and system themes share documented tokens. Model output is rendered through a strict safe Markdown allowlist; no raw HTML, images or automatic remote content.

## Visual structure (concept only)

```text
Desktop: [conversation history] [message stream + sticky composer] [citation detail panel]
Mobile:  [history drawer] [message stream + sticky composer] [citation bottom sheet]
Knowledge: [collection selector] [search/filter + document table] [upload panel/job progress]
Admin: [review queue] [plain-text detail + decision] [usage/status tabs]
```

## Design tokens

The CSS custom properties live in `web/src/app/globals.css`; Tailwind utilities use semantic `@theme inline` aliases. Colors are restrained forest green, warm gold and neutral surfaces. Dark mode changes the same semantic variables rather than maintaining a second component palette.

| Token group | Current values / rule |
|---|---|
| Canvas and surfaces | Light `#f5f7f4`, `#ffffff`, `#eef3ef`; dark `#111a16`, `#18231d`, `#202e26`. |
| Text and borders | Semantic `--ink`, `--muted`, `--line`; pair status icon and label with color. |
| Brand and focus | Forest `#236b53` / dark `#70c29e`; gold focus `#bd8a36` / dark `#e0bd7d`, 3px visible outline. |
| Type | System UI stack (`Aptos`, `Segoe UI`, system sans); no remote font request. |
| Spacing and targets | 4px base rhythm; interactive controls have minimum 44px height/width. |
| Shape and elevation | Cards use 20px radius and soft shadow; controls use 13–16px radius. |
| Motion | 160ms interaction transitions; `prefers-reduced-motion` reduces transitions and animation. |

## Implemented interaction details

| Flow | Screen behavior | API / state |
|---|---|---|
| Login | Google sign-in; unapproved or unverified identities are denied. | Auth.js OIDC callback; server-side identity directory. |
| Chat | New/history/pinned/search, collection scope, streaming, cancel, copy, feedback, retry, refusal and error states. | Conversation CRUD, `/v1/query` SSE, `/v1/feedback`; TanStack Query caches non-secret server state in memory. |
| Sources | Citation opens a keyboard-operable detail dialog with quoted chunk text and provenance. | Citation data returned with query. Original document open/download is not available in the current API contract. |
| Knowledge | Create/rename/delete collections; bounded multi-PDF upload with per-file progress; search/status; retry failed jobs; confirm destructive actions. | Collections, documents and jobs routes via the BFF. |
| Admin | Role-gated quarantine review, API key create/revoke, usage estimate and dependency status. Quarantine is plain text. | Admin endpoints; API authorization repeats the BFF role check. |
| Settings | Theme, language and sign out; retention notice. | Locale route, `next-themes`, Auth.js sign-out. |

The conversation editor presents a revised message as a new user turn, preserving prior history. The current implementation does not offer a source-file URL, retrieval-only mode controls, data-retention edits, or share links. These require API or owner policy decisions and are not presented as working controls.

## Responsive wireframe

```text
Desktop (>= 1024px)
+----------------+-----------------------------------+--------------------+
| Nav / history  | Conversation + sticky composer   | Citation details   |
| Search / pins  | Streaming answer and feedback    | Passage / location |
+----------------+-----------------------------------+--------------------+

Mobile (< 768px)
+-----------------------------------+
| Top bar / navigation drawer       |
| Conversation and status           |
| Sticky composer                   |
| Citation detail dialog / sheet    |
+-----------------------------------+
```

## Verification planned

Playwright flows cover Google login/session, upload/status, streaming citations, refusal, feedback, admin quarantine and mobile viewport. axe and Lighthouse budgets target WCAG 2.2 AA and accessibility ≥90. XSS tests cover HTML/script, Markdown images, unsafe link schemes and remote loads. These tests are future evidence, not completed in Phase 0.

