# Handoff — Deploying Hermes and Odysseus
**Date:** 03/08/2026 08:39  
**Next focus:** Deploy both stacks to .63, register in Komodo

---

## What was done this session

### New stacks created

Both Hermes and Odysseus are built as independent Docker Compose stacks living under `compose/hermes/` and `compose/odysseus/` respectively. They run on **.63** (local-ai-appliance), joining the existing `ai_proxy` and `ai_backend` external Docker networks.

| Stack | Ports (LAN) | Networks |
|---|---|---|
| Hermes Agent | `.63:8642` (API), `.63:9119` (dashboard) | `ai_proxy`, `ai_backend` |
| Odysseus | `.63:7000` (UI) | `ai_proxy`, `ai_backend` |
| ChromaDB (Odysseus sidecar) | internal only | `ai_backend` |

### Key files

| File | Status | Notes |
|---|---|---|
| `compose/hermes/compose.yml` | Ready | `${BIND_IP}` for port binds, `env_file: .env` |
| `compose/hermes/env_var.cfg` | Ready | `BIND_IP`, `TZ`, `HERMES_IMAGE` |
| `compose/hermes/config.yaml` | Ready | Ollama LLM config — pushed to `/mnt/ai-files/hermes/data/config.yaml` |
| `compose/odysseus/compose.yml` | Ready | Builds from GitHub URL; `${BIND_IP}`, `env_file: .env`, `init: true`, `security_opt` |
| `compose/odysseus/env_var.cfg` | Ready | Full config incl. `BIND_IP`, `TZ`, `CHROMADB_IMAGE=chromadb/chroma:1.5.3` |
| `homelab_SOC/stacks/traefik-master/dynamic/ai-services.yaml` | Updated | Hermes → `.63:9119`, Odysseus → `.63:7000` (IPs intentional in dynamic config) |
| `homelab_SOC/scripts/env_scripts/push_hosts.yaml` | Updated | id 6 = hermes → .63, id 7 = odysseus → .63 |

### How env vars work in sub-stacks

`push_hosts.yaml` pushes `env_var.cfg` **as `.env`** on the remote (`remote: /opt/stacks/<stack>/.env`).  
Docker Compose reads `.env` for both `${VAR}` substitution in the YAML **and** `env_file: .env` for container runtime vars. No manual copy needed on the server — the push handles it.

### Traefik dynamic config
- `hermes.murs-local.net` → `http://192.168.1.63:9119`
- `odysseus.murs-local.net` → `http://192.168.1.63:7000`

IPs are deliberate here — Traefik is on .62 and can't resolve Docker service names on .63's networks. `local-llm` also resolves to .63 from .62 (confirmed via ping) but IPs are preferred in the dynamic config.

### `write-docker-compose` skill improvements
Added two new steps to `~/.claude/skills/write-docker-compose/SKILL.md`:
- **Step 6 — IP address audit**: replace `0.0.0.0`/literal LAN IPs in port binds with `${BIND_IP}`; replace inter-container IP URLs with service names; flag `localhost` in cross-container env vars
- **Step 7 — Secrets extraction**: move literal passwords/keys/tokens to env vars

---

## Pre-deployment checklist

### On .63 — create volume directories
```bash
mkdir -p /mnt/ai-files/hermes/data
mkdir -p /mnt/ai-files/odysseus/data
mkdir -p /mnt/ai-files/odysseus/logs
mkdir -p /mnt/ai-files/odysseus/chromadb
```

### Pull the embedding model into Ollama (required before Odysseus first boot)
```bash
docker exec ollama ollama pull all-minilm:l6-v2
```

### Push files to .63 (from WSL on your workstation)
```bash
python push_config.py --id 5   # hermes config.yaml → /mnt/ai-files/hermes/data/
python push_config.py --id 6   # hermes compose + .env
python push_config.py --id 7   # odysseus compose + .env
python push_config.py --id 2   # traefik dynamic config (hermes + odysseus routes)
```

### Deploy

**Option A — manually on .63:**
```bash
cd /opt/stacks/hermes && docker compose up -d
cd /opt/stacks/odysseus && docker compose up -d
```

**Option B — via Komodo on .62:**
Add both stacks in Komodo pointing to `/opt/stacks/hermes` and `/opt/stacks/odysseus` on .63 via the Periphery agent.

---

## Known issues / things to verify

1. **Odysseus healthcheck on `/`** — if it redirects to `/login`, `curl -fs` still passes (follows redirect). If it returns non-2xx, the container will loop unhealthy. Check `docker inspect ai-odysseus --format '{{json .State.Health}}'` after first boot and consider switching to a dedicated `/health` or `/api/health` endpoint if one exists.

2. **Odysseus build time** — first `docker compose up` will clone from GitHub and build the image. This takes time. Komodo's timeout may need increasing for first deploy.

3. **Hermes config path** — Hermes reads its LLM config from `/opt/data/config.yaml` inside the container, mapped to `/mnt/ai-files/hermes/data/config.yaml` on the host. Confirm the file is present before starting.

4. **`all-minilm:l6-v2` must be pulled first** — Odysseus calls Ollama's embeddings endpoint on startup. If the model isn't present, Odysseus will fail to initialise its vector store.

5. **COMFYUI_WORKFLOW_NODES** — still requires one manual setup in Open WebUI UI after a fresh install (node mapping for Animagine XL prompt/model/size/steps nodes). See `compose/comfyui/workflows/animagine-xl-4.0-workflow.cfg` for the values to enter.

---

## Pending (from earlier handoff, still open)

- Lock signups in Open WebUI (`ENABLE_SIGNUP: "false"` in `compose.yml`) after second user account is created
- Remove stale Authentik router from Traefik dynamic config (was using old internal Traefik)

---

## Suggested skills

- `/write-docker-compose` — if adjusting either compose file before deploying (Steps 6 & 7 are now active)
