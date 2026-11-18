# Render and Grafana infrastructure

Terraform is the source of truth for the Render project, staging resources, and Grafana Cloud provisioning. The repository is public; no credentials, rendered Terraform plans, or state files belong here.

## Prerequisites and state

- Terraform CLI **1.17.2**; provider versions are exact-pinned in `versions.tf`. Grafana Alloy v1.22.0 is pinned by immutable digest and its config passed the official image's validator.
- Owner-created HCP Terraform organization/workspace. The partial backend template is `envs/backend.hcl.example`; supply a local ignored backend file and authenticate with the CLI environment, never by committing a token.
- Protected `staging` and `production` GitHub Environments with Render/Grafana and app-provider values stored as environment secrets/variables.
- Owner selection of region and paid datastore plans before the foundation apply. API service plans, S3-compatible bucket, Grafana Cloud stack, alert recipient, and staging embedding/LangSmith keys are needed only for their later rollout stages.

Initialize with a local untracked backend configuration file, then run `terraform init -backend-config=envs/backend.hcl`. CI initializes the configured remote backend. Terraform remote state must be access controlled and encrypted; no local backend is approved for shared/deploy use.

## Plan and apply policy

`make tf-plan` is the local plan entry point once HCP Terraform state and protected inputs are available. `make tf-apply` intentionally refuses. Pull-request CI runs formatting and validation without provider credentials. The staging workflow now has separate `plan` and `apply` jobs. The plan job creates an HCP Terraform saved plan and uploads only a counts/commit/run-ID summary; it never applies. The apply job references that same HCP run and queues its apply only after the `staging` GitHub Environment's reviewer gate passes. Configure required reviewers on that Environment. Since this repository is public, GitHub artifacts are not confidential: the uploaded summary contains no resource addresses or values, and the actual plan remains in access-controlled HCP Terraform. The HCP API token must be a user or team token authorized to apply workspace runs; an organization token cannot call the apply endpoint. Production resources are disabled by default (`deploy_production = false`) and production applies are outside this milestone and forbidden from local shells.

The workflow targets `main`, but the checked-out repository currently has local `master` tracking `origin/master`, and the remote has no `main` branch. From this checkout, run these commands to create and track `main` without deleting `master`:

```sh
git fetch origin
git switch master
git branch -m main
git push -u origin main
```

Then change the repository's default branch to `main` in GitHub Settings → Branches, and set the staging Environment's deployment branch policy to `main`. Verify locally with `git branch -vv` and `git ls-remote --heads origin main master`. Do not delete `origin/master` until GitHub confirms `main` is the default and branch protections/workflows are retargeted.

The protected manual workflow supports staged setup so generated Render hostnames and dependent credentials do not block the initial resources:

1. Leave `deploy_application_services` and `deploy_grafana_resources` false. Choose the region and paid Postgres/Redis plans. This creates the isolated Render project, staging Postgres, and two Redis instances.
2. Create the least-privilege `rag_runtime` Postgres role, provision an S3-compatible bucket, select a service plan, and configure staging app secrets. Re-run with `deploy_application_services` true. This deploys the API and worker.
3. To resolve Alloy's generated-hostname dependency in two passes, first configure the protected Grafana stack values and `api_metrics_targets` after the API hostname exists, leave `alloy_otlp_endpoints` empty, and run with `deploy_grafana_resources` true. This creates the Grafana resources and Alloy private service while API OTLP export remains unset. Read Alloy's internal Service Address from Render's Connect view, then set `TERRAFORM_ALLOY_OTLP_ENDPOINTS_JSON` to the staging OTLP HTTP URL using that private hostname and port 4318; run the same inputs again. This updates the API env group to send telemetry to Alloy. Alloy creation is gated by the API scrape target, not its own not-yet-existing hostname.
4. After Google OAuth, the public web origin, an API URL reachable from the web service, and the protected identity directory are configured, re-run with both `deploy_application_services` and `deploy_web_service` true. Set the `TERRAFORM_WEB_ORIGINS_JSON`, `TERRAFORM_WEB_RAG_API_URLS_JSON`, optional `TERRAFORM_WEB_FARO_URLS_JSON`, and protected `TERRAFORM_WEB_SECRETS_JSON` environment values. The web service receives only its own Auth.js/OIDC/identity/Faro configuration, not the API and worker environment group.

Each dispatch creates a saved plan only on `main`. When that plan contains changes, the apply job queues that exact HCP run only after the `staging` Environment reviewer gate passes. Review the HCP plan before approving apply; workflow logs withhold provider plan/apply output because this repository is public.

Terraform state contains sensitive connection values even when outputs and variables are marked sensitive. Treat remote state and saved plans as secrets. Do not publish a plan file or its output in public logs/artifacts. HCP Terraform retains the saved plan and controls access to its details; the GitHub artifact is intentionally limited to commit, run ID, aggregate add/change/destroy counts and whether approval is needed. Because the repository is public, anyone with repository read access can see that summary.

## Configuration

Copy `envs/staging.tfvars.example` to an ignored local `staging.tfvars` only if needed. Provide sensitive inputs with `TF_VAR_*` environment variables in the protected staging environment. Required staging inputs are declared in `variables.tf`; blank owner choices intentionally have no silent defaults.

`database_runtime_urls.staging` must use the separately provisioned least-privilege `rag_runtime` DB role. The Render Postgres owner connection is interpolated into the API's `pre_deploy_command` as a command-scoped `MIGRATION_DATABASE_URL`; it is not present in the shared API/worker environment group or in the running API/worker process environments. The pre-deploy command runs on a separate Render instance. Keep Terraform state, HCP plan access, and Render service configuration access restricted because the command and state depend on the privileged connection. Do not point the application URL at the owner/migration role. The separate first-tenant bootstrap is an operator one-off and must receive the migration URL only for that invocation; do not add it back to a persistent service env group. S3-compatible storage remains owner-provisioned because this milestone does not select an account or incur bucket costs.

The query generation adapter uses the same Gemini credential as the embedding adapter. There is no separate generation API-key setting in the code. For staging, provide `EMBEDDING_API_KEY` inside the `staging` object of the protected GitHub Environment secret `TERRAFORM_APP_SECRETS_JSON`; Terraform writes it as `EMBEDDING_API_KEY` in the Render API/worker runtime group. The API uses it for both query embeddings and answer generation; the worker uses it for ingestion embeddings. Generation is enabled by default. Setting `GENERATION_ENABLED=false` disables answer generation but does not remove the key requirement for embedding.

## Network and telemetry

All resources use one owner-selected Render region and the staging environment is network-isolated. Postgres and Redis have empty public IP allow lists. `rag-state` uses `noeviction` with journal snapshots; `rag-cache` uses `allkeys_lru` and persistence off. The ingestion process remains a Render background worker. Background workers cannot receive private inbound requests, so Alloy does not attempt to scrape the worker endpoint; worker metrics are an M7 verification gap pending a push/OTLP metrics path or a separately reviewed private metrics service design.

Alloy receives OTLP on 4318 and forwards metrics/logs/traces using the configured Grafana Cloud credentials. Application telemetry must be configured to export only redacted fields. The API OTLP endpoint and API scrape target are explicit protected inputs because Render allocates a generated private hostname; fill them only after the services exist. No real telemetry flow is claimed until a staging smoke check succeeds. Background-worker metrics are not scraped: Render background workers cannot accept inbound traffic, and the current worker exposes only a pull-based listener. A push/OTLP metrics path or a separately reviewed private metrics-service design is required to close this gap.

Grafana dashboard JSON is sourced from `observability/dashboards/rag-platform.json`; the provider manages a Prometheus datasource, dashboard, folder, three alert rules, the owner-addressed email contact point and root notification policy. Alert delivery and query behavior still need a staging smoke exercise against the owner's Grafana Cloud stack. Existing local Prometheus rules remain in `observability/alerts.yml` as the local profile's source.

## Migration and deployment notes

The API uses `/readyz` for Render deployment health checks and runs `alembic upgrade head` as its pre-deploy command. The API Dockerfile is the application image source; `web/Dockerfile` builds the separate Next.js standalone BFF from `./web` and serves `/api/healthz`. The runtime-role bootstrap is a staging prerequisite: create `rag_runtime` with least privilege before providing its URL to Terraform. `pgvector` is enabled by the existing Alembic migration. The web Render service is opt-in and has not been deployed.

## Official documentation checked

- Render Terraform provider 1.9.1: [provider](https://registry.terraform.io/providers/render-oss/render/latest), [`render_web_service`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/web_service), [`render_postgres`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/postgres), [`render_redis`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/redis), [`render_background_worker`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/background_worker), [`render_env_group`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/env_group); project schema is present in [provider source docs](https://github.com/render-oss/terraform-provider-render/blob/main/docs/resources/project.md) although Registry's latest-version page currently says that page is missing.
- [Render private networking](https://render.com/docs/private-network) and [private services](https://render.com/docs/private-services): resources must share a region; workers cannot receive private-network requests; Alloy is a private service.
- [Render PostgreSQL extensions](https://render.com/docs/postgresql-extensions): pgvector is enabled in the database via SQL migration.
- Grafana Terraform provider 4.45.2: [provider](https://registry.terraform.io/providers/grafana/grafana/latest), [`grafana_data_source`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/data_source), [`grafana_dashboard`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/dashboard), [`grafana_folder`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/folder), [`grafana_rule_group`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/rule_group), [`grafana_contact_point`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/contact_point), and [`grafana_notification_policy`](https://registry.terraform.io/providers/grafana/grafana/latest/docs/resources/notification_policy).
- Grafana Alloy [Postgres exporter](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.postgres/), [Redis exporter](https://grafana.com/docs/alloy/latest/reference/components/prometheus/prometheus.exporter.redis/), [OTLP HTTP exporter](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.exporter.otlphttp/), [basic auth](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.auth.basic/), and [Loki OTLP ingestion](https://grafana.com/docs/loki/latest/send-data/otel/).
- [LangSmith tracing configuration](https://docs.langchain.com/langsmith/trace-with-langchain) documents the environment variables passed by the app group and region-specific endpoint selection.
- [pgvector upstream](https://github.com/pgvector/pgvector) documents extension initialization with `CREATE EXTENSION vector;`.
- [Terraform remote backend](https://developer.hashicorp.com/terraform/language/backend/remote): shared state backend and locking.
- [HCP Terraform saved plans](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/run/modes-and-options) describe `terraform plan -out` saved-plan runs, no auto-apply, and automatic stale-plan discard; [HCP Terraform Runs API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/run) documents `POST /runs/:run_id/actions/apply`, the 202 queued response, and the user/team-token requirement.
- Render [pre-deploy commands](https://render.com/docs/deploys#pre-deploy-command) run on a separate instance before deployment; Render [private networking](https://render.com/docs/private-network) documents same-region service hostnames and the private service address shown in the dashboard.
- GitHub [deployment environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments) gate jobs and release environment secrets only after configured protection rules pass. GitHub [environment management](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) documents required reviewer configuration.

These docs were checked on 2026-11-18. Provider plan/apply remains the final schema and capability check before any resource is created. No Terraform plan or apply was run for this change.
