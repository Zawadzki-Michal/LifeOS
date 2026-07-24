# Passed directly as helm provider attributes (no kubeconfig file) — locally
# via terraform.tfvars (gitignored), in CI via -var from GitHub secrets
# (KUBE_API_SERVER/KUBE_TOKEN/KUBE_CA_CERT). Token-based auth against the
# lifeos-deployer ServiceAccount (deploy/lifeos-deployer-rbac.yaml), not
# client-cert auth from the admin kubeconfig — same scoped credential locally
# and in CI, nothing broader used just because a run happens to be local.

variable "kube_host" {
  type        = string
  description = "Kubernetes API server URL, e.g. https://<oracle-vm-ip>:6443"
}

variable "kube_token" {
  type        = string
  description = "Bearer token for the lifeos-deployer ServiceAccount"
  sensitive   = true
}

variable "kube_cluster_ca_certificate" {
  type        = string
  description = "Base64-encoded cluster CA certificate (from the ServiceAccount token Secret's ca.crt, or the kubeconfig's certificate-authority-data)"
  sensitive   = true
}

variable "image_tag" {
  type        = string
  description = "GHCR image tag to deploy (git SHA or run number from CI) — overrides values.yaml's local-import tag, since Terraform's deploy path always pulls from the registry, never the node's local containerd image store."
}

variable "image_repository" {
  type    = string
  default = "ghcr.io/zawadzki-michal/lifeos-app"
}

variable "monitoring_enabled" {
  type        = bool
  default     = true
  description = "True by default since 2026-07-24 — kube-prometheus-stack is healthy and grafana-lifeos-pg/grafana_ro exist on the Oracle cluster now. Override to false only if standing up a fresh cluster from scratch before those prerequisites are in place."
}
