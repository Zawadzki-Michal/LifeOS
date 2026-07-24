# Small image for postgres-backup-cronjob.yaml: pg_dump (matching
# postgres.image's server major version, currently pg16) + rclone (real
# Google Drive API off-box backups on Oracle — the WSL2 hostPath/GoogleDrive-
# desktop-client trick has no equivalent on a bare Linux VM). Built and
# pushed to GHCR by .github/workflows/tests.yml's build-and-push job,
# alongside the main app image.
#
# COUPLING WARNING: if postgres.image's Postgres major version ever changes,
# the postgresqlNN-client package below must be bumped to match. This used
# to be automatic (the backup CronJob reused postgres.image itself for
# pg_dump) — now it's two places to keep in sync.
FROM alpine:3.19

RUN apk add --no-cache postgresql16-client rclone

CMD ["sh"]
