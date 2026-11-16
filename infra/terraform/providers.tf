provider "render" {
  api_key  = var.render_api_key
  owner_id = var.render_owner_id
}

provider "grafana" {
  url  = var.grafana_url
  auth = var.grafana_auth_token
}
