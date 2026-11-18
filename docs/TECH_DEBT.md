# Technical debt and release gates

This is the prioritized M9 register. “Owner TBD” means a product/platform owner must assign a person before production. The severity describes release impact, not an estimate of effort.

| ID | Priority | Debt / risk | Owner | Closure evidence |
|---|---|---|---|---|
| TD-001 | Locally verified; CI verification pending | SQLAlchemy metadata now declares `ix_conversations_tenant_owner_key_updated` exactly as created by the web migration; CI runs `alembic check` after both migrations. | Backend owner | CI must pass the schema-parity check on the populated disposable PostgreSQL database. |
| TD-002 | Blocker | No staging deployment, private networking, selected service plans/region, remote state, or protected identity secrets have been verified. | Platform owner TBD | Staging Terraform plan and CI deployment evidence; smoke and rollback rehearsal. |
| TD-003 | Blocker | No measured load, soak, spike, SLO, saturation or memory baseline. | SRE owner TBD | Staging report with workload, model version, p95/p99, errors, throughput and memory compared with approved targets. |
| TD-004 | Blocker | No backup restore drill or measured RTO/RPO. | Data/platform owner TBD | Restore to clean staging instance, verify data and vector indexes, record measured RTO/RPO. |
| TD-005 | High | No end-to-end fault injection for Postgres, Redis, blob, Gemini, worker interruption, duplicate jobs or partial writes. | Backend/SRE TBD | Repeatable integration evidence for each failure and documented recovery/fallback. |
| TD-006 | High | Provider model, region, retention/DPA, spend caps, budget alert and generation kill-switch exercise remain unconfirmed. | Product/security owner TBD | Written owner decisions and staging tests; no production credentials in Git. |
| TD-007 | High | Web browser, Playwright, axe, Lighthouse, WCAG and authenticated screenshot evidence is absent. | Web owner TBD | Non-production login test; recorded flows, axe report and Lighthouse scores against agreed budgets. |
| TD-008 | High | Image vulnerability scan and published SBOM evidence is absent. | Release engineering TBD | CI image scanner and SBOM artifact with no unresolved high/critical findings. |
| TD-009 | High | Grafana alert delivery, on-call ownership, synthetic canary and incident exercise are not verified. | SRE owner TBD | Staging alert fired and handled; contact path and escalation schedule documented. |
| TD-010 | Locally verified; CI verification pending | SQLAlchemy metadata and migration history drift for the conversation owner index. | Backend owner | Same CI `alembic check` evidence as TD-001; retain schema parity check in CI. |
| TD-011 | Medium | Port contract tests and real Redis/database adapter failure tests are incomplete. | Backend owner TBD | Shared contract suite passes against fakes and real disposable services for every port. |
| TD-012 | Medium | OpenAPI spectral/contract compatibility and Markdown/Mermaid link validation are not evidenced by this M9 run. | Developer experience TBD | CI runs Spectral, API compatibility, link checker and Mermaid render without warnings. |
| TD-013 | Medium | Idempotency-record cleanup is bounded on issuance, but no scheduled lifecycle cleanup has been configured. | Backend owner TBD | Volume-based decision and operational cleanup/retention evidence. |
| TD-014 | Medium | License has no owner decision; changelog and contributor guidance were absent before M9. | Repository owner | Select license or retain explicit proprietary/no-license status; maintain docs in releases. |
| TD-015 | Medium | Deployment traceability from Grafana request/job identifiers to optional LangSmith run references and full worker telemetry needs staging validation. | Observability owner TBD | Redacted end-to-end trace exercise and verified dashboards/alerts. |

## Known limitations

- The query path currently completes generation before emitting answer tokens; the proposed first-token SLO is at risk.
- Image-only PDF OCR is unsupported.
- RLS and migration evidence is local and synthetic; it is not a substitute for staging operational evidence.
- The product is English/Swahili UI with English-only document input per current owner decisions; model and provider behavior still require evaluation.
- No paid cloud resources or production data were used in M9.
