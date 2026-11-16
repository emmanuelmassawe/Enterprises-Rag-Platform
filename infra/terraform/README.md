# Render and Grafana infrastructure

Terraform is the source of truth for the Render project, staging resources, and Grafana Cloud provisioning. The repository is public; no credentials, rendered Terraform plans, or state files belong here.

## Prerequisites and state

- Terraform CLI **1.17.2**; provider versions are exact-pinned in `versions.tf`. Grafana Alloy v1.22.0 is pinned by immutable digest and its config passed the official image's validator.
- Owner-created HCP Terraform organization/workspace. The partial backend template is `envs/backend.hcl.example`; supply a local ignored backend file and authenticate with the CLI environment, never by committing a token.
- Protected `staging` and `production` GitHub Environments with Render/Grafana and app-provider values stored as environment secrets/variables.
- Owner selection of region and paid datastore plans before the foundation apply. API service plans, S3-compatible bucket, Grafana Cloud stack, alert recipient, and staging embedding/LangSmith keys are needed only for their later rollout stages.

Initialize with a local untracked backend configuration file, then run `terraform init -backend-config=envs/backend.hcl`. CI initializes the configured remote backend. Terraform remote state must be access controlled and encrypted; no local backend is approved for shared/deploy use.

## Plan and apply policy

`make tf-plan` is the local plan entry point once HCP Terraform state and protected inputs are available. `make tf-apply` intentionally refuses. Pull-request CI runs formatting and validation without provider credentials. Apply is performed by the protected CI workflow, only for staging in M7. Production resources are disabled by default (`deploy_production = false`) and production applies are outside this milestone and forbidden from local shells.

The protected manual workflow supports a three-stage setup so generated Render hostnames and dependent credentials do not block the initial resources:

1. Leave `deploy_application_services` and `deploy_grafana_resources` false. Choose the region and paid Postgres/Redis plans. This creates the isolated Render project, staging Postgres, and two Redis instances.
2. Create the least-privilege `rag_runtime` Postgres role, provision an S3-compatible bucket, select a service plan, and configure staging app secrets. Re-run with `deploy_application_services` true. This deploys the API and worker.
3. After Render exposes the API and Alloy private hostnames, configure the protected Grafana stack values, `api_metrics_targets`, and `alloy_otlp_endpoints`. Re-run with `deploy_grafana_resources` true. This provisions Grafana resources and Alloy telemetry collection when both target maps include staging.

Each dispatch produces and applies a saved plan only on `main` inside the protected `staging` environment. Review the inputs and protected environment configuration before dispatch; workflow logs withhold provider plan/apply output because this repository is public.

Terraform state contains sensitive connection values even when outputs and variables are marked sensitive. Treat remote state and saved plans as secrets. Do not publish a plan file or its output in public logs/artifacts.

## Configuration

Copy `envs/staging.tfvars.example` to an ignored local `staging.tfvars` only if needed. Provide sensitive inputs with `TF_VAR_*` environment variables in the protected staging environment. Required staging inputs are declared in `variables.tf`; blank owner choices intentionally have no silent defaults.

`database_runtime_urls.staging` must use the separately provisioned least-privilege `rag_runtime` DB role. The Render Postgres owner connection is used only for the migration command. Do not point the application URL at the owner/migration role. S3-compatible storage remains owner-provisioned because this milestone does not select an account or incur bucket costs.

## Network and telemetry

All resources use one owner-selected Render region and the staging environment is network-isolated. Postgres and Redis have empty public IP allow lists. `rag-state` uses `noeviction` with journal snapshots; `rag-cache` uses `allkeys_lru` and persistence off. The ingestion process remains a Render background worker. Background workers cannot receive private inbound requests, so Alloy does not attempt to scrape the worker endpoint; worker metrics are an M7 verification gap pending a push/OTLP metrics path or a separately reviewed private metrics service design.

Alloy receives OTLP on 4318 and forwards metrics/logs/traces using the configured Grafana Cloud credentials. Application telemetry must be configured to export only redacted fields. The API OTLP endpoint and API scrape target are explicit protected inputs because Render allocates a generated private hostname; fill them only after the services exist. No real telemetry flow is claimed until a staging smoke check succeeds. Background-worker metrics are not scraped: Render background workers cannot accept inbound traffic, and the current worker exposes only a pull-based listener. A push/OTLP metrics path or a separately reviewed private metrics-service design is required to close this gap.

Grafana dashboard JSON is sourced from `observability/dashboards/rag-platform.json`; the provider manages a Prometheus datasource, dashboard, folder, three alert rules, the owner-addressed email contact point and root notification policy. Alert delivery and query behavior still need a staging smoke exercise against the owner's Grafana Cloud stack. Existing local Prometheus rules remain in `observability/alerts.yml` as the local profile's source.

## Migration and deployment notes

The API uses `/readyz` for Render deployment health checks and runs `alembic upgrade head` as its pre-deploy command. The Dockerfile is the already-reviewed application image source. The runtime-role bootstrap is a staging prerequisite: create `rag_runtime` with least privilege before providing its URL to Terraform. `pgvector` is enabled by the existing Alembic migration. `rag-web` is deliberately deferred to Milestone 8 because the Next.js BFF does not exist yet.

## Official documentation checked

- Render Terraform provider 1.9.1: [provider](https://registry.terraform.io/providers/render-oss/render/latest), [`render_web_service`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/web_service), [`render_postgres`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/postgres), [`render_redis`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/redis), [`render_background_worker`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/background_worker), [`render_env_group`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/env_group); project schema is present in [provider source docs](https://github.com/render-oss/terraform-provider-render/blob/main/docs/resources/project.md) although Registry's latest-version page currently says that page is missing.
- [Render private networking](https://render.com/docs/private-network) and [private services](https://render.com/docs/private-services): resources must share a region; workers cannot receive private-network requests; Alloy is a private service.
- [Render PostgreSQL extensions](https://render.com/docs/postgresql-extensions): pgvector is enabled in the database via SQL migration.
- Grafana Terraform provider 4.45.2: [provider](https://registry.terraform.io/providers/grafana/grafana/latest), [`grafana_data_source`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/data_source), [`grafana_dashboard`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/dashboard), [`grafana_folder`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/folder), [`grafana_rule_group`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/rule_group), [`grafana_contact_point`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/contact_point), and [`grafana_notification_policy`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/notification_policy).
- Grafana Alloy [Postgres exporter](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.postgres/), [Redis exporter](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.redis/), [OTLP HTTP exporter](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.otlphttp/), [basic auth](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.auth.basic/), and [Loki OTLP ingestion](https://grafana.com/docs/loki/latest/send-data/otel/).
- [LangSmith tracing configuration](https://docs.langchain.com/langsmith/trace-with-langchain) documents the environment variables passed by the app group and region-specific endpoint selection.
- [pgvector upstream](https://github.com/pgvector/pgvector) documents extension initialization with `CREATE EXTENSION vector;`.
- [Terraform remote backend](https://developer.hashicorp.com/terraform/language/backend/remote): shared state backend and locking.

These docs were checked on 2026-11-16. Provider plan/apply remains the final schema and capability check before any resource is created.
