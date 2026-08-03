# Handoff — 2026-08-03 — Open WebUI Fresh Install & Upgrade to v0.11.0

## Goal
Resolved a broken login screen after the Authentik→native-auth migration, performed a fresh Open WebUI install, and upgraded from v0.10.2 to v0.11.0.

## Project location
- **Working dir:** `C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance`
- **Read first:** `CLAUDE.md`, `compose.yml`, `env_var.cfg`
- **Previous handoff:** `docs/handoffs/handoff-2026-08-02_10-00-auth-simplification.md`

## Working agreement
- Global `~/.claude/CLAUDE.md` and `~/.claude/rules/` take priority over project `CLAUDE.md`
- Archive only when user explicitly asks — never proactively
- Do not run shell/docker/bash commands unless user explicitly asks
- No `&&` chaining in Bash; one command per call; no `$VAR` expansion inline
- Use `env_var.cfg` as source of truth for image tags and config
- After every edit to `env_var.cfg`, copy it to `.env` in the same step (hooks unavailable in enterprise account)

## Root cause resolved this session

The login form showed "Sign in to Open WebUI" with a blank black screen and no form fields. Investigation via CDP confirmed:

1. **Stale OIDC session cookie** — `owui-session` contained an old Authentik OAuth state and was causing Open WebUI to try to resume a dead OAuth flow.
2. **Database-stored config overriding env vars** — `/api/config` returned `enable_login_form: false` and `enable_signup: false`. These were set via the admin UI during the Authentik era and stored in PostgreSQL, overriding the `ENABLE_LOGIN_FORM: "true"` env var in `compose.yml`.

## Fix applied

Fresh installation:
- Ran `scripts/reset-open-webui.sh` on the server (drops + recreates the DB, clears `/mnt/ai-files/open-webui/data/`)
- Upgraded image tag from `v0.10.2` → `v0.11.0` in `env_var.cfg` (and `.env`)
- First user to sign up became admin

## Files modified this session

| File | Change |
|---|---|
| `env_var.cfg` | Updated `OPEN_WEBUI_IMAGE` to `ghcr.io/open-webui/open-webui:v0.11.0` |
| `.env` | Copied from `env_var.cfg` (gitignored) |
| `scripts/reset-open-webui.sh` | New script — wipes Open WebUI DB and data volume |

## Current stack state

| Service | Version | Notes |
|---|---|---|
| open-webui | v0.11.0 | Fresh install; admin account created |
| postgres | pgvector/pgvector:0.8.5-pg18 | DB recreated fresh |
| ollama | 0.32.4 | Unchanged |
| speaches | 0.8.3-cpu | Unchanged |
| portainer | 2.39.5 | Unchanged |
| searxng | latest | Unchanged |
| comfyui | yanwk/comfyui-boot:cu130-slim | Unchanged |
| weather-server | local build | Unchanged |

## Next steps

### Immediate
1. **Lock signups** — once the second user account is created, set `ENABLE_SIGNUP: "false"` in `compose.yml` and redeploy:
   ```bash
   docker compose up -d open-webui
   ```
2. **Remove stale Authentik router** from the external Traefik dynamic config file on the server (carried over from previous handoff — still not done).

### Cleanup (when ready)
- Delete leftover Authentik/Redis data on disk (carried from previous handoff):
  ```bash
  rm -rf /mnt/ai-files/redis/
  rm -rf /mnt/ai-files/authentik/   # only when confident not needed
  ```
- Stale vars in `env_var.cfg` (no longer referenced): `TRAEFIK_BIND_IP`, `TRAEFIK_IMAGE`, `AUTHENTIK_IMAGE`, `CF_DNS_API_TOKEN`, `ACME_EMAIL` — leave or clean up as desired.

## v0.11.0 notable changes (from CHANGELOG)
- Redesigned UI, sub-agents, folder pages, chat forking, SSO toggle, PKCE
- Admin settings now live inside the main Settings window (no longer a separate page)
- `python-jose` and GCS emulator removed from image
- `prompt_tokens`/`completion_tokens` now per-call (not cumulative) — `input_tokens`/`output_tokens` are cumulative

## What to avoid
- Do not re-introduce Authentik or OIDC without an ADR
- Do not bind services on `0.0.0.0`
- `ENABLE_SIGNUP: "true"` is temporary — must be set to `"false"` after user accounts are created
- Do not expose Ollama, PostgreSQL, or Speaches with host port bindings on the LAN IP

## Suggested skills for next session
- `/context7-mcp` — before any image tag or env var changes, verify against live docs
- `/write-docker-compose` — if adding new services to compose.yml
- `/chrome-devtools-mcp` — for browser-based debugging of Open WebUI

## How to respond
Start with a 1–2 line summary of your understanding and continue from here — do not restart or re-examine decisions already made.
