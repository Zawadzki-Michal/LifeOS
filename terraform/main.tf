resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  namespace        = "cert-manager"
  create_namespace = true

  set {
    name  = "crds.enabled"
    value = "true"
  }
}

resource "helm_release" "cert_manager_config" {
  name      = "cert-manager-config"
  chart     = "${path.module}/../deploy/cert-manager-config"
  namespace = "default"

  depends_on = [helm_release.cert_manager]
}

resource "helm_release" "lifeos" {
  name             = "lifeos"
  chart            = "${path.module}/../deploy/lifeos"
  namespace        = "lifeos"
  create_namespace = true

  values = [
    file("${path.module}/../deploy/lifeos/values.yaml"),
    file("${path.module}/../deploy/lifeos/values-oracle.yaml"),
  ]

  # A migration-bearing deploy legitimately crash-loops until the
  # lifeos-migrate Job is run by hand (see deploy/README.md) — waiting here
  # would make every apply that includes a new migration time out.
  wait = false

  # Terraform's deploy path always pulls from GHCR, never the node's local
  # containerd image store — overrides values.yaml's local-import defaults
  # (repository: lifeos-app, pullPolicy: Never), which stay correct for the
  # manual/local helm upgrade flow used for quick debugging.
  set {
    name  = "image.repository"
    value = var.image_repository
  }
  set {
    name  = "image.tag"
    value = var.image_tag
  }
  set {
    name  = "image.pullPolicy"
    value = "IfNotPresent"
  }

  set {
    name  = "monitoring.enabled"
    value = var.monitoring_enabled
  }

  # kube-prometheus-stack's ServiceMonitor CRD must exist before this
  # release's app-servicemonitor.yaml template can apply.
  depends_on = [helm_release.cert_manager_config, helm_release.kube_prometheus_stack]
}

resource "helm_release" "kube_prometheus_stack" {
  name             = "kube-prometheus-stack"
  repository       = "https://prometheus-community.github.io/helm-charts"
  chart            = "kube-prometheus-stack"
  namespace        = "monitoring"
  create_namespace = true

  values = [
    file("${path.module}/../deploy/kube-prometheus-stack-values.yaml"),
    file("${path.module}/../deploy/kube-prometheus-stack-values-oracle.yaml"),
  ]

  # grafana-lifeos-pg Secret + grafana_ro Postgres role created by hand on
  # 2026-07-24 (see deploy/README.md Phase 4) — Grafana is healthy now, so
  # this waits for real again instead of silently succeeding broken.
}
