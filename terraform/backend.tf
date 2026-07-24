# Remote state on OCI Object Storage via its S3-compatible API — required
# because CI (GitHub-hosted runners) is ephemeral; local state would look
# empty on every run and try to reinstall/duplicate everything. No native
# state locking on this backend — mitigated by the deploy workflow's
# `concurrency: { group: lifeos-deploy, cancel-in-progress: false }` guard
# instead. Never run a manual `apply` from a laptop while CI might also be
# running one.
#
# Bucket/namespace were created once by hand (see deploy/README.md's
# Terraform section) — not managed by this Terraform itself, same
# chicken-and-egg reasoning as not Terraform-managing the VM.
#
# Auth: access_key/secret_key are deliberately absent here — supplied via
# the AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars at init/plan/apply
# time (an OCI "Customer Secret Key", not the API signing key used for the
# oci CLI). Never put them in this file, it's committed to git.
terraform {
  backend "s3" {
    bucket = "lifeos-terraform-state"
    key    = "lifeos/terraform.tfstate"
    region = "eu-paris-1"
    endpoints = {
      s3 = "https://axgcvmrkeepf.compat.objectstorage.eu-paris-1.oraclecloud.com"
    }
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_requesting_account_id  = true
    skip_metadata_api_check     = true
    skip_s3_checksum            = true
    force_path_style            = true
  }
}
