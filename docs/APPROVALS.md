# Approvals (owner only)

Only the human owner ticks these boxes. The coding agent must not start a milestone until the previous one is approved, and must never edit this file's checkboxes.

- [ tick ] Milestone 0: Phase 0 design approved (requirements FR/NFR, API design + `api/openapi.yaml`, architecture + ADRs)
- [ tick ] Milestone 1: Repo scaffold, tooling, CI skeleton, health endpoints, Docker, docker-compose
- [ tick ] Milestone 2: DB schema, migrations, RLS, repositories, auth, rate limiting
- [ tick ] Milestone 3: Ingestion pipeline (parsers, chunking, embeddings, worker, jobs API, Redis queue)
- [ tick ] Milestone 4: Retrieval, generation, citations, streaming, guardrails, caching
- [ tick ] Milestone 5: Observability (LangSmith, Grafana instrumentation), resilience, AI security layer, red-team suite
- [ tick ] Milestone 6: Evaluation harness and golden dataset
- [tick ] Milestone 7: Terraform (Render, Redis x2, Alloy, Grafana), staging deploy
- [ ] Milestone 8: Web UI/UX
- [ ] Milestone 9: Production Readiness Review, documentation polish, go/no-go

## Owner notes and decisions

(Write dated notes here: answers to the agent's questions, accepted risks, scope changes.)
