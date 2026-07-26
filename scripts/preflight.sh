#!/usr/bin/env bash
set -Eeuo pipefail

fail=0
check() {
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf '[OK]   %s\n' "$description"
  else
    printf '[FAIL] %s\n' "$description"
    fail=1
  fi
}

check "Docker is installed" docker version
check "Docker Compose is installed" docker compose version
check "NVIDIA driver is visible" nvidia-smi
check "GPU works inside Docker" docker run --rm --gpus all ubuntu:24.04 nvidia-smi
check "No CHANGE_ME values remain in .env" bash -c '! grep -q CHANGE_ME .env'
check "Compose configuration renders" docker compose --env-file .env config

if [[ "$fail" -ne 0 ]]; then
  exit 1
fi

printf '\nPreflight checks passed.\n'
