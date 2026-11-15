# ADR-010: Render deployment managed by Terraform

- Status: Proposed, pending owner approval
- Date: 2026-11-15

## Context

BRIEF targets Render and Terraform. Resource names, argument support and plan limits must be checked instead of inferred.

## Decision

Use official `render-oss/render` provider as Terraform source of truth, pinned to a reviewed version; provision API web service, worker, BFF web service, Postgres, two Key Value stores, private telemetry collector and environment-specific resources. Keep state remote and locked. Plans are reviewable artifacts; production apply occurs only through approved protected CI workflow. Use Render health check paths for web services and TCP health for private services unless official docs add support.

## Evidence checked (checked 2026-11-15)

- Terraform Registry current [Render provider](https://registry.terraform.io/providers/render-oss/render/latest) surfaced version 1.9.1. Its [`render_web_service`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/web_service) schema documents `render_web_service`, region values, `health_check_path`, `pre_deploy_command`, `max_shutdown_delay_seconds`, instance count/autoscaling, sensitive env values and runtime source structures.
- Registry [`render_postgres`](https://registry.terraform.io/providers/render-oss/render/latest/docs/resources/postgres) documents Render Postgres resource fields including region, version, IP allow list and high availability. The official [provider page](https://registry.terraform.io/providers/render-oss/render/latest) is maintained independently from Render's service documentation; re-check exact version schema before implementation.
- Registry [`render_keyvalue` v1.6.0](https://registry.terraform.io/providers/render-oss/render/1.6.0/docs/resources/keyvalue) documents the key-value resource and eviction policy. Latest-provider URL for that resource did not resolve in the current registry lookup, so confirm resource naming/schema against the pinned provider before writing Terraform.
- Render [health checks docs](https://render.com/docs/health-checks) state HTTP path checks apply to web services; private services only support default TCP checks. Health checks occur every few seconds, fail newly deployed instances closed, and can restart persistently unhealthy instances.
- Render [service types](https://render.com/docs/service-types) documents web/private services, workers, Postgres and Key Value; [Postgres backups](https://render.com/docs/postgresql-backups) state paid Postgres has PITR with recovery windows dependent on workspace plan (3 days Hobby, 7 days Pro or higher in current docs).
- Render [Key Value docs](https://render.com/docs/key-value) state paid instances support persistence; eviction policy options include `noeviction` and `allkeys-lru`.
- Official `render-oss/render` Registry docs expose web service plan identifiers such as `starter`, `standard`, `pro`, `pro_plus`, `pro_max`, `pro_ultra`; pricing and suitability are owner budget decisions, not selected here.

## Consequences

- Infrastructure is reviewable and repeatable, while provider limitations remain explicit.
- Render plans/capabilities can change; Terraform plan must be checked in staging before any apply.
- Localhost is treated as a local development origin; production domain remains unselected.

