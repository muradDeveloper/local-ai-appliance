# Handoff — 2026-08-02 — Auth Simplification & Stack Cleanup

## Goal
Removed Authentik OIDC, Redis, and internal Traefik from the local AI appliance stack. Open WebUI now uses its own native login form. Routing is handled by an external Traefik instance; services expose direct ports on the LAN IP `192.168.1.63`.

## Project location
- **Working dir:** `C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance`
- **Read first:** `CLAUDE.md`, `compose.yml`, `env_var.cfg`
- **Env template:** `env_var.cfg` (not `.env.example` — that file is inaccessible)

## Working agreement
- Global `~/.claude/CLAUDE.md` and `~/.claude/rules/` take priority over project `CLAUDE.md`
- Archive only when user explicitly asks — never proactively
- Do not run shell/docker/bash commands unless user explicitly asks
- No `&&` chaining in Bash; one command per call; no `$VAR` expansion inline
- Use `env_var.cfg` as the source of truth for image tags and config

## Locked decisions

| Decision | Reason |
|---|---|
| Authentik removed entirely | Switching to Open WebUI native auth; 2 trusted users, no SSO needed |
| Redis removed | Was only used by Authentik |
| Internal Traefik removed | External Traefik handles all DNS routing and TLS termination |
| Services bind on `192.168.1.63:<port>` | External Traefik proxies to these LAN ports via file-based static routes |
| Open WebUI uses PostgreSQL | Existing data is there; SQLite migration not worth the effort |
| Speaches not exposed externally | It's API-only (no mic UI); mic access is through Open WebUI which calls Speaches internally |

## Done

### Files modified this session
| File | Change |
|---|---|
| `compose.yml` | Removed Traefik service, Authentik server+worker, Redis. Switched Open WebUI to native auth (`ENABLE_LOGIN_FORM: true`, `ENABLE_SIGNUP: true`). Added direct port bindings for all LAN-facing services. Removed Authentik DB vars from postgres block. |
| `env_var.cfg` | Commented out all Authentik vars, OIDC vars, Redis image, AUTH_FQDN. |
| `CLAUDE.md` | Added global instructions priority note, pre-change archiving rule, updated architectural constraints to reflect external Traefik and direct port binding model. Archived stale Traefik/Authentik rules. |

### Current stack (compose.yml)
| Service | Port binding | Notes |
|---|---|---|
| postgres | none | Internal only, `database` network |
| ollama | `127.0.0.1:11434` | Loopback only, for VS Code/Continue on the VM |
| speaches | `expose` only | Internal only, `backend` network |
| open-webui | `192.168.1.63:8080` | Native auth enabled, signup open |
| portainer | `192.168.1.63:9000` + `9443` | 9000=HTTP for Traefik, 9443=HTTPS direct |
| searxng | none | Internal only, accessed by Open WebUI via Docker network |
| weather-server | `192.168.1.63:8000` | Custom tool server for Open WebUI |
| comfyui | `192.168.1.63:8188` | Image generation |

### External Traefik dynamic config (on the server, not in this repo)
Routes already configured for: `open-webui`, `portainer-ai`, `comfyui`, `weather`, `dozzle-ai`.
**Still contains a stale `authentik` router and service — needs to be removed.**

### Archive
`archive/backup-2026-08-02-before-open-webui-native-auth/` — snapshot of `compose.yml` and `env_var.cfg` before all changes this session.

## Next steps

### Immediate (on the server)
1. Copy updated `env_var.cfg` → `.env` on the server (currently out of sync)
2. Run `docker compose --env-file .env up -d --remove-orphans` to stop orphaned Authentik + Redis containers and apply all changes
3. Remove the `authentik` router and service from the external Traefik dynamic config file
4. Create the first Open WebUI admin account at `https://ai.murs-local.net`
5. Once both user accounts are created, set `ENABLE_SIGNUP: "false"` in `compose.yml` and redeploy

### Cleanup (when ready)
- Delete leftover data on disk:
  ```bash
  rm -rf /mnt/ai-files/redis/
  rm -rf /mnt/ai-files/authentik/   # only when confident it's not needed
  ```
- The Authentik database still exists inside Postgres data at `/mnt/ai-files/postgres/` — inert but not removed

### Open questions
- Portainer: user couldn't access via direct IP (`https://192.168.1.63:9443`) — likely a browser SSL warning (self-signed cert, click Advanced → Proceed). Unconfirmed.
- Several stale vars remain in `env_var.cfg`: `TRAEFIK_BIND_IP`, `TRAEFIK_IMAGE`, `AUTHENTIK_IMAGE`, `CF_DNS_API_TOKEN`, `ACME_EMAIL` — no longer referenced by compose but left in place. Clean up if desired.

## What to avoid
- Do not re-introduce Authentik or OIDC without an ADR
- Do not re-introduce Redis unless a service explicitly requires it
- Do not bind services on `0.0.0.0`
- Do not expose Ollama, PostgreSQL, or Speaches with host port bindings on the LAN IP
- `ENABLE_SIGNUP: "true"` is temporary — must be set back to `"false"` after user accounts are created

## How to respond
Start with a 1–2 line summary of your understanding and continue from here — do not restart or re-examine decisions already made.
