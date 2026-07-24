# LifeOS on k3s — Phase 1 (postgres, redis, app)

Deployment target: a dedicated WSL2 distro (`Ubuntu-24.04`) running k3s,
separate from Docker Desktop's own WSL usage. docker-compose remains the
local dev workflow unchanged — this is only the always-on deployment target.
Full rationale and phased plan: see the approved plan doc (ask if you need
the path again).

Current state on this machine: bootstrapped and verified working (see
below) — node `yogi`, k3s v1.36.2+k3s1, Ollama reconfigured to listen on
`0.0.0.0:11434`.

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
