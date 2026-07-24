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

  # NOTE: monitoring.enabled is true in values.yaml by default, which
  # requires the kube-prometheus-stack release below (for the ServiceMonitor
  # CRD) to exist first, AND requires the grafana-lifeos-pg Secret +
  # grafana_ro Postgres role to already exist in the monitoring namespace
  # (created once by hand, same pattern as lifeos-secrets — see
  # deploy/README.md's Phase 4 section). Until both of those are done on
  # this cluster, override with `-var monitoring_enabled=false` or the
  # kube-prometheus-stack release + lifeos app pod will fail to come up.
  set {
    name  = "monitoring.enabled"
    value = var.monitoring_enabled
  }

  # Deliberately NOT depends_on kube_prometheus_stack: monitoring_enabled
  # defaults false precisely so this release doesn't need that one to
  # succeed first. Add the dependency back once monitoring_enabled flips to
  # true for good (the ServiceMonitor CRD must exist by then regardless).
  depends_on = [helm_release.cert_manager_config]
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

  # Grafana's grafana-lifeos-pg Secret + the grafana_ro Postgres role don't
  # exist on this cluster yet (created once by hand, same pattern as
  # lifeos-secrets — see deploy/README.md's Phase 4 section) — until they
  # do, Grafana crash-loops waiting on that secretKeyRef. wait = false so
  # that doesn't fail the whole apply; flip back to the default (true) once
  # the prerequisite is set up here too.
  wait = false
}
