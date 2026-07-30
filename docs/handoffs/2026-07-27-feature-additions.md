# Handoff — Feature Additions & Compose Hardening
**Date:** 27/07/2026  
**Branch:** `setup/initial-deployment`

---

## What was done this session

### 1. Open WebUI — model visibility fix
- Added `BYPASS_MODEL_ACCESS_CONTROL: "true"` to the `open-webui` service so all users see the full model dropdown without per-model permission grants.

### 2. Web search — SearXNG integration
- Added `searxng` service to `compose.yml` (backend + proxy networks, Traefik labels, health check).
- Added Open WebUI env vars: `ENABLE_WEB_SEARCH`, `WEB_SEARCH_ENGINE`, `SEARXNG_QUERY_URL`, `WEB_SEARCH_RESULT_COUNT`, `WEB_SEARCH_CONCURRENT_REQUESTS`.
- Created `compose/searxng/settings.yml` — JSON format enabled (required for Open WebUI API queries).
- Added `SEARXNG_IMAGE` and `SEARXNG_FQDN` to `env_var.cfg`.
- **Note:** The SearXNG Query URL must also be set manually in Open WebUI Admin Panel → Settings → Web Search (env var doesn't pre-populate the UI field). Set to `http://searxng:8080/search?q=<query>` and Concurrent Requests to `10`.

### 3. Compose conventions rule — CLAUDE.md updated
Added a mandatory checklist to `CLAUDE.md → Compose conventions` covering:
- Image must be a `${VAR}` from `.env`
- All env values from `.env`
- Persistent data under `/mnt/ai-files/<service>/`
- Health check required
- Traefik labels required for all LAN-facing services
- Networks: join only what's needed

### 4. Health checks audit & fixes
All services audited against Context7 docs. Results:

| Service | Status | Notes |
|---|---|---|
| Traefik | Removed | `traefik healthcheck` CLI can't read CLI flags; image is `FROM scratch` (no wget/curl) |
| Redis | ✅ `redis-cli ping` | Confirmed |
| PostgreSQL | ✅ `pg_isready` | Confirmed |
| Ollama | Updated to `ollama ps` | `ollama list` not a health endpoint |
| Speaches | ✅ `curl /health` | Unconfirmed by docs but left as-is |
| Authentik server | ✅ `/-/health/ready/` | Confirmed, checks DB connectivity |
| Authentik worker | N/A | No HTTP endpoint, not feasible |
| Open WebUI | ✅ `curl /health` | Confirmed |
| Portainer | Removed | Image is minimal Go binary — no curl, wget, or pgrep available |
| SearXNG | ✅ `wget /healthz` | Confirmed — returns plain text `OK` |

### 5. ComfyUI added to compose.yml
- Added `comfyui` service using `yanwk/comfyui-boot:cu130-slim` (community image, actively maintained, updated weekly).
- Chose over ai-dock (stale, >1yr old) and SD Forge.
- ComfyUI preferred over SD Forge for this stack because it releases VRAM when idle, allowing Ollama to reclaim GPU memory between image generation sessions.
- Volumes correctly mapped to `/root/ComfyUI/` paths (yanwk layout).
- `CLI_ARGS` env var included with commented options (`--lowvram`, `--gpu-only`, `--fast`).
- Added `COMFYUI_IMAGE` and `COMFYUI_FQDN=comfyui.murs-local.net` to `env_var.cfg`.

---

## Outstanding / next steps

### SearXNG
- [ ] Copy `SEARXNG_FQDN` and `SEARXNG_IMAGE` to `.env` on VM (diff confirmed these are missing)
- [ ] Fix `SEARXNG_IMAGE` in `.env` — currently set to `searxng/searxng:latest`; pin to a dated tag
- [ ] Create DNS record for `search.murs-local.net`
- [ ] Copy `compose/searxng/settings.yml` to `/mnt/ai-files/searxng/config/settings.yml` on VM (volume mount path changed from repo-relative to `/mnt/ai-files/searxng/config`)
- [ ] Replace `secret_key: "changeme-replace-with-random-string"` in `settings.yml` with output of `openssl rand -hex 32`

### ComfyUI
- [ ] Copy `COMFYUI_IMAGE` and `COMFYUI_FQDN` to `.env` on VM
- [ ] Create host directories: `mkdir -p /mnt/ai-files/comfyui/{models,output,input,custom_nodes,user}`
- [ ] Create DNS record for `comfyui.murs-local.net`
- [ ] Download a model checkpoint into `/mnt/ai-files/comfyui/models/checkpoints/` (SDXL or Flux recommended for RTX 3060 12GB)
- [ ] Deploy: `docker compose up -d comfyui`
- [ ] Wire Open WebUI — Admin Panel → Images → set URL to `http://comfyui:8188`

### Discussed but not started
- Code execution sandbox (Open WebUI built-in, needs a sandboxed container)
- Context7 MCP on the VM (needs outbound internet; Open WebUI has MCP support)
- Mem0 memory layer (commented out in `compose.yml`, pending Ollama-compatible server image)

---

## Key files changed this session

| File | Change |
|---|---|
| `compose.yml` | SearXNG service, ComfyUI service, health check fixes, BYPASS_MODEL_ACCESS_CONTROL, web search env vars |
| `compose/searxng/settings.yml` | Created — SearXNG config with JSON format enabled |
| `env_var.cfg` | Added `SEARXNG_IMAGE`, `SEARXNG_FQDN`, `COMFYUI_IMAGE`, `COMFYUI_FQDN` |
| `CLAUDE.md` | Added mandatory compose checklist under Compose conventions |

---

## Environment notes
- GPU: RTX 3060 12GB — shared between Ollama (LLM) and ComfyUI (image gen)
- Two trusted users; internal LAN only (`murs-local.net`)
- Traefik handles TLS via Cloudflare DNS-01 Let's Encrypt
- Authentik is the SSO/OIDC provider; Open WebUI uses OIDC login only (`ENABLE_LOGIN_FORM: "false"`)

---

## Suggested skills for next session

- `/context7-mcp` — before touching any image tag, volume path, or env var for a new service
- `/run` — to verify ComfyUI starts and the UI is reachable after deployment
- `feature-dev:code-architect` — if adding code execution sandbox (needs sandboxed container design)
