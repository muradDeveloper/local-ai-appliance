#!/usr/bin/env bash
set -Eeuo pipefail

ENV_FILE="${1:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  cp .env.example "$ENV_FILE"
fi

random_hex() {
  openssl rand -hex "${1:-32}"
}

replace_value() {
  local key="$1"
  local value="$2"
  sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
}

replace_value POSTGRES_SUPERUSER_PASSWORD "$(random_hex 24)"
replace_value OPENWEBUI_DB_PASSWORD "$(random_hex 24)"
replace_value AUTHENTIK_DB_PASSWORD "$(random_hex 24)"
replace_value MEM0_DB_PASSWORD "$(random_hex 24)"
replace_value AUTHENTIK_SECRET_KEY "$(random_hex 48)"
replace_value AUTHENTIK_BOOTSTRAP_PASSWORD "$(random_hex 24)"
replace_value WEBUI_SECRET_KEY "$(random_hex 48)"
replace_value RESTIC_PASSWORD "$(random_hex 32)"

chmod 600 "$ENV_FILE"
printf 'Generated secrets in %s. Review hostnames, IPs, image tags and OIDC values.\n' "$ENV_FILE"
