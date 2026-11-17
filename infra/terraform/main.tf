locals {
  environments             = var.deploy_production ? toset(["staging", "production"]) : toset(["staging"])
  application_environments = var.deploy_application_services ? local.environments : toset([])
  grafana_environments     = var.deploy_grafana_resources ? toset(["staging"]) : toset([])
  telemetry_environments = toset([
    for environment in local.application_environments : environment
    if var.deploy_grafana_resources && contains(keys(var.alloy_otlp_endpoints), environment) && contains(keys(var.api_metrics_targets), environment)
  ])
  names = {
    for environment in local.environments : environment => "rag-${environment}"
  }
}

resource "render_project" "platform" {
  name = var.project_name
  environments = {
    staging = {
      name             = "staging"
      protected_status = "unprotected"
      network_isolated = true
    }
    production = {
      name             = "production"
      protected_status = "protected"
      network_isolated = true
    }
  }
}

resource "render_postgres" "platform" {
  for_each = local.environments

  name           = "${local.names[each.key]}-db"
  plan           = var.postgres_plan
  region         = var.region
  version        = "17"
  database_name  = "enterprise_rag"
  database_user  = "rag_migrator"
  environment_id = render_project.platform.environments[each.key].id

  # An empty allow list keeps access on the Render private network.
  ip_allow_list = []
}

resource "render_redis" "state" {
  for_each = local.environments

  name              = "${local.names[each.key]}-state"
  plan              = var.redis_plan
  region            = var.region
  max_memory_policy = "noeviction"
  persistence_mode  = "journal_snapshot"
  environment_id    = render_project.platform.environments[each.key].id
  ip_allow_list     = []
}

resource "render_redis" "cache" {
  for_each = local.environments

  name              = "${local.names[each.key]}-cache"
  plan              = var.redis_plan
  region            = var.region
  max_memory_policy = "allkeys_lru"
  persistence_mode  = "off"
  environment_id    = render_project.platform.environments[each.key].id
  ip_allow_list     = []
}

resource "render_env_group" "runtime" {
  for_each = local.application_environments

  name           = "${local.names[each.key]}-runtime"
  environment_id = render_project.platform.environments[each.key].id
  env_vars = {
    APP_ENV                     = { value = each.key }
    DATABASE_URL                = { value = var.database_runtime_urls[each.key] }
    MIGRATION_DATABASE_URL      = { value = replace(render_postgres.platform[each.key].connection_info.internal_connection_string, "postgresql://", "postgresql+asyncpg://") }
    REDIS_URL                   = { value = render_redis.state[each.key].connection_info.internal_connection_string }
    CACHE_REDIS_URL             = { value = render_redis.cache[each.key].connection_info.internal_connection_string }
    BLOB_BACKEND                = { value = "s3" }
    BLOB_BUCKET                 = { value = var.blob_bucket_names[each.key] }
    BLOB_ENDPOINT_URL           = { value = var.blob_endpoint_urls[each.key] }
    BLOB_REGION                 = { value = var.blob_regions[each.key] }
    BLOB_ACCESS_KEY_ID          = { value = var.app_secrets[each.key]["S3_ACCESS_KEY_ID"] }
    BLOB_SECRET_ACCESS_KEY      = { value = var.app_secrets[each.key]["S3_SECRET_ACCESS_KEY"] }
    EMBEDDING_API_KEY           = { value = var.app_secrets[each.key]["EMBEDDING_API_KEY"] }
    LANGSMITH_API_KEY           = { value = var.app_secrets[each.key]["LANGSMITH_API_KEY"] }
    LANGSMITH_TRACING           = { value = "true" }
    LANGSMITH_PROJECT           = { value = "rag-${each.key}" }
    LANGSMITH_ENDPOINT          = { value = try(var.langsmith_endpoints[each.key], "") }
    METRICS_SCRAPE_TOKEN        = { value = var.app_secrets[each.key]["METRICS_SCRAPE_TOKEN"] }
    OTEL_EXPORTER_OTLP_ENDPOINT = { value = try(var.alloy_otlp_endpoints[each.key], "") }
    OTEL_EXPORTER_OTLP_PROTOCOL = { value = "http/protobuf" }
  }
}

resource "render_web_service" "api" {
  for_each = local.application_environments

  name                       = "${local.names[each.key]}-api"
  plan                       = var.service_plan
  region                     = var.region
  environment_id             = render_project.platform.environments[each.key].id
  start_command              = "uvicorn rag.composition:app --app-dir src --host 0.0.0.0 --port 10000 --no-server-header"
  pre_deploy_command         = "alembic upgrade head"
  health_check_path          = "/readyz"
  max_shutdown_delay_seconds = 60
  num_instances              = 1
  runtime_source = {
    docker = {
      repo_url        = var.repository_url
      branch          = var.deploy_branch
      dockerfile_path = "./Dockerfile"
      context         = "."
      auto_deploy     = false
    }
  }
}

resource "render_web_service" "web" {
  for_each = var.deploy_web_service ? local.application_environments : toset([])

  name                       = "rag-web-${each.key}"
  plan                       = var.service_plan
  region                     = var.region
  environment_id             = render_project.platform.environments[each.key].id
  start_command              = "node server.js"
  health_check_path          = "/api/healthz"
  max_shutdown_delay_seconds = 30
  num_instances              = 1
  runtime_source = {
    docker = {
      repo_url        = var.repository_url
      branch          = var.deploy_branch
      dockerfile_path = "./web/Dockerfile"
      context         = "./web"
      auto_deploy     = false
    }
  }
  env_vars = {
    APP_ORIGIN                  = { value = var.web_origins[each.key] }
    RAG_API_URL                 = { value = var.web_rag_api_urls[each.key] }
    AUTH_URL                    = { value = var.web_origins[each.key] }
    AUTH_TRUST_HOST             = { value = "true" }
    AUTH_SECRET                 = { value = var.web_secrets[each.key]["AUTH_SECRET"] }
    AUTH_GOOGLE_ID              = { value = var.web_secrets[each.key]["AUTH_GOOGLE_ID"] }
    AUTH_GOOGLE_SECRET          = { value = var.web_secrets[each.key]["AUTH_GOOGLE_SECRET"] }
    WEB_IDENTITY_DIRECTORY_JSON = { value = var.web_secrets[each.key]["WEB_IDENTITY_DIRECTORY_JSON"] }
    FARO_COLLECTOR_URL          = { value = try(var.web_faro_collector_urls[each.key], "") }
    RELEASE_VERSION             = { value = var.release_version }
  }
}

resource "render_background_worker" "ingestion" {
  for_each = local.application_environments

  name                       = "${local.names[each.key]}-worker"
  plan                       = var.service_plan
  region                     = var.region
  environment_id             = render_project.platform.environments[each.key].id
  start_command              = "python -m rag.workers.ingestion"
  max_shutdown_delay_seconds = 60
  num_instances              = 1
  runtime_source = {
    docker = {
      repo_url        = var.repository_url
      branch          = var.deploy_branch
      dockerfile_path = "./Dockerfile"
      context         = "."
      auto_deploy     = false
    }
  }
}

resource "render_env_group_link" "api" {
  for_each = local.application_environments

  env_group_id = render_env_group.runtime[each.key].id
  service_ids  = [render_web_service.api[each.key].id]
}

resource "render_env_group_link" "worker" {
  for_each = local.application_environments

  env_group_id = render_env_group.runtime[each.key].id
  service_ids  = [render_background_worker.ingestion[each.key].id]
}

resource "render_private_service" "alloy" {
  for_each = local.telemetry_environments

  name           = "alloy-${each.key}"
  plan           = var.service_plan
  region         = var.region
  environment_id = render_project.platform.environments[each.key].id
  start_command  = "run --server.http.listen-addr=0.0.0.0:12345 /etc/alloy/config.alloy"
  runtime_source = {
    image = {
      image_url = var.alloy_image
    }
  }
  env_vars = {
    GRAFANA_PROMETHEUS_URL      = { value = var.grafana_prometheus_remote_write_url }
    GRAFANA_PROMETHEUS_USERNAME = { value = var.grafana_prometheus_username }
    GRAFANA_PROMETHEUS_PASSWORD = { value = var.grafana_prometheus_password }
    GRAFANA_LOKI_ENDPOINT       = { value = var.grafana_loki_endpoint }
    GRAFANA_LOKI_USERNAME       = { value = var.grafana_loki_username }
    GRAFANA_LOKI_PASSWORD       = { value = var.grafana_loki_password }
    GRAFANA_TEMPO_ENDPOINT      = { value = var.grafana_tempo_endpoint }
    GRAFANA_TEMPO_USERNAME      = { value = var.grafana_tempo_username }
    GRAFANA_TEMPO_PASSWORD      = { value = var.grafana_tempo_password }
    API_METRICS_TARGET          = { value = var.api_metrics_targets[each.key] }
    METRICS_SCRAPE_TOKEN        = { value = var.app_secrets[each.key]["METRICS_SCRAPE_TOKEN"] }
    DATABASE_URL                = { value = replace(var.database_runtime_urls[each.key], "postgresql+asyncpg://", "postgresql://") }
    STATE_REDIS_URL             = { value = render_redis.state[each.key].connection_info.internal_connection_string }
    CACHE_REDIS_URL             = { value = render_redis.cache[each.key].connection_info.internal_connection_string }
  }
  secret_files = {
    "/etc/alloy/config.alloy" = { content = file("${path.module}/../alloy/config.alloy") }
  }
}

resource "grafana_data_source" "prometheus" {
  for_each = local.grafana_environments

  type                     = "prometheus"
  name                     = "RAG ${each.key} metrics"
  url                      = var.grafana_prometheus_url
  access_mode              = "proxy"
  basic_auth_enabled       = true
  basic_auth_username      = var.grafana_prometheus_username
  secure_json_data_encoded = jsonencode({ basicAuthPassword = var.grafana_prometheus_password })
  is_default               = true
}

resource "grafana_dashboard" "operations" {
  for_each = local.grafana_environments

  config_json = file("${path.module}/../../observability/dashboards/rag-platform.json")
  overwrite   = true
}

resource "grafana_contact_point" "operations" {
  for_each = local.grafana_environments

  name = "RAG operations email"
  email {
    addresses = [var.grafana_alert_email]
  }
}

resource "grafana_folder" "operations" {
  for_each = local.grafana_environments

  title = "RAG Platform ${each.key} Operations"
}

resource "grafana_rule_group" "operations" {
  for_each = local.grafana_environments

  name             = "RAG platform service alerts"
  folder_uid       = grafana_folder.operations[each.key].uid
  interval_seconds = 60

  rule {
    name           = "RAG HTTP 5xx rate above 1 percent"
    condition      = "A"
    for            = "5m"
    no_data_state  = "NoData"
    exec_err_state = "Error"
    annotations = {
      summary     = "HTTP server error rate is above 1% for five minutes"
      runbook_url = "${var.repository_url}/blob/main/docs/RUNBOOK_AI_INCIDENTS.md"
    }
    labels = { severity = "ticket" }
    data {
      ref_id         = "A"
      datasource_uid = grafana_data_source.prometheus[each.key].uid
      relative_time_range {
        from = 300
        to   = 0
      }
      model = jsonencode({
        datasource    = { type = "prometheus", uid = grafana_data_source.prometheus[each.key].uid }
        editorMode    = "code"
        expr          = "sum(rate(rag_http_requests_total{status=~\"5..\"}[5m])) / clamp_min(sum(rate(rag_http_requests_total[5m])), 1)"
        instant       = true
        intervalMs    = 1000
        maxDataPoints = 43200
        refId         = "A"
      })
    }
  }

  rule {
    name           = "RAG AI canary leak detected"
    condition      = "A"
    for            = "0s"
    no_data_state  = "NoData"
    exec_err_state = "Error"
    annotations = {
      summary     = "A model output contained the system prompt canary"
      runbook_url = "${var.repository_url}/blob/main/docs/RUNBOOK_AI_INCIDENTS.md"
    }
    labels = { severity = "page" }
    data {
      ref_id         = "A"
      datasource_uid = grafana_data_source.prometheus[each.key].uid
      relative_time_range {
        from = 60
        to   = 0
      }
      model = jsonencode({
        datasource    = { type = "prometheus", uid = grafana_data_source.prometheus[each.key].uid }
        editorMode    = "code"
        expr          = "increase(rag_ai_canary_leaks_total[1m])"
        instant       = true
        intervalMs    = 1000
        maxDataPoints = 43200
        refId         = "A"
      })
    }
  }

  rule {
    name           = "RAG LangSmith export failures"
    condition      = "A"
    for            = "5m"
    no_data_state  = "NoData"
    exec_err_state = "Error"
    annotations = {
      summary     = "More than ten LangSmith export failures occurred in fifteen minutes"
      runbook_url = "${var.repository_url}/blob/main/docs/RUNBOOK_AI_INCIDENTS.md"
    }
    labels = { severity = "ticket" }
    data {
      ref_id         = "A"
      datasource_uid = grafana_data_source.prometheus[each.key].uid
      relative_time_range {
        from = 900
        to   = 0
      }
      model = jsonencode({
        datasource    = { type = "prometheus", uid = grafana_data_source.prometheus[each.key].uid }
        editorMode    = "code"
        expr          = "increase(rag_tracing_export_failures_total[15m]) > 10"
        instant       = true
        intervalMs    = 1000
        maxDataPoints = 43200
        refId         = "A"
      })
    }
  }
}

resource "grafana_notification_policy" "operations" {
  for_each = local.grafana_environments

  group_by        = ["alertname", "severity"]
  contact_point   = grafana_contact_point.operations[each.key].name
  group_wait      = "30s"
  group_interval  = "5m"
  repeat_interval = "4h"
}

output "render_environment_ids" {
  description = "Render project environment IDs."
  value       = { for name, environment in render_project.platform.environments : name => environment.id }
}

output "staging_internal_database_url" {
  description = "Sensitive migration connection URL; state and CLI output are sensitive."
  value       = render_postgres.platform["staging"].connection_info.internal_connection_string
  sensitive   = true
}

output "staging_state_redis_url" {
  description = "Sensitive internal Redis URL for durable job/control state."
  value       = render_redis.state["staging"].connection_info.internal_connection_string
  sensitive   = true
}

output "staging_cache_redis_url" {
  description = "Sensitive internal Redis URL for the evictable cache."
  value       = render_redis.cache["staging"].connection_info.internal_connection_string
  sensitive   = true
}
