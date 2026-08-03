#!/usr/bin/env bash
# Wipes all Open WebUI data: stops the container, drops and recreates the
# database, and clears the data volume. Run on the server from the project root.
set -euo pipefail

docker compose stop open-webui

docker exec ai-postgres psql -U postgres-db \
  -c "DROP DATABASE \"openwebui-db-instance\";"

docker exec ai-postgres psql -U postgres-db \
  -c "CREATE DATABASE \"openwebui-db-instance\" OWNER \"openwebui-db-user\";"

rm -rf /mnt/ai-files/open-webui/data/*

echo "Done. Run: docker compose up -d open-webui"
