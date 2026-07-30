# Handoff — 26/07/2026 — Initial Deployment Session

## What was accomplished this session

- Initialised git repository and made the first commit
- Replaced `fedirz/faster-whisper-server` + `kokoro-fastapi` with a single `speaches-ai/speaches:0.8.3-cpu` container serving both STT (Whisper) and TTS (Kokoro) on port 8000
- Removed `mem0` from the stack (see `compose.yml` comment and `archive/01-create-databases-with-mem0.sh`)
- Fixed all Docker image tags — pinned to specific releases in `env_var.cfg`
- Fixed PostgreSQL 18 volume mount (`/var/lib/postgresql` not `/var/lib/postgresql/data`)
- Fixed init script to double-quote hyphenated usernames and pass DB env vars into the postgres container
- Fixed Ollama healthcheck (`ollama list` — no curl in image)
- Fixed Authentik healthcheck (no curl or wget — uses `python3 urllib.request`)
- Added `authentik-worker` → `depends_on: authentik-server: condition: service_healthy` to prevent migration race condition
- Added `authentik-worker` to `proxy` network so it can resolve external DNS
- Upgraded Traefik from `v3.5` → `v3.7.9` to fix Docker API version negotiation (v3.5 requested API 1.24, daemon minimum is 1.40)
- Corrected Cloudflare DNS A records from `192.168.1.62` to `192.168.1.63`
- Fixed `backup/backup.sh` — was referencing named Docker volume `openwebui_data` but compose uses bind mount at `/mnt/ai-files/open-webui/data`
- Created `docs/SERVER-LAYOUT.md` documenting project dir and data dir structure

## Current container state (end of session)

| Container | Status |
|---|---|
| ai-traefik | Running |
| ai-redis | Healthy |
| ai-postgres | Healthy |
| ollama | Healthy |
| ai-speaches | Healthy |
| ai-authentik-server | Running (healthcheck passing — see known issue below) |
| ai-open-webui | Healthy |
| ai-portainer | Running |
| ai-authentik-worker | **Missing** — blocked by authentik-server unhealthy status |

## Known issues / immediate next steps

### 1. Authentik healthcheck timing
The `authentik-server` container reports unhealthy to Compose due to migration time exceeding `start_period: 60s` on fresh DB, but the server itself is functioning. The healthcheck test (`python3 urllib.request`) was confirmed working manually. Consider increasing `start_period` to `120s`.

### 2. Authentik worker not running
Because `authentik-server` shows unhealthy to Compose, `authentik-worker` won't start (blocked by `service_healthy`). Once the healthcheck timing is resolved, run:
```bash
docker compose up -d authentik-worker
```

### 3. Authentik OIDC not configured
Open WebUI has `OAUTH_CLIENT_SECRET=CHANGE_AFTER_CREATING_AUTHENTIK_PROVIDER` in `.env`. Steps to fix:
1. Log into Authentik at `https://auth.murs-local.net` (user: `akadmin`, password: `AUTHENTIK_BOOTSTRAP_PASSWORD` from `.env`)
2. Create an OAuth2/OpenID Provider — Client ID: `open-webui-client`, redirect URI: `https://ai.murs-local.net/oauth/oidc/callback`
3. Create an Application with slug `open-webui` linked to the provider
4. Copy the generated client secret into `.env` as `OAUTH_CLIENT_SECRET`
5. `docker compose up -d open-webui`

### 4. Authentik groups for Open WebUI
Open WebUI is configured for role-based access via Authentik groups:
- `OAUTH_ADMIN_ROLES: ai-admins`
- `OAUTH_ALLOWED_ROLES: ai-admins,ai-users`

Create these groups in Authentik and assign users accordingly.

### 5. Ollama models not yet pulled
No models are loaded — `ollama list` returns empty. Pull at minimum:
```bash
docker exec ollama ollama pull qwen2.5-coder:14b-instruct-q4_K_M
docker exec ollama ollama pull nomic-embed-text
```

### 6. Speaches model not yet downloaded
First TTS/STT request will trigger download of `Systran/faster-whisper-medium` and `speaches-ai/Kokoro-82M-v1.0-ONNX`. Pre-warm with:
```bash
curl -s http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"speaches-ai/Kokoro-82M-v1.0-ONNX","voice":"af_bella","input":"Warming up."}' \
  --output /dev/null
```

## Key file locations

| File | Purpose |
|---|---|
| `compose.yml` | Full service definitions |
| `env_var.cfg` | Source of truth for image tags and config (copy to `.env`, never commit) |
| `compose/postgres/init/01-create-databases.sh` | DB init script — copy to `/mnt/ai-files/postgres/init/` on server |
| `docs/SERVER-LAYOUT.md` | Full directory structure for `/mnt/ai-files/` and `/opt/local-ai-appliance/` |
| `docs/DECISIONS.md` | Architectural decisions |
| `archive/01-create-databases-with-mem0.sh` | Archived init script with mem0 — restore if memory service is added |
| `backup/backup.sh` | Nightly restic backup script |

## Pending compose.yml items to review next session

- `authentik-server` `start_period` may need increasing to `120s`
- `portainer` has no healthcheck
- `authentik-worker` has no healthcheck
- Git push to `https://github.com/muradDeveloper/local-ai-appliance.git` was never completed (user interrupted push confirmation)

## Suggested skills

- `/handoff` — if continuing across another session
- `/context7-mcp` — before touching any image version or config schema
- `/commit-commands:commit-push-pr` — to push accumulated changes to GitHub once Authentik is fully working
