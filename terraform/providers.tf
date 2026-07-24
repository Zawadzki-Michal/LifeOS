provider "helm" {
  kubernetes {
    host                   = var.kube_host
    token                  = var.kube_token
    cluster_ca_certificate = base64decode(var.kube_cluster_ca_certificate)
  }
}
