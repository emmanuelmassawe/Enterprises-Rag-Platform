terraform {
  required_version = "= 1.17.2"

  required_providers {
    render = {
      source  = "render-oss/render"
      version = "= 1.9.1"
    }
    grafana = {
      source  = "grafana/grafana"
      version = "= 4.45.2"
    }
  }

  backend "remote" {}
}
