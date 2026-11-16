# ADR-017: Render staging infrastructure and Grafana Cloud provisioning

- Status: Proposed implementation, staging apply pending owner inputs
- Date: 2026-11-16
- Supersedes: the outdated Render Key Value resource-name statement in ADR-010. ADR-010's Terraform-managed Render/Grafana direction remains valid.

## Context

Milestone 7 provisions the API, ingestion worker, Postgres, separate durable/control and evictable Redis-compatible stores, Alloy, and Grafana Cloud resources. The repository is public. The owner has not selected a Render region, service or datastore plans, budgets, object-store account, Grafana stack, state workspace, alert recipient, or staging provider credentials. Render private networking is regional. Production applies must remain gated and must never run from a local shell.

## Decision

- Pin Terraform 1.17.2, Render provider 1.9.1 and Grafana provider 4.45.2; commit the Terraform dependency lock file. Pin Grafana Alloy v1.22.0 by its official image digest, which passed `alloy validate` with synthetic endpoints.
- Use `render_project` with isolated `staging` and `production` environments. Deploy staging resources by default; create production resources only when the protected workflow explicitly opts in.
- Provision Render Postgres with vector extension enabled by the existing Alembic migration. Use the migration URL only for the pre-deploy migration and require a separate `rag_runtime` URL for the application.
- Use the current provider resource `render_redis` twice. `rag-state` gets `noeviction` and journal snapshots; `rag-cache` gets `allkeys_lru` and persistence off. Do not add public IP allow-list entries.
- Deploy the queue consumer as a Render background worker. Render documents that background workers cannot receive inbound private-network traffic; therefore Alloy does not scrape the worker's pull-only metrics endpoint. Worker metrics ingestion remains open pending a push/OTLP metric exporter or an approved private metrics-service redesign.
- Run Alloy as a private service. API/Alloy private hostnames are owner/environment inputs after a first staging service exists; no generated hostname is guessed. Alloy receives OTLP and remote-writes Prometheus metrics using sensitive Grafana credentials.
- Provision the Prometheus query datasource, existing operations dashboard JSON, a folder, three alert rules derived from `observability/alerts.yml`, an owner-addressed contact point, and a root notification policy. Alert delivery and query semantics still require a smoke exercise against the owner's Grafana Cloud stack.
- Use an HCP Terraform remote backend with locking, configured outside git. Terraform state and saved plans can contain connection credentials and are treated as secrets. PR workflows run static checks without provider secrets; applies run only in protected CI environments.
- Split staging provisioning into three explicit protected workflow stages: Render database/cache foundation; API/worker after the runtime role, bucket and app secrets exist; Grafana resources and Alloy after account credentials and Render private hostnames are known. Both service/Grafana toggles default off, avoiding a dependency cycle on generated endpoints.
- Defer `rag-web` to M8 because the Next.js BFF does not yet exist. Keep bucket creation outside this change because provider/account, retention, encryption and budget are undecided.

## NFR mapping

| NFR | Decision that supports it | Remaining evidence |
|---|---|---|
| NFR-AVAIL-001, NFR-REL-001 | Readiness-gated API deploy; durable queue Redis; cache eviction isolated from queue state; same-region private dependencies | Staging deploy, dependency fault tests, availability SLI |
| NFR-DR-001 | Paid Postgres plan is owner-selected; state Redis persistence is on; Terraform state is remote and locked | Backup plan confirmation and measured restore drill/RPO/RTO |
| NFR-SEC-003 | Sensitive variables/env-group values; private networking; no public datastore allow-list entries; protected CI applies | Secret scan, Render plan review, TLS and access review |
| NFR-PRIV-001, NFR-OBS-001 | Alloy receives app telemetry; Grafana credentials remain server-side; existing app exporter is metadata-redacted | App log export integration, worker metrics path, staging export/redaction and alert exercise |
| NFR-OPS-001 | Version-pinned providers, `fmt`/`validate`, staged resources and `/readyz` deploy health check | tflint/checkov workflow, staging plan/apply, smoke and rollback rehearsal |
| NFR-COST-001 | No plan/region defaults and production creation disabled by default | Owner budget, selected plans, spend cap and budget alerts |

## Consequences

Terraform captures repeatable staging infrastructure without committing credentials or selecting a cost-bearing plan on the owner's behalf. The configuration is structurally valid against the pinned provider schemas. No paid resources have been created. The foundation stage still needs owner accounts, Render region/datastore plan choices, and remote state. Later stages need the runtime database role URL, object-store configuration, app secrets, and Grafana credentials/targets. Telemetry is not complete: the current worker metric endpoint is pull-only and Render workers cannot be scraped; logs from the current application go to stdout and are not yet exported over OTLP.

## Official documentation checked 2026-11-16

- [Render Terraform provider 1.9.1](https://registry.terraform.io/providers/render-oss/render/latest) and provider schemas for [`render_web_service`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/web_service), [`render_postgres`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/postgres), [`render_redis`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/redis), [`render_background_worker`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/background_worker), and [`render_env_group`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/env_group).
- [`render_project` provider source documentation](https://github.com/render-oss/terraform-provider-render/blob/main/docs/resources/project.md); the Terraform Registry's versioned `render_project` page currently returns “page not found”, so source docs are used and the discrepancy is recorded.
- Render [private networking](https://render.com/docs/private-network) and [private services](https://render.com/docs/private-services) document same-region connectivity, private service ingress, and the lack of inbound networking for workers.
- Render [Postgres extensions](https://render.com/docs/postgresql-extensions) documents enabling extensions using SQL.
- The upstream [pgvector project](https://github.com/pgvector/pgvector) documents `CREATE EXTENSION vector;` and Postgres vector operations; Render's extension list is the deployment availability check.
- Grafana Terraform provider 4.45.2 [provider page](https://registry.terraform.io/providers/grafana/grafana/latest), [`grafana_data_source`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/data_source), [`grafana_dashboard`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/dashboard), [`grafana_folder`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/folder), [`grafana_rule_group`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/rule_group), [`grafana_contact_point`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/contact_point), and [`grafana_notification_policy`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/notification_policy).
- Grafana Alloy [`prometheus.exporter.postgres`](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.postgres/), [`prometheus.exporter.redis`](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.redis/), [`otelcol.exporter.otlphttp`](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.otlphttp/), and [`otelcol.auth.basic`](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.auth.basic/) docs were checked for exporter arguments and authentication. [Loki OTLP ingestion](https://grafana.com/docs/loki/latest/send-data/otel/) requires the `/otlp` endpoint and OTLP HTTP exporter.
- Official Alloy `v1.22.0` container digest `sha256:9acc2529bc1edb7f5b2bd801dd8334ebc80c158e3a9e5526ecd7c9a273d43189` was pulled and ran `alloy validate` successfully with synthetic-only endpoints/credentials.
- LangSmith's [manual tracing environment setup](https://docs.langchain.com/langsmith/trace-with-langchain) documents `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and region-specific `LANGSMITH_ENDPOINT`; the selected region remains an owner decision.
- [Terraform remote backend documentation](https://developer.hashicorp.com/terraform/language/backend/remote) documents shared remote state and locking.
