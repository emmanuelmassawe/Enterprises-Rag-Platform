variable "render_api_key" {
  description = "Render API key for the target workspace. Supply via a protected environment variable."
  type        = string
  sensitive   = true
}

variable "render_owner_id" {
  description = "Render workspace owner ID."
  type        = string
  sensitive   = true
}

variable "grafana_url" {
  description = "Grafana Cloud stack URL."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_auth_token" {
  description = "Grafana Cloud service account token with dashboard and alert provisioning permissions."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_prometheus_url" {
  description = "Grafana Cloud Prometheus query endpoint URL for the Grafana datasource."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_prometheus_remote_write_url" {
  description = "Grafana Cloud Prometheus remote-write endpoint URL (typically the tenant push endpoint)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_prometheus_username" {
  description = "Grafana Cloud Prometheus instance ID used for basic authentication."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_prometheus_password" {
  description = "Grafana Cloud Prometheus write token."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_alert_email" {
  description = "Owner-provided alert recipient; no address is assumed."
  type        = string
  sensitive   = true
  default     = ""
}

variable "project_name" {
  description = "Human-readable Render project name."
  type        = string
  default     = "enterprise-rag-platform"
}

variable "repository_url" {
  description = "HTTPS URL of the public source repository."
  type        = string
  default     = "https://github.com/emmanuelmassawe/Enterprises-Rag-Platform"
  validation {
    condition     = can(regex("^https://github\\.com/[^/]+/[^/]+$", var.repository_url))
    error_message = "repository_url must be an HTTPS GitHub repository URL."
  }
}

variable "deploy_branch" {
  description = "Protected branch deployed by Render."
  type        = string
  default     = "main"
}

variable "region" {
  description = "Render region selected by the owner. Required because private networking is regional."
  type        = string
  validation {
    condition     = contains(["frankfurt", "ohio", "oregon", "singapore", "virginia"], var.region)
    error_message = "region must be a currently supported Render region. Confirm the choice with the owner."
  }
}

variable "service_plan" {
  description = "Paid Render compute plan selected after budget review."
  type        = string
  default     = ""
}

variable "postgres_plan" {
  description = "Paid Render Postgres plan selected after budget and backup review."
  type        = string
}

variable "redis_plan" {
  description = "Paid Render Key Value plan selected after budget review."
  type        = string
  validation {
    condition     = contains(["starter", "standard", "pro", "pro_plus"], var.redis_plan)
    error_message = "redis_plan must be a supported paid Render Redis plan."
  }
}

variable "database_runtime_urls" {
  description = "Environment -> least-privilege rag_runtime PostgreSQL URL. Supply only after the runtime role is provisioned; URLs are sensitive."
  type        = map(string)
  sensitive   = true
  default     = {}
  validation {
    condition     = !var.deploy_application_services || (contains(keys(var.database_runtime_urls), "staging") && can(regex("^postgresql\\+asyncpg://", var.database_runtime_urls["staging"])))
    error_message = "When application services are enabled, a postgresql+asyncpg:// staging runtime URL for rag_runtime is required."
  }
}

variable "alloy_otlp_endpoints" {
  description = "Environment -> Alloy OTLP HTTP URL using the Render private hostname, supplied after Alloy has been created and its private address is known."
  type        = map(string)
  default     = {}
}

variable "api_metrics_targets" {
  description = "Environment -> Render API private hostname:port for Alloy Prometheus scraping."
  type        = map(string)
  default     = {}
}

variable "app_secrets" {
  description = "Environment-scoped secret values for app/worker configuration; no secret defaults are permitted."
  type        = map(map(string))
  sensitive   = true
  default     = {}
  validation {
    condition = !var.deploy_application_services || alltrue([
      for environment in ["staging"] :
      contains(try(keys(var.app_secrets[environment]), []), "EMBEDDING_API_KEY") &&
      contains(try(keys(var.app_secrets[environment]), []), "S3_ACCESS_KEY_ID") &&
      contains(try(keys(var.app_secrets[environment]), []), "S3_SECRET_ACCESS_KEY") &&
      contains(try(keys(var.app_secrets[environment]), []), "LANGSMITH_API_KEY") &&
      contains(try(keys(var.app_secrets[environment]), []), "METRICS_SCRAPE_TOKEN")
    ])
    error_message = "Staging embedding, S3, LangSmith, and metrics-scrape secrets are required."
  }
}

variable "langsmith_endpoints" {
  description = "Optional environment-scoped LangSmith API endpoint. Leave unset for the account's default region; configure the official regional URL when required."
  type        = map(string)
  sensitive   = true
  default     = {}
}

variable "blob_bucket_names" {
  description = "Environment-scoped S3-compatible bucket names provisioned outside this Render stack."
  type        = map(string)
  default     = {}
  validation {
    condition     = !var.deploy_application_services || contains(keys(var.blob_bucket_names), "staging")
    error_message = "A staging S3-compatible bucket name is required when application services are enabled."
  }
}

variable "blob_endpoint_urls" {
  description = "Environment-scoped S3-compatible endpoint URLs."
  type        = map(string)
  default     = {}
  validation {
    condition     = !var.deploy_application_services || contains(keys(var.blob_endpoint_urls), "staging")
    error_message = "A staging S3-compatible endpoint is required when application services are enabled."
  }
}

variable "blob_regions" {
  description = "Environment-scoped S3-compatible regions."
  type        = map(string)
  default     = {}
  validation {
    condition     = !var.deploy_application_services || contains(keys(var.blob_regions), "staging")
    error_message = "A staging S3-compatible region is required when application services are enabled."
  }
}

variable "grafana_loki_endpoint" {
  description = "Grafana Cloud Loki push endpoint (verified/configured by the owner)."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_loki_username" {
  description = "Grafana Cloud Loki instance ID."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_loki_password" {
  description = "Grafana Cloud Loki push token."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_tempo_endpoint" {
  description = "Grafana Cloud Tempo OTLP/HTTP endpoint."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_tempo_username" {
  description = "Grafana Cloud Tempo instance ID."
  type        = string
  sensitive   = true
  default     = ""
}

variable "grafana_tempo_password" {
  description = "Grafana Cloud Tempo push token."
  type        = string
  sensitive   = true
  default     = ""
}

variable "alloy_image" {
  description = "Grafana Alloy v1.22.0 image, pinned to the immutable official image digest validated in this milestone."
  type        = string
  default     = "grafana/alloy@sha256:9acc2529bc1edb7f5b2bd801dd8334ebc80c158e3a9e5526ecd7c9a273d43189"
  validation {
    condition     = can(regex("^grafana/alloy@sha256:[0-9a-f]{64}$", var.alloy_image))
    error_message = "alloy_image must use grafana/alloy@sha256:<64 lowercase hex digits>."
  }
}

variable "deploy_production" {
  description = "Create production resources only during an explicitly approved protected-environment rollout."
  type        = bool
  default     = false
}

variable "deploy_application_services" {
  description = "Enable the API and worker after the separate rag_runtime role and application secrets are ready. Keep false for the initial Render datastore foundation apply."
  type        = bool
  default     = false
  validation {
    condition     = !var.deploy_application_services || contains(["starter", "standard", "pro", "pro_plus", "pro_max", "pro_ultra"], var.service_plan)
    error_message = "Choose a supported paid Render service_plan before enabling the API or worker."
  }
}

variable "deploy_web_service" {
  description = "Create the separate Next.js BFF service after staging API, Google OAuth and identity mappings are configured."
  type        = bool
  default     = false
  validation {
    condition     = !var.deploy_web_service || var.deploy_application_services
    error_message = "deploy_application_services must be true before enabling the web BFF."
  }
}

variable "web_origins" {
  description = "Environment-scoped public HTTPS origin for the web UI, for example the Render web hostname."
  type        = map(string)
  default     = {}
  validation {
    condition = !var.deploy_web_service || alltrue([
      for environment in(var.deploy_production ? ["staging", "production"] : ["staging"]) :
      contains(keys(var.web_origins), environment) && can(regex("^https://", try(var.web_origins[environment], "")))
    ])
    error_message = "An HTTPS origin is required for each enabled web environment."
  }
}

variable "web_rag_api_urls" {
  description = "Environment-scoped RAG API base URL reachable from the web service; use the same-region private URL where available."
  type        = map(string)
  default     = {}
  validation {
    condition = !var.deploy_web_service || alltrue([
      for environment in(var.deploy_production ? ["staging", "production"] : ["staging"]) :
      contains(keys(var.web_rag_api_urls), environment) && can(regex("^https?://", try(var.web_rag_api_urls[environment], "")))
    ])
    error_message = "A reachable RAG API URL is required for each enabled web environment."
  }
}

variable "web_faro_collector_urls" {
  description = "Optional environment-scoped Faro collector URL; leave empty until the owner Grafana Cloud receiver is configured."
  type        = map(string)
  default     = {}
}

variable "web_secrets" {
  description = "Environment-scoped web BFF secrets: AUTH_SECRET, AUTH_GOOGLE_ID, AUTH_GOOGLE_SECRET and WEB_IDENTITY_DIRECTORY_JSON."
  type        = map(map(string))
  sensitive   = true
  default     = {}
  validation {
    condition = !var.deploy_web_service || alltrue(flatten([
      for environment in(var.deploy_production ? ["staging", "production"] : ["staging"]) : [
        for key in ["AUTH_SECRET", "AUTH_GOOGLE_ID", "AUTH_GOOGLE_SECRET", "WEB_IDENTITY_DIRECTORY_JSON"] :
        contains(try(keys(var.web_secrets[environment]), []), key) && length(trimspace(try(var.web_secrets[environment][key], ""))) > 0
      ]
    ]))
    error_message = "Auth.js secret, Google OAuth credentials, and identity directory are required for each enabled web environment."
  }
}

variable "release_version" {
  description = "Non-secret release identifier injected into runtime telemetry."
  type        = string
  default     = "unknown"
}

variable "deploy_grafana_resources" {
  description = "Enable Grafana Cloud datasources, dashboard, alert rules, contact point and notification policy once the owner stack credentials are ready."
  type        = bool
  default     = false
  validation {
    condition = !var.deploy_grafana_resources || alltrue([
      for value in [
        var.grafana_url,
        var.grafana_auth_token,
        var.grafana_prometheus_url,
        var.grafana_prometheus_remote_write_url,
        var.grafana_prometheus_username,
        var.grafana_prometheus_password,
        var.grafana_alert_email,
        var.grafana_loki_endpoint,
        var.grafana_loki_username,
        var.grafana_loki_password,
        var.grafana_tempo_endpoint,
        var.grafana_tempo_username,
        var.grafana_tempo_password,
      ] : length(trimspace(value)) > 0
    ])
    error_message = "Grafana URL, tokens, endpoints, usernames, and alert email must be configured when Grafana resources are enabled."
  }
}
