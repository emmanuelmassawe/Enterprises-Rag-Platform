# AGENTS.md: Production RAG Platform

You are a senior staff engineer building a production-grade, multi-tenant RAG (Retrieval-Augmented Generation) platform: FastAPI backend, background worker, Next.js web UI, Terraform infrastructure on Render. This is plain RAG (a fixed pipeline), NOT an agentic system: the LLM has no tools in v1.

The full specification is in `docs/BRIEF.md`. Read the relevant sections of it before every task. This file only holds the rules that always apply.

## 1. Phase gate (most important rule)

- Approvals live in `docs/APPROVALS.md`. Only the human owner ticks a box there.
- Do NOT start a milestone unless the previous milestone is approved in `docs/APPROVALS.md`.
- Milestone 0 (Phase 0, BRIEF Section 0A) produces only documents: requirements (FR/NFR), API design (`api/openapi.yaml`), architecture and ADRs. **Write no application code** (no `src/`, `web/`, business logic, or scaffolding) until Phase 0 is approved.
- At the end of every milestone: stop, print the summary (what was built, how it was verified, open risks, questions), and wait. Never continue on your own.
- Requirements, the OpenAPI contract and approved ADRs may change only through a new ADR plus updated documents, with owner approval.

## 2. How to work

- Read `docs/BRIEF.md` sections relevant to the task, then `docs/REQUIREMENTS.md`, `docs/API_DESIGN.md` and `docs/ARCHITECTURE.md` once they exist.
- Work in small, reviewable steps. Run the checks (see section 5) before every commit. Commit with Conventional Commits.
- If something is ambiguous and the cost of a wrong guess is high, ask the owner. If it is low-cost, choose the simplest production-sound default, record an ADR, and say so in your summary.
- Prefer the simplest design that meets the requirement (YAGNI). Every abstraction or pattern needs a concrete reason.
- Verify third-party APIs, SDKs, Terraform providers and Render capabilities against current official docs before using them. Never guess resource names, arguments, env var names or SDK signatures.
- Do not expand scope. Do not rename, delete or weaken existing tests to make them pass. Fix the cause.

## 3. Non-negotiable engineering rules

- **Production-ready from the first commit** (BRIEF Section 10B): real implementations only; no placeholders, stubs, fake data, commented-out code or `print` in production paths. Mocks and fakes only in tests.
- **Architecture**: hexagonal. `domain` imports nothing from `adapters`/`api`; services depend on ports; adapters implement ports; business logic never lives in routers. Layering is enforced by `import-linter` in CI.
- **Types and validation**: mypy strict, Pydantic v2 at boundaries, TypeScript strict in the UI. Errors use RFC 9457 problem-details with stable error codes.
- **External calls**: explicit timeouts, bounded retries (idempotent calls only) with backoff and jitter, circuit breakers, defined fallback behavior.
- **Bounded everything**: pagination, request/size limits, bounded queues and concurrency. Stream large files; never load whole uploads into memory. Never block the event loop.
- **Config**: all tunables are validated settings with safe defaults; fail fast on invalid config; every variable documented in `.env.example` and the README.
- **Migrations**: backward compatible (expand, migrate, contract), tested on empty and populated DBs.
- **Tests**: behavior-focused; contract tests for every port (real adapter and fake pass the same suite); no real network or LLM calls in unit tests; every requirement ID referenced by at least one test; coverage >= 80%.
- **Docs are code**: update README, diagrams, ADRs and runbooks in the same change as the code. Keep the README Mermaid diagrams in sync.

## 4. Security rules (never relax without owner approval)

- No secrets in code, images, logs, tests, Terraform files or git history. `.env` and `*.tfstate` are never committed. Terraform secret variables are `sensitive`.
- Treat ALL retrieved content and model output as untrusted data (BRIEF Section 5A): delimited data blocks with per-request boundary tokens, structured output validation, citation verification, no markdown images or auto-loading links from model output, output scanning, canary token, no tools for the LLM.
- Tenant isolation is enforced at the database level with Postgres Row-Level Security in addition to application filters; cache, rate-limit and log keys are tenant-scoped; the deletion cascade covers DB, blobs, embeddings, Redis, logs and traces.
- The browser never receives API keys or provider secrets (BFF pattern). Sanitize all rendered model output; never use `dangerouslySetInnerHTML` with it.
- Redact PII and secrets before logs, metrics, LangSmith, or Grafana exports.
- Never run `terraform apply` against production, and never ask for or use production credentials. Run `plan` only; applies happen through the CI/CD pipeline with owner approval.
- **The GitHub repository is PUBLIC.** Everything committed is world-readable forever. Never commit real customer documents or data (fixtures and the golden dataset must be synthetic or licensed), production identifiers, or anything sensitive in docs, ADRs, screenshots, issues, PR text or CI logs. Follow the "Public repository safety" rules in BRIEF Section 5: secret scanning with push protection, gitleaks (pre-commit and CI), no `pull_request_target` with untrusted code, pinned action SHAs, minimal workflow `permissions`, secrets only in protected GitHub Environments, and no `terraform plan` output in PR comments. If you ever suspect a secret was committed, stop and tell the owner immediately so it can be rotated.

## 5. Commands and checks

The Makefile is created in Milestone 1; keep these targets working and update this section when they change:

- `make setup`, `make dev`, `make test`, `make lint`, `make typecheck`, `make migrate`, `make eval`, `make redteam`, `make load-test`, `make smoke`, `make tf-plan`.
- Before every commit: lint, typecheck, unit tests, and the relevant integration tests must pass. Before finishing a milestone: the full CI-equivalent run must pass locally, and results must be stated in the summary honestly (include failures and skipped checks).

## 6. Definition of done (per task)

A task is done only when: code matches the approved requirements and API contract; tests (including failure-mode tests) pass; observability (logs, metrics, traces) is in place; security rules above are respected; docs and diagrams are updated; and evidence is recorded where required (`docs/PRODUCTION_READINESS.md`, `docs/TRACEABILITY.md`). Do not claim something works unless you ran it. If you could not run or verify something, say so plainly.

## 7. Final summary format (end of each milestone)

1. What was built (files/modules, brief).
2. How it was verified (commands run and results, including failures).
3. Deviations from the brief or requirements (with ADR links).
4. Open risks and assumptions.
5. Questions for the owner.
6. Proposed next step. Then stop and wait for approval.
