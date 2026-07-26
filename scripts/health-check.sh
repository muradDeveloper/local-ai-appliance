#!/usr/bin/env bash
set -Eeuo pipefail

docker compose ps
printf '\nGPU:\n'
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,temperature.gpu --format=csv
printf '\nOllama models:\n'
docker exec ollama ollama list || true
printf '\nOpen WebUI health:\n'
docker exec ai-open-webui python - <<'PY'
import urllib.request
print(urllib.request.urlopen("http://127.0.0.1:8080/health", timeout=5).read().decode())
PY
