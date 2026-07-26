#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
source .env

timestamp="$(date +'%Y%m%d-%H%M%S')"
work="/tmp/local-ai-backup-${timestamp}"
mkdir -p "$work"
trap 'rm -rf "$work"' EXIT

# Export application databases.
docker exec ai-postgres pg_dump -U "$POSTGRES_SUPERUSER" -Fc "$OPENWEBUI_DB_NAME" \
  > "$work/openwebui.dump"
docker exec ai-postgres pg_dump -U "$POSTGRES_SUPERUSER" -Fc "$AUTHENTIK_DB_NAME" \
  > "$work/authentik.dump"

# Export Open WebUI data directory (Chroma vector store, browser-uploaded files).
# Crash-consistent — Open WebUI is not paused. Acceptable for a homelab nightly run.
tar -czf "$work/openwebui-data.tar.gz" -C /mnt/ai-files/open-webui/data .

# Record model inventory instead of backing up large model blobs.
docker exec ollama ollama list > "$work/model-inventory.txt"

# Record deployment state.
docker compose config > "$work/compose-rendered.yml"
docker compose images > "$work/container-images.txt"
sha256sum "$work"/* > "$work/SHA256SUMS"

# Back up the exports, source documents and repository configuration.
restic backup \
  "$work" \
  .env \
  compose.yml \
  compose \
  knowledge \
  docs

# Apply retention and verify repository metadata.
restic forget --prune \
  --keep-daily "$BACKUP_RETENTION_DAILY" \
  --keep-weekly "$BACKUP_RETENTION_WEEKLY" \
  --keep-monthly "$BACKUP_RETENTION_MONTHLY"

restic check
printf 'Backup completed: %s\n' "$timestamp"
