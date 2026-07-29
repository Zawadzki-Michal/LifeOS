# The lifeos.michalzawadzki.dev A record — hand-created on 2026-07-28 (see
# deploy/README.md), adopted under Terraform here via `terraform import`
# rather than left as a manual, undocumented one-off like the VM/network
# provisioning is (see main.tf's comment on why *those* stay manual: a
# DNS record has none of the "botched apply against the only node" risk
# that justifies leaving the VM alone).
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

resource "cloudflare_record" "lifeos" {
  zone_id = var.cloudflare_zone_id
  name    = "lifeos"
  type    = "A"
  content = "141.253.108.155" # the Oracle VM's public IP — same host as KUBE_API_SERVER, different port
  ttl     = 1                 # 1 = "Automatic" in the dashboard
  proxied = false             # DNS-only/grey-cloud, deliberately — see values-oracle.yaml's ingress.hosts comment
}
