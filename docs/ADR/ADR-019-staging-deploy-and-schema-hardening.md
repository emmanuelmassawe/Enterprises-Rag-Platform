# ADR-019: Staging plan/apply separation and deployment wiring

- Status: Proposed; owner review pending
- Date: 2026-11-18

## Context

The staging workflow applied immediately after planning, preventing a separate review of the plan. Terraform plan files and provider output are sensitive, and the repository is public. The HCP Terraform backend supports saved plans and exposes a run-scoped apply API. Staging also has a `main` versus `master` branch mismatch. The Render migration URL was in an environment group shared by the API and worker, and Alloy creation required its own generated endpoint before Alloy existed. M9 found that Alembic metadata omitted an index present in the migration.

## Decisions

1. Split staging automation into `plan` and `apply` jobs. The plan job creates an HCP Terraform saved plan using `terraform plan -out`, stores only the HCP run ID and safe action counts as workflow outputs, and uploads a one-day summary with no resource names or values. The apply job uses the same HCP run ID and calls `POST /runs/:run_id/actions/apply` after the `staging` GitHub Environment protection gate. It never calculates a new plan or transfers a plan file. Keep the detailed plan in HCP Terraform. Configure required reviewers on the GitHub Environment. Since the repository is public, GitHub artifact visibility is public; the sanitized summary is informational, not a private/protected document.
2. Keep all workflows on `main`. Rename the local `master` branch and push `main`; then change GitHub's default branch and deployment branch policy before removing `master`.
3. Remove the owner connection URL from the shared API/worker environment group. Pass it only as the command-scoped `MIGRATION_DATABASE_URL` assignment for Render's API pre-deploy command. Render runs pre-deploy commands on a separate instance. State and Render service configuration still contain privileged migration connection material and require restricted access. Bootstrap remains a separate operator one-off and must not persist the migration URL on API/worker services.
4. Create Alloy when the API scrape target exists, leaving API OTLP export unset. After Render creates Alloy and exposes its private service address, supply the OTLP endpoint and update the API environment. This avoids a dependency on Alloy's future hostname while preserving same-region private networking.
5. Add the exact migration-created conversation index to SQLAlchemy metadata and retain `alembic check` in CI after a populated migration replay.
6. Use one Gemini API key for both embeddings and answer generation. It is provided as `staging.EMBEDDING_API_KEY` inside the protected GitHub Environment secret `TERRAFORM_APP_SECRETS_JSON`, then mapped to the Render API/worker environment group. There is no distinct generation API-key variable.

## Consequences and limits

- HCP Terraform retains the actual saved plan. GitHub carries only the run ID and redacted counts; the public artifact is not an access-control boundary.
- The staging Environment must have required reviewers configured. Because the plan job also needs its secrets, the Environment may request approval before planning and again before apply; the second gate is the apply authorization.
- The HCP token used by the apply job must be a user/team token with workspace apply permission. Organization tokens cannot invoke the apply endpoint.
- The Render pre-deploy command runs separately from the running API, but migration connection material is still part of protected Terraform/Render configuration. Terraform 1.17.2 formatting, backend-disabled initialization, and validation passed using pinned providers. A provider schema query was not completed because the remote backend configuration required initialization; the `pre_deploy_command` sensitivity attribute and live Render configuration remain unverified. No apply or live deployment was run.
- `alembic check` was added to CI. The new metadata correction passed locally against a fresh no-volume PostgreSQL database after a populated migration replay; CI has not yet run.
- Alloy's two-pass dependency is verified from the Terraform references and Render's documented same-region private service addressing; it has not been exercised against an owner Render account.

## Official documentation checked (2026-11-18)

- HCP Terraform [saved plan modes](https://developer.hashicorp.com/terraform/cloud-docs/workspaces/run/modes-and-options) document CLI `terraform plan -out`, no auto-apply for saved plans, and automatic discard when underlying state changes before confirmation.
- HCP Terraform [Runs API](https://developer.hashicorp.com/terraform/cloud-docs/api-docs/run) documents `POST /runs/:run_id/actions/apply`, the `202` queued response, and the requirement for a user or team token.
- GitHub [deployment environments](https://docs.github.com/en/actions/concepts/workflows-and-actions/deployment-environments) document reviewer gates and protected environment secrets; [environment management](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments) describes required reviewers.
- Render [deploys](https://render.com/docs/deploys#pre-deploy-command) document pre-deploy commands running on a separate instance. Render [private networking](https://render.com/docs/private-network) documents same-region private hostnames and where to find a private service's Service Address.
- The pinned Terraform provider is `render-oss/render` 1.9.1; its official [web service resource documentation](https://registry.terraform.io/providers/render-oss/render/1.9.1/docs/resources/web_service) documents `pre_deploy_command`. Exact local provider schema validation remains pending.
