# Handoff — 2026-08-04 14:43 — Compose review, SearXNG, Traefik

## Context

Continuing work on the local AI appliance stack (Proxmox Ubuntu VM, RTX 3060).
Branch: `setup/initial-deployment`. External Traefik on 192.168.1.62 proxies all LAN-facing services. AI stack runs on 192.168.1.63.

Previous session handoff: `docs/handoffs/handoff-2026-08-04_01-00_-_extended_-_hermes-odysseus-deployment-fixes.md`

---

## What was done this session

### 1. Docker Compose review (`/write-docker-compose`)

Three compose files reviewed. All changes applied.

#### `compose/odysseus/compose.yml`
- ChromaDB healthcheck: TCP probe `bash -c 'echo > /dev/tcp/localhost/8000'` → `python3 urllib.request.urlopen('http://localhost:8000/api/v2/heartbeat')` (curl not present in image; `init: true` and `security_opt` were already correct)

#### `compose.yml` (main)
- All `/mnt/ai-files/` volume paths replaced with `${AI_FILES_BASE}/` (parameterised)
- Profile volume changed from repo-relative `./compose/comfyui/profiles` → `${AI_FILES_BASE}/open-webui/profiles:/app/profiles:ro` (consistent pattern; added to push_hosts sync)
- `init: true` added to all 8 services
- `security_opt: no-new-privileges:true` added to all services missing it (postgres, ollama, speaches, open-webui, weather-server, searxng, comfyui — portainer already had it)
- SearXNG given host port binding: `${LLM_BIND_IP}:8888:8080` (previously internal-only)

#### `env_var.cfg`
- Added `AI_FILES_BASE=/mnt/ai-files` (near `LLM_BIND_IP`)
- **After any edit to env_var.cfg: run `cp env_var.cfg .env` before `docker compose up -d`** (hooks disabled on this enterprise account)

### 2. `scripts/push_config.py` (real path: `homelab_SOC/scripts/env_scripts/push_config.py`)
- Added remote directory pre-flight check via SSH `test -d`
- Prompts user to create missing directories (`mkdir -p`) before rsync
- Results cached in `homelab_SOC/scripts/env_scripts/.push_dir_cache.json` — delete to force re-check

### 3. `scripts/push_hosts.yaml` (real path: `homelab_SOC/scripts/env_scripts/push_hosts.yaml`)
- Added profiles sync to service id 5 (local-ai-appliance):
  - local: `compose/comfyui/profiles/` → remote: `/mnt/ai-files/open-webui/profiles/`

### 4. SearXNG `compose/searxng/settings.yml`
- `use_default_settings: true` → dict form with `engines.remove` list (correct SearXNG config syntax to prevent engine init, not just disable for search)
- Removed from loading entirely: `wikidata` (403 on SPARQL init), `ahmia` (missing deps), `torch` (missing deps)
- Disabled for search: `startpage` (server IP blocked by CAPTCHA, `suspended_time=3600`)
- Fixed `wttrin` engine: added `engine: wttr` field (missing field caused load failure)
- Remaining harmless log noise (no action needed):
  - `X-Forwarded-For nor X-Real-IP header is set!` — Open WebUI calls SearXNG directly via Docker network, bypassing Traefik; `limiter: false` so nothing is blocked
  - `missing config file: /etc/searxng/limiter.toml` — irrelevant while limiter is off

### 5. Traefik `homelab_SOC/stacks/traefik-master/dynamic/ai-services.yaml`
- Added SearXNG router: `search.murs-local.net` → `http://192.168.1.63:8888`
- Added Traefik-level `healthCheck` to all backend services:

| Service | Health path | Port |
|---|---|---|
| open-webui | `/health` | 8080 |
| comfyui | `/system_stats` | 8188 |
| weather | `/openapi.json` | 8000 |
| portainer-ai | `/api/status` | 9443 (HTTPS) |
| hermes | `/health` | 9119 |
| odysseus | `/` | 7000 |
| dozzle-ai | `/healthz` | 8111 |
| searxng | `/healthz` | 8888 |
| authentik | *(no healthcheck — stale entry, service not running)* | 9000 |

- Authentik entry left in place (service removed from stack but entry not yet cleaned up — stale)

### 6. Traefik `homelab_SOC/stacks/traefik-master/traefik.yaml`
- Added TODO comment block on `websecure` entrypoint for `forwardedHeaders.trustedIPs` (see below)

---

## Pending / not yet deployed

### Must do before `docker compose up -d`
```bash
# On the AI server (192.168.1.63)
cp env_var.cfg .env
docker compose up -d
```

### Push configs to server
```bash
# From WSL — push_config.py runs in WSL, not PowerShell
python push_config.py local-ai-appliance   # compose.yml, env_var.cfg, profiles/, searxng settings
python push_config.py traefik-master       # ai-services.yaml, traefik.yaml
```
First run of `local-ai-appliance` push will prompt to create `/mnt/ai-files/open-webui/profiles/` — answer `y`.

### Open WebUI — tool + profile mount
- Tool file: `compose/comfyui/tools/image_negative_prompt_gen.py` (v2.0, full rewrite from previous session)
- Must be pasted manually into Open WebUI admin UI: Workspace → Tools → New
- Profile volume `${AI_FILES_BASE}/open-webui/profiles:/app/profiles:ro` will be active after the compose restart above
- Set Valve `profiles_path` = `/app/profiles/all_profiles.yml`, `default_checkpoint` = your active checkpoint alias

### Odysseus — not yet deployed
- Repo not cloned on server yet
- See previous handoff for deployment steps: `docs/handoffs/handoff-2026-08-04_01-00_-_extended_-_hermes-odysseus-deployment-fixes.md`
- Odysseus `env_var.cfg` uses Docker DNS for SearXNG: `SEARXNG_INSTANCE=http://searxng:8080` — valid since both share `ai_backend` network; update to `https://search.murs-local.net` if preferred

### Traefik — forwardedHeaders.trustedIPs (deferred)
In `homelab_SOC/stacks/traefik-master/traefik.yaml`, the `websecure` entrypoint has a commented-out block:
```yaml
# forwardedHeaders:
#   trustedIPs:
#     - "127.0.0.1/32"
#     - "172.16.0.0/12"
#     - "192.168.0.0/16"
#     - "10.0.0.0/8"
```
Uncomment this so Traefik correctly strips and re-adds `X-Forwarded-For` before passing to backends. This will fix the SearXNG botdetection warning for browser requests that come through Traefik. Does NOT fix the Open WebUI→SearXNG direct path (which is intentional).

### Authentik — stale Traefik entry
`ai-services.yaml` still has an authentik router + service pointing to port 9000, but Authentik was removed from the stack. Clean this up when convenient.

---

## Key architectural constraints (do not change without ADR)
- No `init: true` on Hermes — uses s6-overlay as PID 1, confirmed in previous handoff
- All host port bindings use `${LLM_BIND_IP}` (192.168.1.63), never `0.0.0.0`
- `env_var.cfg` is gitignored; never commit it; always `cp env_var.cfg .env` after edits
- Profiles YAML parsed at runtime by PyYAML inside Open WebUI container; Fitzpatrick Scale (I–VI), not Monk Scale
- SearXNG is internal-only for Open WebUI; also now exposed via Traefik at `search.murs-local.net` port 8888

---

## File map — what changed this session

| File | Repo |
|---|---|
| `compose.yml` | local-ai-appliance |
| `env_var.cfg` | local-ai-appliance |
| `compose/odysseus/compose.yml` | local-ai-appliance |
| `compose/searxng/settings.yml` | local-ai-appliance |
| `compose/comfyui/tools/image_negative_prompt_gen.py` | local-ai-appliance (prev session) |
| `compose/comfyui/profiles/all_profiles.yml` | local-ai-appliance (prev session) |
| `scripts/push_hosts.yaml` | homelab_SOC (symlinked) |
| `scripts/push_config.py` | homelab_SOC (symlinked) |
| `stacks/traefik-master/dynamic/ai-services.yaml` | homelab_SOC |
| `stacks/traefik-master/traefik.yaml` | homelab_SOC |

Note: `scripts/push_hosts.yaml` and `scripts/push_config.py` in the local-ai-appliance repo are **symlinks** to `homelab_SOC/scripts/env_scripts/`. Always edit the real path to avoid symlink write errors.

---

## Suggested skills for next session

- `/write-docker-compose` — if adding Odysseus to the stack or reviewing its compose after deployment
- `/handoff` — at end of next session
