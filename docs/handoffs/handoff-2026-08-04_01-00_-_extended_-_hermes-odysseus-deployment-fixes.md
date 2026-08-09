# Handoff — Hermes & Odysseus Deployment Fixes
**Date:** 04/08/2026 01:00  
**Branch:** `setup/initial-deployment`

---

## Goal

Get the Hermes Agent and Odysseus stacks running on .63. Both stacks were created last session; this session diagnosed and fixed startup failures in both. Hermes is now running. Odysseus is configured but not yet deployed.

---

## Project location

Working dir: `C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance`

Read first:
- `CLAUDE.md` — project constraints and conventions
- `docs/handoffs/handoff-2026-08-03_08-39-deploying-hermes-and-odysseus.md` — previous session; deployment checklist still relevant

---

## Working agreement

See `CLAUDE.md`. Key points:
- Always use Context7 before touching image config, env vars, or compose blocks
- Use `/write-docker-compose` skill when creating or reviewing any service block
- Never bind on `0.0.0.0`; LAN-facing ports use `${BIND_IP}:host:container`
- No `init: true` on images that use s6-overlay as PID 1 (it conflicts)
- Secrets stay in `env_var.cfg` (gitignored); never committed

---

## Locked decisions

| Decision | Reason |
|---|---|
| `command: ["gateway", "run"]` on Hermes | Default entrypoint launches interactive TUI; exits immediately without a TTY |
| Basic auth for Hermes dashboard (not OAuth/--insecure) | `--insecure` deprecated in v0.16.0; public binds require an auth provider; Nous Portal OAuth needs an account |
| No `init: true` on Hermes | s6-overlay must be PID 1; tini/init conflicts with it and causes immediate crash |
| Healthcheck on `/health` not `/v1/models` | `/health` is the documented unauthenticated liveness probe (Context7 confirmed) |
| Odysseus builds from local clone at `/root/repos/odysseus` | User switched from GitHub URL build context in the IDE |

---

## Done

### Hermes — `compose/hermes/`

**`compose.yml`** — fully corrected:
- `command: ["gateway", "run"]` added (was missing; caused TUI exit loop)
- `init: true` removed (was added erroneously; conflicts with s6-overlay)
- `security_opt: no-new-privileges:true` added
- Healthcheck fixed: `/v1/models` → `/health`

**`env_var.cfg`** — dashboard basic auth added:
```
HERMES_DASHBOARD_BASIC_AUTH_USERNAME=admin
HERMES_DASHBOARD_BASIC_AUTH_PASSWORD=<redacted>
HERMES_DASHBOARD_BASIC_AUTH_SECRET=<redacted>
```
These satisfy the auth gate that blocks 0.0.0.0 binding when no provider is configured.

**Status: container running and healthy on .63** (user confirmed).

---

### Odysseus — `compose/odysseus/`

**`compose.yml`** — two fixes applied:
- YAML indentation bug fixed: `chromadb` was nested under `odysseus` as a property instead of being a sibling service (caused `mapping key "container_name" already defined` parse error)
- Build context switched to `context: /root/repos/odysseus` (local clone); GitHub URL commented out

**Status: not yet deployed.** Repo not yet cloned on .63.

---

## Next step

### 1. Deploy Odysseus on .63

```bash
# Clone the repo
git clone https://github.com/pewdiepie-archdaemon/odysseus.git --branch dev /root/repos/odysseus

# Push compose + env (if not already done via push_config.py)
python push_config.py --id 7   # odysseus compose + .env

# Deploy
docker compose -f /opt/stacks/odysseus/compose.yml up -d --build
```

Pre-flight (from previous handoff, still open):
```bash
# Create volume dirs if not already done
mkdir -p /mnt/ai-files/odysseus/{data,logs,chromadb}

# Pull embedding model into Ollama before first boot
docker exec ollama ollama pull nomic-embed-text
```

Check first-boot admin password:
```bash
docker logs ai-odysseus | grep -i password
```

### 2. Open question

The user had `open-webui-illustrious-anime-balanced-api.json` open in the IDE at end of session. Unknown if this is a new task for next session — ask before starting anything with it.

---

## Suggested skills

- `/write-docker-compose` — before touching any compose block
- `/context7-mcp` — before referencing any image tag, env var name, or config key

---

## What to avoid

- Do not reintroduce `init: true` to Hermes — s6-overlay is the init system
- Do not use `--insecure` flag for Hermes dashboard — it's deprecated and non-functional in v0.16.0+
- Do not use `/v1/models` as a healthcheck endpoint — requires auth; use `/health`
- Do not build Odysseus from the GitHub URL context — user has switched to local clone
- Do not add `ODYSSEUS_ADMIN_PASSWORD` to Odysseus env — first-admin is auto-generated and printed in logs

---

## How to respond

Start with 1–2 lines confirming you understand: Hermes is running; Odysseus needs its repo cloned and stack deployed. Then ask about the `open-webui-illustrious-anime-balanced-api.json` file before doing anything else.
