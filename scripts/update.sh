#!/usr/bin/env bash
set -Eeuo pipefail

printf 'Create and verify an application backup before continuing.\n'
read -r -p 'Type UPDATE to continue: ' answer
[[ "$answer" == "UPDATE" ]] || exit 1

docker compose pull
docker compose up -d --remove-orphans
docker compose ps
