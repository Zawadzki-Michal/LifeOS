# LifeOS deployment runbook

**Current production**: the **Oracle Cloud cluster** (`141.253.108.155`) —
real traffic, real data, Terraform-managed, full CI/CD (push to `master`
auto-builds/deploys). Reachable at both **`https://lifeos.michalzawadzki.dev`**
(the real domain, added 2026-07-28 — Cloudflare DNS-only A record, not
proxied) and **`https://141-253-108-155.sslip.io`** (the original address,
kept working as a fallback, not replaced). One Ingress/cert-manager SAN
certificate covers both hostnames (`ingress.hosts` in `values-oracle.yaml`).
See **"v3 — Oracle Cloud cluster"** below for everything specific to it
(Terraform, CI/CD, Tailscale, rclone backups).

**Cold-standby**: the original **WSL2 cluster** (this Windows machine,
`Ubuntu-24.04` distro) — kept running deliberately, not decommissioned yet,
as a rollback point while the Oracle cluster proves itself over time. Real
traffic was cut over away from it (Telegram webhook, Google OAuth) but its
own data/services still run. The rest of this document (everything before
the "v3" section) is its setup history and remains accurate for it.

docker-compose remains the local dev workflow on both — this is only ever
the always-on deployment target, never touched for day-to-day development.

## One-time cluster bootstrap (already done on this machine — WSL2)

## One-time cluster bootstrap (already done on this machine)

1. Install a dedicated WSL2 distro, without launching it (`--install -d`
   alone triggers an interactive username/password wizard on first launch
   that can't be scripted; `--no-launch` skips straight past that — every
   subsequent command targets it as `root` explicitly instead of a default
   user):
   ```
   wsl --install -d Ubuntu-24.04 --no-launch
   ```
2. Install k3s inside it, without the bundled Traefik (ngrok stays the
   external-exposure path, so an unused ingress controller is just more
   surface area):
   ```
   wsl -d Ubuntu-24.04 -u root -- sh -c 'curl -sfL https://get.k3s.io | INSTALL_K3S_EXEC="--disable=traefik" sh -'
   ```
   This installs k3s as a systemd service (Ubuntu 24.04's WSL image ships
   with systemd enabled by default) — it starts automatically whenever this
   WSL distro is running.
3. Copy the kubeconfig out for Windows-side `kubectl`:
   ```
   wsl -d Ubuntu-24.04 -u root -- cat /etc/rancher/k3s/k3s.yaml > $env:USERPROFILE\.kube\config
   ```
   **Note:** WSL2 localhost-forwarding did not reach k3s's port 6443 on this
   machine (connection refused on `127.0.0.1:6443` even though k3s listens
   on all interfaces inside the VM) — the kubeconfig's `server:` field was
   rewritten to the distro's actual IP instead (see step 4's IP — it's the
   same address family). If `kubectl` ever stops connecting, re-check the
   distro's current IP (`wsl -d Ubuntu-24.04 -u root -- ip -4 addr show eth0`)
   and update `server:` in `%USERPROFILE%\.kube\config` accordingly — this
   IP can shift across WSL network resets, same caveat as step 4.
4. Find the WSL2 gateway IP (this is "the Windows host" as seen from
   pods — needed for the Ollama Service below, and can change across WSL2
   restarts/updates, so re-check if Ollama connectivity ever breaks):
   ```
   wsl -d Ubuntu-24.04 -u root -- sh -c "ip route show | grep default"
   ```
   Put that IP in `deploy/lifeos/values.yaml`'s `ollama.hostIP` (currently
   `172.27.176.1` on this machine).
5. **Ollama must listen on more than just `127.0.0.1`, or it's unreachable
   from WSL2 no matter what DNS/Service tricks are used** — this was the
   actual blocker discovered during bootstrap, more specific than "figure
   out the networking path" (Docker Desktop's `host.docker.internal` magic
   that made this a non-issue in compose doesn't exist for plain k3s). Fixed
   by setting `OLLAMA_HOST=0.0.0.0:11434` as a persistent User environment
   variable and restarting the Ollama process. Tradeoff accepted
   deliberately: Ollama's unauthenticated API is now reachable from the
   whole home LAN, not just WSL2/k3s — acceptable on a trusted home network,
   but worth knowing if the network ever changes. (The scoped alternative —
   binding only to the WSL vEthernet adapter IP — was considered and
   rejected because that IP has the same restart-can-change fragility as
   the gateway IP above, and this way there's only one IP to ever re-check,
   not two.)

6. **WSL2 silently tears down a distro's network path ~10s after the last
   attached `wsl.exe` process exits** — even with `vmIdleTimeout=-1` in
   `.wslconfig` (that setting governs the shared utility VM, not each
   distro's own per-instance lifecycle). Discovered live: `kubectl` worked
   immediately after any `wsl -d ... --` command, then started failing with
   "connection refused" within ~10 seconds of no further WSL activity —
   this would have made the "always-on cluster" goal quietly false. Fixed
   with a permanent keep-alive session:
   ```
   wsl -d Ubuntu-24.04 -u root -- sleep infinity
   ```
   started detached/hidden and left running continuously. **This needs to
   survive reboots via a Scheduled Task — not yet set up, since registering
   one requires elevated/interactive access this environment didn't have.**
   Set it up once, from a normal (non-admin) PowerShell window:
   ```powershell
   $action = New-ScheduledTaskAction -Execute "wsl.exe" -Argument "-d Ubuntu-24.04 -u root -- sleep infinity"
   $trigger = New-ScheduledTaskTrigger -AtLogOn
   $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
   Register-ScheduledTask -TaskName "LifeOS-k3s-keepalive" -Action $action -Trigger $trigger -Settings $settings -Description "Keeps a WSL2 session attached to the k3s distro so it doesn't idle out."
   ```
   Until this is registered, the keep-alive session only lasts until the
   next full reboot/logoff — re-run the `wsl -d ... sleep infinity` command
   (in the background) after any restart in the meantime.

## Building and loading the app image

No registry — k3s imports a locally-built image directly:
```
docker build -t lifeos-app:<tag> .
docker save lifeos-app:<tag> | wsl -d Ubuntu-24.04 -u root -- k3s ctr images import -
```
Bump `<tag>` (a date or short git SHA — never reuse `dev`/`latest` for a real
deploy) in `deploy/lifeos/values.yaml`'s `image.tag`, then `helm upgrade`.
`imagePullPolicy: Never` means a forgotten tag bump silently keeps the old
image running — always check `image.tag` before `helm upgrade`.

## Secrets

Never templated in the chart. One-time setup:
```
cp .env.k8s-secrets.example .env.k8s-secrets   # fill in real values, never commit
kubectl create namespace lifeos
kubectl create secret generic lifeos-secrets -n lifeos --from-env-file=.env.k8s-secrets
```
To rotate/update: `kubectl delete secret lifeos-secrets -n lifeos && kubectl create secret ...` again, then restart the app pod (`kubectl rollout restart deployment/lifeos-app -n lifeos`) to pick up the change.

## Install / upgrade

```
helm upgrade --install lifeos ./deploy/lifeos -n lifeos --create-namespace
```

## First-time data

Phase 1 uses fresh/throwaway data, not the real Postgres data — that
migration is Phase 2. A fresh `pgvector/pgvector` database doesn't have the
`vector` extension enabled by default (this bit us live — several migrations
create `VECTOR(...)` columns and fail with `type "vector" does not exist`
otherwise); enable it once per fresh database, then run migrations via the
manual-trigger `lifeos-migrate` CronJob (not run automatically on every
deploy, matching the existing "run alembic by hand" habit from compose):
```
kubectl exec -n lifeos postgres-0 -- psql -U lifeos -d lifeos -c "CREATE EXTENSION IF NOT EXISTS vector;"
kubectl create job --from=cronjob/lifeos-migrate lifeos-migrate-manual -n lifeos
kubectl logs -n lifeos job/lifeos-migrate-manual   # confirm it reached the latest revision
kubectl delete job -n lifeos lifeos-migrate-manual
```
The app pod's `wait-for-postgres` init container only waits for Postgres to
accept TCP connections, not for migrations to exist — it will crash-loop
with `relation "user" does not exist` until the job above has run at least
once; `kubectl delete pod` on it afterward to force an immediate retry
instead of waiting out the backoff.

## Verifying Phase 1

The app image has no `curl` (`python:3.12-slim`, never installed) — use
Python instead for any in-pod HTTP check:
```
kubectl get pods -n lifeos                                  # all Running
kubectl exec -n lifeos deploy/lifeos-app -- python -c "import urllib.request; print(urllib.request.urlopen('http://ollama:11434/api/tags', timeout=5).read()[:200])"
kubectl port-forward -n lifeos svc/lifeos-app 8000:8000      # then curl/open http://localhost:8000, /health, /api/auth/me (expect 401 unauthenticated)
```

**Verified working on this machine** (Phase 1 complete): all 3 pods
Running/Ready, Ollama reachable from the app pod via the in-cluster
`ollama` Service, `/health` returns `{"status":"ok"}`, and the webapp static
assets + `/api/auth/me` both respond correctly over `kubectl port-forward`.

## Resource ceiling (`.wslconfig`)

`%UserProfile%\.wslconfig` caps WSL2's memory/CPU so gaming keeps headroom —
see that file for the current values and rationale.

## Phase 2 — real data cutover (done on this machine)

```
docker compose stop app                                        # avoid a mid-write dump
docker compose exec -T postgres pg_dump -Fc -U lifeos -d lifeos > lifeos-cutover.dump
docker compose start app                                        # back up in seconds

# release the k3s app's DB connections before dropping its throwaway database
kubectl scale deployment lifeos-app -n lifeos --replicas=0
kubectl exec -n lifeos postgres-0 -- psql -U lifeos -d postgres -c "DROP DATABASE lifeos;"
kubectl exec -n lifeos postgres-0 -- psql -U lifeos -d postgres -c "CREATE DATABASE lifeos OWNER lifeos;"
kubectl exec -n lifeos postgres-0 -- psql -U lifeos -d lifeos -c "CREATE EXTENSION IF NOT EXISTS vector;"

# `kubectl cp` on Windows: cd into the dump's directory first and pass a
# *relative* local path — an absolute Windows path like C:\Users\... has
# its own colon, which kubectl cp's src/dest parser confuses with the
# namespace/pod:path syntax ("one of src or dest must be a local file
# specification"). MSYS_NO_PATHCONV=1 is also needed so Git Bash doesn't
# rewrite the in-container /tmp/... path into a bogus Windows one.
cd "$(dirname lifeos-cutover.dump)"
MSYS_NO_PATHCONV=1 kubectl cp lifeos-cutover.dump lifeos/postgres-0:/tmp/lifeos-cutover.dump
MSYS_NO_PATHCONV=1 kubectl exec -n lifeos postgres-0 -- pg_restore -U lifeos -d lifeos --no-owner --no-privileges /tmp/lifeos-cutover.dump

kubectl scale deployment lifeos-app -n lifeos --replicas=1
```
Verified: row counts (`user`, `chat_session`, `chat_message`, `expense`)
matched exactly between the compose source and the k3s restore, and the app
started cleanly against the restored data.

**Rollback**: the compose stack and its volumes were left fully intact —
`docker compose up -d` still brings back pre-cutover state if k3s has early
problems. The two data stores diverge from the moment of cutover onward, so
this is "return to pre-cutover state," not a seamless resume.

## Backups

`postgres-backup` CronJob (daily 4am, 14-day retention, dedicated PVC
separate from `postgres-data`) — trigger manually anytime:
```
kubectl create job --from=cronjob/postgres-backup postgres-backup-manual -n lifeos
kubectl logs -n lifeos job/postgres-backup-manual   # confirms the dump filename written
kubectl delete job -n lifeos postgres-backup-manual
```
**Restore-tested and verified** (not just "a file exists"): restored a real
dump into a disposable Postgres in a throwaway pod (mounting the
`postgres-backup` PVC read-only) and confirmed row counts matched the real
data exactly.

**Off-box copy** — the backup PVC lives on the same physical disk as
`postgres-data`, so on its own it only protects against logical
corruption/bad migrations, not disk failure. Rather than standing up
`rclone` + API credentials for B2/a NAS, the CronJob copies each dump to
`/offbox`, a `hostPath` volume pointed at
`/mnt/c/Users/mzzaw/Documents/GoogleDrive/lifeos-backups` — a WSL2 DrvFs
path into the ordinary Windows folder the GoogleDrive desktop client
already syncs. No extra credentials or tooling needed; the already-running
Drive client is what actually gets the file off-box from there.

- Toggle: `backup.offBox.enabled` in `values.yaml` (default `true`). Set to
  `false` if the hostPath ever stops being valid (different machine,
  renamed folder, Drive client removed) rather than let the job fail.
- Same `retentionDays` prune applies to both `/backups` (the PVC) and
  `/offbox` (the GoogleDrive folder).
- Best-effort: if the copy step fails (e.g. path momentarily unavailable),
  the job logs a warning but still succeeds — the local PVC dump is the
  primary backup and is never blocked by the off-box leg.
- **Not verified**: whether the Drive client actually uploads a given file
  is outside what a Linux container can observe — check
  `C:\Users\mzzaw\Documents\GoogleDrive\lifeos-backups` directly (or
  drive.google.com) after a manual run to confirm sync status.

## Phase 3 — n8n, adminer, ngrok (done on this machine)

**n8n data migration** — n8n is SQLite-backed, not Postgres, so it moves as
a raw file copy via a throwaway pod mounting its PVC:
```
docker compose stop n8n
docker run --rm -v lifeos_n8n_data:/data -v "$USERPROFILE/AppData/Local/Temp":/out alpine sh -c "tar czf /out/n8n-data.tar.gz -C /data ."
kubectl scale deployment n8n -n lifeos --replicas=0
# apply a throwaway pod mounting the n8n-data PVC (see git history for the exact manifest used),
# kubectl cp the tarball in, tar xzf it over the fresh empty data, delete the throwaway pod
kubectl scale deployment n8n -n lifeos --replicas=1
```
Verified: real `database.sqlite` (1.4MB, matching the compose source
byte-for-byte) present post-migration, n8n UI reachable and responding.

**Two real bugs hit deploying n8n, both now fixed in the chart:**
1. **`enableServiceLinks` collision** — Kubernetes auto-injects legacy
   Docker-links-style env vars for every Service in the namespace (e.g. a
   Service named `n8n` gets you `N8N_PORT=tcp://10.x.x.x:5678` injected
   into every pod). n8n's own app code reads `N8N_PORT` expecting a plain
   port number and crashed on the URL form. Fixed with
   `enableServiceLinks: false` on every Deployment/StatefulSet in the chart
   (not just n8n's — pre-empting the same class of bug anywhere else a
   Service name happens to match an app's own env var convention).
2. **OOM at the initial 512Mi memory limit** — n8n's Node.js process needs
   real headroom beyond its own baseline usage; it JS-heap-OOM'd repeatedly
   until raised to `limits.memory: 1Gi` in `values.yaml`.

**Adminer**: verified reachable via `kubectl port-forward -n lifeos svc/adminer 8081:8080` — no other changes from the plan's design (ClusterIP-only, no tunnel exposure).

**ngrok cutover — real external traffic moved to k3s**:
```
docker compose stop ngrok   # frees the static domain — both can't hold it at once
# flip ngrok.enabled: true in values.yaml, then:
helm upgrade lifeos ./deploy/lifeos -n lifeos
```
Verified against the live public domain (no re-registration needed
anywhere — Telegram's webhook URL and the Google OAuth redirect URI both
point at the same ngrok static domain, unchanged; only what's *behind* it
changed):
- `GET https://<domain>/health` → `{"status":"ok"}`
- `POST https://<domain>/telegram/webhook` → reachable, handled cleanly
- `GET https://<domain>/api/auth/login` → correct 307 redirect to Google
  with the right `client_id`/`redirect_uri`
- Telegram's `getWebhookInfo` confirmed the registered URL needed no change

**Not verified by me, needs a real human check**: an actual Telegram
message round-trip and clicking through the real Google OAuth consent
screen both need real device/account interaction — do these yourself to
fully close out Phase 3.

**Post-cutover cleanup**: stopped the compose `app` container specifically
(not the whole stack) — with ngrok now pointed at k3s, a still-running
compose `app` would independently fire its own copy of the daily scheduler
broadcasts (`app/scheduler.py`'s in-process loops), double-sending
Telegram/webapp messages. `postgres`/`redis`/`n8n`/`adminer` compose
containers stay up as an inert rollback fallback per the plan's Phase 5
guidance — only `app` (the thing that actively *does* something) needed
stopping.

## Phase 4 — kube-prometheus-stack + Grafana (done on this machine)

**Install** (separate Helm release, prometheus-community's upstream chart —
never folded into the `lifeos` chart):
```
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack -n monitoring --create-namespace -f deploy/kube-prometheus-stack-values.yaml
```
`deploy/kube-prometheus-stack-values.yaml` sizes everything down from chart
defaults (7d Prometheus retention, modest memory limits throughout, no
Grafana persistence) for a single-node homelab sharing a 12GB WSL2 ceiling
with everything else.

**A third WSL2-specific gotcha, on top of the two from earlier phases**:
node-exporter's DaemonSet pod crashed with `path "/" is mounted on "/" but
it is not a shared or slave mount` — it needs shared mount propagation on
the host root to do its host-path bind mounts, and WSL2's rootfs defaults
to private. Fixed with:
```
wsl -d Ubuntu-24.04 -u root -- mount --make-rshared /
```
**Not persistent** — this needs re-running after every WSL2 restart (same
category as the keep-alive session and Ollama's `OLLAMA_HOST` binding).
Worth folding into the same startup script/Scheduled Task as the keep-alive
session eventually, rather than tracking three separate manual steps.

**App metrics**: added `prometheus-fastapi-instrumentator` (`requirements.txt`,
`app/main.py` — registered *before* the `StaticFiles` catch-all mount at
`/`, since a `Mount("/")` registered first would otherwise shadow `/metrics`
in Starlette's route matching order) plus a `ServiceMonitor` in the chart
(`deploy/lifeos/templates/app-servicemonitor.yaml`, gated by
`monitoring.enabled`). Requires the `release: kube-prometheus-stack` label
— that release's Prometheus only discovers ServiceMonitors carrying its own
release label by default. Verified: target shows in Prometheus with an
empty `lastError` and a fresh `lastScrape` timestamp.

**Ollama latency histogram**: `ollama_request_duration_seconds` in
`app/ollama_client.py`, labeled by `endpoint`/`model`, wrapping the actual
Ollama HTTP calls in `generate()`/`chat()`/`chat_with_tools()` (not
`list_models()` — that's just a health check, not real work). Directly
targets the GPU-contention symptom from earlier this session (a running
game making an Ollama request look "stuck") — this turns that into a
visible p99 spike instead of a mystery. **Verification note**: Prometheus
metrics are per-process — a `kubectl exec` one-off script does NOT share
the live server's in-memory registry, so a real datapoint only shows up
from an actual request through the running server (a real Telegram/webapp
message) — folds into the same "needs a human" item as Phase 3's Telegram
round-trip check.

**OpenRouter spend history** — didn't exist before Phase 4 (verified via
`app/routers/usage.py`: entirely live-fetched from OpenRouter's own API,
nothing persisted). Added as a small feature, not just observability
wiring:
- New `openrouter_usage_log` table (`app/models.py`'s `OpenRouterUsageLog`,
  migration `b7e1a2f9c4d3`) — `Numeric(12,6)` for cost, not this file's
  usual `(12,2)`, since OpenRouter's per-call USD cost is routinely a
  fraction of a cent.
- `app/openrouter_client.py::chat()` gained a `source` param and logs every
  call (best-effort — a logging failure never breaks an already-successful
  reply). All three call sites updated: `chat_service.py` (`"chat_cloud"`),
  `reasoning_client.py`'s `consult()` (`"consult_advanced_model"`) and
  `analyze_image()` (`"analyze_image"`).
- OpenRouter's response really does include real per-call `cost` in
  `usage.cost` — confirmed live (`$0.000059` for a trivial GPT-5 Nano call),
  no extra request flag needed.
- **Grafana data source, least-privilege**: a dedicated `grafana_ro`
  Postgres role, `GRANT SELECT` on `openrouter_usage_log` only — not the
  app's own `lifeos` superuser. Its password lives in a Secret created
  directly in the `monitoring` namespace (`grafana-lifeos-pg` —
  `lifeos-secrets` in the `lifeos` namespace can't be referenced
  cross-namespace, and mirroring it over would just be broader access than
  Grafana actually needs), wired into the datasource's `secureJsonData` via
  Grafana's `$__env{...}` provisioning-time expansion (`envValueFrom` in
  `deploy/kube-prometheus-stack-values.yaml` — not the plain `env:` field,
  which only takes literal strings, not `secretKeyRef`s).
- **Verified working end-to-end**, not just "provisioned": queried the data
  source directly via Grafana's `/api/ds/query` and got back the real test
  row (model, source, cost) written moments earlier by a live OpenRouter
  call.

**Grafana access**:
```
kubectl get secret -n monitoring kube-prometheus-stack-grafana -o jsonpath="{.data.admin-password}" | base64 -d
kubectl port-forward -n monitoring svc/kube-prometheus-stack-grafana 3000:80   # then http://localhost:3000, user "admin"
```
No account, no signup — entirely self-hosted inside the cluster.

## v3 — Oracle Cloud cluster (done on 141.253.108.155)

Same chart, second cluster: a `VM.Standard.E3.Flex` (2 OCPU/16GB, Ubuntu
24.04) — E4.Flex wasn't available in this tenancy/region, E3 is the direct
equivalent at the same per-OCPU/GB price. WSL2 stays up as a cold-standby
rollback point until the full decommission (see the plan's Phase 7). Bare
k3s bootstrap (Traefik **enabled** this time — no ngrok, real Ingress
instead):
```bash
ssh -i ~/.ssh/lifeos_oracle ubuntu@<vm-ip> "curl -sfL https://get.k3s.io | sudo sh -"
```
**Two firewall layers, both need opening for 80/443/6443** — the OCI
Security List (console) *and* the OS's own iptables (Oracle's Ubuntu images
ship a default-REJECT INPUT chain independent of the Security List):
```bash
ssh -i ~/.ssh/lifeos_oracle ubuntu@<vm-ip> 'sudo iptables -I INPUT 5 -p tcp -m state --state NEW -m tcp --dport 80 -j ACCEPT; sudo iptables -I INPUT 6 -p tcp -m state --state NEW -m tcp --dport 443 -j ACCEPT; sudo iptables -I INPUT 7 -p tcp -m state --state NEW -m tcp --dport 6443 -j ACCEPT; sudo netfilter-persistent save'
```
k3s's self-signed serving cert doesn't include the public IP as a SAN by
default — `kubectl` from outside the node fails TLS verification until you
add it and restart:
```bash
ssh -i ~/.ssh/lifeos_oracle ubuntu@<vm-ip> 'printf "tls-san:\n  - <vm-ip>\n" | sudo tee /etc/rancher/k3s/config.yaml && sudo systemctl restart k3s'
```
Kubeconfig: same `/etc/rancher/k3s/k3s.yaml` pull as WSL2, `server:` rewritten
to the public IP instead of `127.0.0.1` — saved separately as
`~/.kube/oracle-config` (Windows path `C:\Users\<you>\.kube\oracle-config`)
rather than overwriting the WSL2 default, so both clusters stay reachable:
`KUBECONFIG=<path> kubectl ...`.

**Image delivery**: no registry yet either (Phase 5 below adds GHCR) — same
`docker save | ctr images import -` as WSL2, just piped over SSH to the
remote node instead of through `wsl`:
```bash
docker save lifeos-app:<tag> | ssh -i ~/.ssh/lifeos_oracle ubuntu@<vm-ip> "sudo k3s ctr images import -"
```

**cert-manager + Ingress + TLS**: installed via `helm` from inside the WSL2
distro (it already has `helm`; Windows-side doesn't), pointed at the Oracle
kubeconfig via `KUBECONFIG=/mnt/c/Users/<you>/.kube/oracle-config`:
```bash
helm repo add jetstack https://charts.jetstack.io
helm install cert-manager jetstack/cert-manager -n cert-manager --create-namespace --set crds.enabled=true
helm upgrade --install cert-manager-config ./deploy/cert-manager-config
```
`deploy/lifeos/values-oracle.yaml` layers on top of `values.yaml` (`-f
values.yaml -f values-oracle.yaml`) for everything Oracle-specific: ingress
host/issuer, Ollama's Tailscale address, no local ollama Service.

**DNS**: `anna-zawadzka.pl`'s DNS is managed through a Getspace hosting
panel whose zone editor doesn't actually publish to its own authoritative
nameservers (`ns3`/`ns4.getspace.us`) — confirmed two ways: the apex record
it displays doesn't match what's live, and a brand-new disposable test
record never appeared either after "publishing." Not a propagation delay, a
broken panel — worth a support ticket with them separately. **Settled
permanently on `sslip.io`** instead (`141-253-108-155.sslip.io` resolves to
that literal IP automatically, no account/setup, a real public DNS record so
Let's Encrypt's HTTP-01 challenge works exactly like a normal domain) —
baked into `values-oracle.yaml`, not a stopgap.

**Real domain added (2026-07-28)**: `lifeos.michalzawadzki.dev`, a domain
actually owned (unlike `anna-zawadzka.pl`'s broken panel above), DNS managed
through Cloudflare. A single A record → `141.253.108.155`, **DNS-only /
grey-cloud (proxy off)** — deliberate, not an oversight: Cloudflare's proxy
would terminate TLS at its edge with its own certificate (making the
Let's Encrypt cert cert-manager issues here irrelevant unless "Full
(strict)" mode is also configured), and would add a layer that can
buffer/interfere with the app's SSE chat streaming, voice, and embedded
Grafana iframe for no benefit on a single personal-use origin. `ingress.host`
(singular) became `ingress.hosts` (list) in the chart so both hostnames
share one Ingress and one SAN certificate — sslip.io kept working
throughout, not replaced. `GOOGLE_OAUTH_REDIRECT_URI` was switched to the
new domain (the app sends one configured `redirect_uri`, not derived
per-request from the Host header) — the matching Authorized redirect URI
was added to the existing Google OAuth client in Cloud Console first, same
"add the new one, leave the old one in place" precedent as the ngrok→sslip.io
cutover above.

**Ollama reachability via Tailscale**: installed on the Windows host
directly (already listens on `0.0.0.0:11434` from the WSL2 setup) and on the
Oracle VM (`curl -fsSL https://tailscale.com/install.sh | sudo sh`, then
`sudo tailscale up`). **Pod-level DNS can NOT resolve Tailscale MagicDNS
names** — verified live: `nslookup <host>.tail386db8.ts.net` from inside a
throwaway pod returns `NXDOMAIN`, even though it resolves fine from the node
shell. Root cause: the node's `/etc/resolv.conf` points at systemd-resolved's
stub (`127.0.0.53`), which only proxies MagicDNS's split-DNS routing in the
*host* network namespace — k3s's CoreDNS `forward` plugin reads that same
file but runs in a different netns where `127.0.0.53` doesn't route
anywhere, so it falls through to the real upstream
(`169.254.169.254`, Oracle's own metadata DNS) which has never heard of
`*.ts.net`. Fixed by using the stable Tailscale IP directly in
`OLLAMA_BASE_URL` instead of the MagicDNS hostname (see the comment in
`values-oracle.yaml`) — re-check that IP with `tailscale status` on the
Windows host if it's ever reconfigured.

**Real data cutover** (Postgres + n8n, from the live WSL2 cluster — not
compose, since that cutover already happened in Phase 2/3 above): identical
mechanics to the original Phase 2/3 cutover (`pg_dump`/`pg_restore`,
tar/`kubectl cp` for n8n's SQLite file), just re-targeted at the Oracle
kubeconfig for the restore side and briefly scaling the **WSL2** app to 0
(not Oracle's) around the dump so production isn't mid-write. Verified: row
counts matched exactly, `n8n`'s `database.sqlite` restored byte-for-byte.

**Live traffic cutover**: Telegram's webhook re-pointed via the Bot API
(`setWebhook`/`getWebhookInfo`, no console needed), Google OAuth's redirect
URI added by hand in
[console.cloud.google.com/apis/credentials](https://console.cloud.google.com/apis/credentials)
(no API for this without existing service-account/gcloud setup) — the old
ngrok redirect URI was left in place alongside the new one, no need to
remove it. ngrok/WSL2 itself was **not** torn down — left running as inert
cold-standby, same "stop what actively duplicates work, don't force-delete
the rest" precedent as the original compose→k3s cutover.

**Windows/WSL2 shell gotcha worth knowing**: `kubectl exec`/`cp` container-
side path arguments (e.g. `/tmp/foo`) get silently mangled into Windows
paths by Git Bash's MSYS path-conversion *unless* `MSYS_NO_PATHCONV=1` is
set — but that same env var, if combined with a `KUBECONFIG=/c/Users/...`
Unix-style path on the *same* command line, breaks KUBECONFIG resolution
instead (kubectl.exe needs a real Windows path, and MSYS_NO_PATHCONV
disables the auto-translation that would normally fix that up). Net effect:
use a Windows-style path (`C:\Users\...`) for `KUBECONFIG` specifically, and
`MSYS_NO_PATHCONV=1` for everything else touching container-side paths.

### Terraform

`terraform/` manages the four Helm releases (`cert-manager`,
`cert-manager-config`, `lifeos`, `kube-prometheus-stack`) — only the `helm`
provider, no `kubernetes` provider, so secrets stay structurally unreachable
from Terraform. Provisioning the VM itself stays a manual one-time step (see
above), not Terraform — free-tier capacity errors have nothing to do with
IaC, and a network/firewall touched once and never again gets little upside
from IaC relative to the risk of a botched automated apply against the only
node.

**State backend** — OCI Object Storage via its S3-compatible API (GitHub-hosted
runners are ephemeral, so local state would look empty on every CI run and
try to reinstall everything). One-time bootstrap, via the `oci` CLI
(`pip install oci-cli` if not already present — needs `~/.oci/config` +
API signing key, set up once via the OCI console's "Add API Key" flow):
```bash
oci iam customer-secret-key create --user-id <your-user-ocid> --display-name terraform-state-backend
# save the returned "key" (secret) and "id" (access key) — the secret is shown ONCE, never retrievable again
oci os bucket create --compartment-id <tenancy-ocid> --name lifeos-terraform-state --namespace <objectstorage-namespace>
```
`terraform/backend.tf` has the non-secret parts (bucket/endpoint/region)
committed; the access/secret key pair is supplied via `AWS_ACCESS_KEY_ID`/
`AWS_SECRET_ACCESS_KEY` env vars at `init`/`plan`/`apply` time — never
committed, same discipline as every other secret in this project.

**Deploy credential** — a scoped `ServiceAccount`/`ClusterRole`/
`ClusterRoleBinding`/token `Secret`
(`deploy/lifeos-deployer-rbac.yaml`), applied once by hand:
```bash
kubectl apply -f deploy/lifeos-deployer-rbac.yaml
```
Not cluster-admin, but genuinely broad within its scope — every API group
the four releases actually touch (core, apps, batch, networking, cert-manager,
kube-prometheus-stack's monitoring CRDs) plus `rbac.authorization.k8s.io`/
`apiextensions.k8s.io` since `kube-prometheus-stack` manages its own
RBAC/CRDs internally and Kubernetes won't let a principal grant permissions
it doesn't itself hold. No node-level access, no wildcard `apiGroup`.
Extract the values Terraform/CI need:
```bash
kubectl get secret lifeos-deployer-token -n lifeos-ci -o jsonpath="{.data.token}" | base64 -d    # -> kube_token / KUBE_TOKEN
kubectl get secret lifeos-deployer-token -n lifeos-ci -o jsonpath="{.data.ca\.crt}"               # -> kube_cluster_ca_certificate / KUBE_CA_CERT (already base64, don't decode again)
# kube_host / KUBE_API_SERVER = https://<vm-ip>:6443
```

**Local usage**: copy `terraform/terraform.tfvars.example` to
`terraform.tfvars` (gitignored) and fill in the three values above, plus
`image_tag` (any already-imported tag for a local run, since Terraform's
deploy path always pulls from GHCR — see below — not the node's local
containerd store).
```bash
cd terraform
AWS_ACCESS_KEY_ID=<key> AWS_SECRET_ACCESS_KEY=<secret> terraform init
terraform import helm_release.cert_manager cert-manager/cert-manager
terraform import helm_release.cert_manager_config default/cert-manager-config
terraform import helm_release.lifeos lifeos/lifeos
terraform plan   # cert_manager / cert_manager_config should show zero-diff;
                  # lifeos will show a real diff (image.* switching from the
                  # local-import values to GHCR) until build-and-push has
                  # actually pushed a real tag — don't apply that one until
                  # then. kube_prometheus_stack has nothing to import (not
                  # installed on this cluster yet) — creating it needs the
                  # grafana-lifeos-pg Secret + grafana_ro Postgres role set
                  # up first (Phase 4 above), so monitoring_enabled defaults
                  # false until that's done.
```

### CI/CD

`.github/workflows/tests.yml` now has three jobs: `test` (unchanged) →
`build-and-push` (builds the root `Dockerfile`, pushes
`ghcr.io/zawadzki-michal/lifeos-app:<short-sha>`, public package, no pull
secret needed) → `deploy` (`terraform apply` with the new tag, then the
migrate-Job dance: delete-then-create the `lifeos-migrate` Job, wait for
completion, force-delete the app pod so it doesn't wait out
`CrashLoopBackOff`'s backoff, `kubectl rollout status` as the real
pass/fail gate — `helm_release.lifeos` sets `wait = false` precisely because
a migration-bearing deploy legitimately crash-loops until that Job runs).
Only on `push` to `master`, not PRs. `deploy`'s `concurrency: { group:
lifeos-deploy, cancel-in-progress: false }` is what actually prevents two
applies racing each other — the OCI backend has no native state locking.

`.github/workflows/rollback.yml` — `workflow_dispatch` with an `image_tag`
input, same `terraform apply` + force-rollout mechanics, no migration
re-run (assumes backward-compatible schema, same assumption alembic-by-hand
already relies on elsewhere).

**GitHub repo secrets needed** (Settings → Secrets and variables → Actions):
`TF_STATE_ACCESS_KEY` / `TF_STATE_SECRET_KEY` (the OCI Customer Secret Key
pair from the Terraform bootstrap above), `KUBE_API_SERVER`, `KUBE_TOKEN`,
`KUBE_CA_CERT` (the `lifeos-deployer` values above) — `GITHUB_TOKEN` for
GHCR push is automatic, no setup needed.

**Known local-Windows gotcha while bootstrapping any of this**: WSL2's
`bash` auto-appends the interop Windows `PATH` (via `appendWindowsPath`),
which contains spaces (`Program Files (x86)`) — an unquoted `$PATH` in a
script (`export PATH=/foo:$PATH`) undergoes word-splitting on those spaces
and throws `syntax error near unexpected token '('`. Always quote it
(`"$PATH"`), or better, write multi-step scripts to a file and `bash
script.sh` rather than long inline `-c` one-liners.

### Backups (rclone → Google Drive)

The WSL2 hostPath/GoogleDrive-desktop-client trick (see the "Off-box copy"
section above) has no equivalent on a bare Linux VM — no desktop sync
client running here. `deploy/lifeos/templates/postgres-backup-cronjob.yaml`
now supports two off-box mechanisms via `backup.offBox.mode`:
`hostPath` (WSL2, unchanged) or `rclone` (Oracle, real Google Drive API).
`deploy/backup.Dockerfile` (alpine + `postgresql16-client` + `rclone`,
pushed to `ghcr.io/zawadzki-michal/lifeos-backup` by the same CI
`build-and-push` job as the app image) replaces `postgres.image` as the
CronJob's container — the pg_dump binary now lives there instead, since
`postgres.image` never had rclone.

**One-time `rclone config` OAuth setup — must be done by a human, not
automatable**: run `rclone config` locally on Windows (not the headless
Oracle VM — no browser there):
```
n                          # New remote
name> gdrive                # must match backup.offBox.rcloneRemote exactly
Storage> drive               # search/select Google Drive
client_id>                   # blank — rclone's built-in shared credentials
client_secret>               # blank
scope> 2                     # drive.file — least-privilege, rclone only sees files it creates
root_folder_id>              # blank
service_account_file>        # blank
Use auto config?> y          # opens your browser — log in as the Google account backups should land in, grant access
Configure as Shared Drive?> n
```
Find the resulting file with `rclone config file` (Windows default:
`%APPDATA%\rclone\rclone.conf`). Then create the K8s Secret (same
"created once by hand, never templated" pattern as `lifeos-secrets`):
```
kubectl create secret generic rclone-config -n lifeos --from-file=rclone.conf=<path-to-rclone.conf>
```

**After the first CI run** that builds `deploy/backup.Dockerfile`: set the
`lifeos-backup` GHCR package to public visibility (Settings → Packages →
`lifeos-backup`), same one-time step `lifeos-app` needed — otherwise
`imagePullPolicy` fails with `ImagePullBackOff` (no pull secret configured).
Then bump `values.yaml`'s `backup.image` from the `REPLACE_ME` placeholder
to the real pushed tag.

**Verification** — same manual-trigger flow as the WSL2 hostPath leg:
```
kubectl create job --from=cronjob/postgres-backup postgres-backup-manual -n lifeos
kubectl logs -n lifeos job/postgres-backup-manual   # confirm "copied to off-box rclone remote gdrive:lifeos-backups", not a failure line
kubectl delete job -n lifeos postgres-backup-manual
```
**Not verified by the job itself** — same caveat as the hostPath leg,
just via a different mechanism: confirm the file actually landed with
`rclone lsf gdrive:lifeos-backups` (from a machine with the same
`rclone.conf`) or the Drive web UI, not just that the CronJob logged
success.
