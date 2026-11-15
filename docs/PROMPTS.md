# Prompts for Codex (copy one at a time)

Use one prompt per milestone, in order. Start a fresh Codex session for each milestone (AGENTS.md is reloaded automatically and keeps the rules in force). Do not paste the next prompt until you have reviewed the previous milestone and ticked its box in `docs/APPROVALS.md`.

---

## Prompt 0: Phase 0 design (documents only, NO code)

```
Read AGENTS.md, docs/BRIEF.md (all of it), and docs/OWNER_DECISIONS.md.

Execute Milestone 0 only (BRIEF Section 0A, Phase 0 design-first). Write NO application code, no src/, no web/, no scaffolding.

Deliver, committed to the repo:
1. docs/REQUIREMENTS.md: functional requirements (IDs, MoSCoW, Given/When/Then acceptance criteria) and non-functional requirements (IDs, measurable targets, measurement and verification method). Use the proposed defaults in the brief where docs/OWNER_DECISIONS.md is silent, marked "proposed, confirm with owner". List open questions.
2. docs/API_DESIGN.md and api/openapi.yaml (OpenAPI 3.1, lint-clean with Spectral): everything listed in BRIEF Section 0A Deliverable 2, including the SSE event contract and the endpoints needed by the web UI.
3. docs/ARCHITECTURE.md with Mermaid diagrams, docs/ADR/ with initial ADRs, docs/GLOSSARY.md, and a mapping of each NFR to the architectural decision that satisfies it.
4. docs/TRACEABILITY.md (requirement -> component -> endpoint -> test -> monitoring).
5. docs/UX.md outline (personas and key flows aligned to the FRs).

Verify third-party/provider facts (Render, Terraform provider, LangSmith, Grafana, pgvector) against current official docs and cite what you checked in the ADRs.

When finished, post the Phase 0 summary in the format defined in AGENTS.md section 7, with assumptions, open questions and risks. Then STOP and wait for my approval. Do not start Milestone 1.
```

---

## Prompt 1: Scaffold, tooling, CI, Docker

```
Read AGENTS.md. Confirm in docs/APPROVALS.md that Milestone 0 is approved; if not, stop and tell me.
Read docs/BRIEF.md Sections 2, 2B, 3, 9, 10 and the approved docs/REQUIREMENTS.md, docs/API_DESIGN.md, docs/ARCHITECTURE.md.

Execute Milestone 1 only: repo scaffold following the hexagonal layout, uv + pyproject, ruff, mypy strict, import-linter contracts, pytest setup, pre-commit, Makefile targets, config with pydantic-settings and fail-fast validation, structured logging, request IDs, /healthz and /readyz and /version, Dockerfile (multi-stage, non-root), docker-compose.yml (api, worker, postgres+pgvector, two Redis instances, minio), .env.example, GitHub Actions CI skeleton with all the gates from BRIEF Sections 9 and 10B (forbidden patterns, gitleaks, pip-audit, image scan), PR template, CODEOWNERS, CONTRIBUTING.md, and an initial README with the architecture diagrams.

Verify everything by running it: docker compose up, health endpoints, make lint/typecheck/test. Report results honestly. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 2: Database, RLS, auth, rate limiting

```
Read AGENTS.md. Confirm Milestone 1 is approved in docs/APPROVALS.md.
Read docs/BRIEF.md Sections 4, 5, 5A (controls 4, 6, 7, 10), 6B and the approved requirements and API design.

Execute Milestone 2 only: SQLAlchemy 2.0 async models, Alembic migrations (including CREATE EXTENSION vector), Postgres Row-Level Security with separate migration and application DB roles, repositories behind ports, API key auth (hashed, scoped), tenant resolution bound to the request context, rate limiting and quotas on Redis (rag-state) behind ports with in-memory fakes, contract tests for every port, and a test that proves cross-tenant access is impossible even if application filters are bypassed.

Run migrations on an empty and a populated database. Include fault-injection tests for Postgres and Redis outages. Report honestly. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 3: Ingestion pipeline

```
Read AGENTS.md. Confirm Milestone 2 is approved.
Read docs/BRIEF.md Sections 3 (ingestion), 5A (control 2), 6B, 10B and the approved requirements and API design.

Execute Milestone 3 only: document upload API (streaming, size/type limits, content sniffing, virus-scan hook, idempotency key), BlobStore port with S3-compatible and local adapters, Redis-backed queue worker with retries and DLQ, parsers (PDF, DOCX, TXT, MD, HTML) with sanitization of hidden text, chunking with page/section metadata, embedding providers behind ports with batching, upsert with content-hash dedup, injection scan and quarantine of suspicious chunks, job status API, deletion cascade (DB, blobs, embeddings, Redis), and tests including crash-mid-job and duplicate delivery.

Include fixtures with poisoned documents (hidden text, injection payloads). Report honestly. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 4: Retrieval and generation

```
Read AGENTS.md. Confirm Milestone 3 is approved.
Read docs/BRIEF.md Sections 2A, 3 (query pipeline), 5A (controls 1, 3, 5), 6B and the approved requirements and API design.

Execute Milestone 4 only: hybrid retrieval (pgvector HNSW + Postgres FTS) with Reciprocal Rank Fusion and a pluggable reranker, tenant/ACL-aware retrieval, context assembly under a token budget, versioned prompts with random per-request boundary tokens, LLM provider port with timeouts/retries/circuit breaker, structured output with citation verification and groundedness check, refusal when evidence is insufficient, output scanning and exfiltration prevention, SSE streaming following the contract in api/openapi.yaml, exact and semantic caching on rag-cache with version-aware keys and invalidation, conversations and messages endpoints, feedback endpoint.

Measure retrieval quality separately from generation. Record EXPLAIN ANALYZE results for the main queries. Report honestly. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 5: Observability, resilience, AI security layer

```
Read AGENTS.md. Confirm Milestone 4 is approved.
Read docs/BRIEF.md Sections 5A (all), 6, 6A, 6B, 6C, 10B and the approved requirements.

Execute Milestone 5 only: OpenTelemetry instrumentation, protected /metrics with the metric set and cardinality rules from Section 6C, LangSmith integration behind the LLMTracer port (masked inputs/outputs, feedback scores, outage-safe, per-tenant opt-out), correlation IDs across logs/traces/LangSmith, the complete AI security layer from Section 5A (injection detector port, spotlighting, canary, security events, quotas, kill switch, fallback modes), Grafana dashboards and alert rules as code in infra/grafana (validated locally with the observability compose profile), docs/SLO.md, docs/AI_SECURITY.md with the OWASP LLM Top 10 mapping, docs/RUNBOOK_AI_INCIDENTS.md, the red-team suite in tests/security with Attack Success Rate reporting, fault-injection tests, and a load-test script with recorded baseline results.

Verify LangSmith, Grafana and Render details against current official docs. Report honestly, including any red-team category that does not meet its threshold. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 6: Evaluation harness

```
Read AGENTS.md. Confirm Milestone 5 is approved.
Read docs/BRIEF.md Sections 7, 6A and the approved requirements (RAG quality NFRs).

Execute Milestone 6 only: golden dataset (questions, expected sources, reference answers, include Swahili and English if specified in docs/OWNER_DECISIONS.md), retrieval metrics (recall@k, MRR, nDCG), generation metrics (groundedness, answer relevance, citation accuracy, refusal accuracy) with an LLM-as-judge behind a port, LangSmith datasets/experiments integration, `make eval` with thresholds that fail CI, a baseline report in docs/, and a documented procedure for blue/green re-indexing evaluation.

Report the baseline numbers honestly and propose thresholds. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 7: Terraform and staging deployment

```
Read AGENTS.md. Confirm Milestone 6 is approved.
Read docs/BRIEF.md Sections 8, 9, 6B, 6C, 10B (sections C, D, E) and the approved architecture.

Execute Milestone 7 only: Terraform for Render following the layout in Section 8 (project/environments, Postgres, two Key Value instances with the correct eviction policies, API web service, worker, Grafana Alloy private service, rag-web placeholder service config if UI is not built yet, env groups, pre-deploy migrations) and the Grafana provider resources. Remote state with locking, pinned versions, envs/*.tfvars.example (no secrets), tflint and tfsec/checkov in CI, plan on PRs, apply only through the pipeline with manual approval for production.

Verify every resource and argument against the current provider docs; document any gap and the fallback. Do NOT run terraform apply against production and do not ask me for production credentials. Run `terraform plan` only unless I explicitly provide staging credentials and ask for a staging apply. Write the deployment guide, including rollback. Report honestly. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 8: Web UI/UX

```
Read AGENTS.md. Confirm Milestone 7 is approved.
Read docs/BRIEF.md Section 10A, 5A (UI-specific security), 6C (Faro), and docs/UX.md, docs/API_DESIGN.md.

Execute Milestone 8 only: the Next.js web UI exactly as specified in Section 10A: BFF with session auth (no secrets in the browser), streaming chat with first-class verifiable citations and all the UI states, conversation history, knowledge-base management with live ingestion status, admin area with quarantine review, settings, English and Swahili i18n, light/dark themes, responsive layout, WCAG 2.2 AA, safe rendering of model output, Playwright e2e tests (including XSS tests with adversarial outputs), axe and Lighthouse CI budgets, Grafana Faro, the rag-web Terraform config, and screenshots/GIF for the README. Develop against the OpenAPI mock server first, then the real API.

Complete docs/UX.md with design tokens and decisions. Report honestly. Then STOP with the AGENTS.md section 7 summary.
```

---

## Prompt 9: Production Readiness Review and docs

```
Read AGENTS.md. Confirm Milestone 8 is approved.
Read docs/BRIEF.md Sections 10B, 11, 10 (README requirements).

Execute Milestone 9 only: run the production-readiness verification and record evidence in docs/PRODUCTION_READINESS.md: chaos/fault-injection runs, load/soak/spike results against staging compared with the NFRs, backup and restore drill with measured RTO/RPO, zero-downtime deploy and rollback rehearsal, security review, dependency/image scan results, alert firing exercise, cost model and provider spend caps, traceability matrix with no untested requirement. Complete the README (all required sections, Mermaid diagrams, principles tables, screenshots), ADR index, CHANGELOG, and the docs CI checks.

Do not mark anything as passed without evidence. List every item that failed or could not be verified. End with a go/no-go recommendation; the decision is mine. Then STOP with the AGENTS.md section 7 summary.
```

---

## Utility prompts

**Review a milestone before I approve it**
```
Act as an independent senior reviewer. Without changing any code, review the work of the last milestone against AGENTS.md, docs/BRIEF.md, and the approved requirements/API design. Check: requirement coverage, security rules (RLS, secrets, output handling), production-readiness rules (no stubs, timeouts, bounds), test quality (failure modes, contract tests), docs accuracy. Run the checks yourself and report real results. List findings by severity with file references.
```

**Fix failing CI**
```
CI is failing. Read the failing job logs, find the root cause, and fix it properly. Do not weaken, skip or delete tests or gates. Explain the cause and the fix, and run the checks locally before finishing.
```

**Security deep-dive**
```
Perform a security review of the current code against docs/BRIEF.md Sections 5 and 5A and the OWASP Top 10 for LLM Applications. Try to break it: cross-tenant access, prompt injection via documents, exfiltration via model output, cache poisoning, quota bypass, SSRF/path traversal in uploads/URLs, secret leakage in logs and traces. Add failing tests for each real issue found, then fix them. Report honestly.
```

**Resume after a long break or lost context**
```
Read AGENTS.md and docs/APPROVALS.md. Inspect the git log and the repository to determine the current state. Summarize which milestone is in progress, what is done, what is missing, and the next step. Do not change anything until I confirm.
```
