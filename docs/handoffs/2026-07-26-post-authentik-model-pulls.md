# Handoff — 26/07/2026 — Post-Authentik / Model Pulls

## What was accomplished this session

- Set passwords for all three new users: `mursadmin`, `murs`, `alaa`
- Confirmed Open WebUI is up — "Continue with Authentik" OIDC button visible at `https://ai.murs-local.net`
- Researched and confirmed explicit quantization tags for all planned Ollama models (see model list below)
- **Root-caused and fixed Docker DNS failure**: `ai_backend` network had `internal: true` in `compose.yml`, which blocks all outbound internet traffic. Removed `internal: true` from `ai_backend` (kept on `ai_database`). Recreated the network via `docker compose down ollama speaches open-webui && docker network rm ai_backend && docker compose up -d`.
- Model pulls started — still in progress at end of session
- Wrote `docs/AUTHENTIK-SETUP.md` — full step-by-step Authentik OIDC setup manual from 22 screenshots in `.scratch/manual/`
- Captured screenshots 23–24 in `.scratch/manual/` covering the Open WebUI landing and "Get started" screens

## Confirmed model pull list

All tags verified against `ollama.com/library` on 26/07/2026:

| Pull tag | Size | Role |
|---|---|---|
| `nomic-embed-text` | 0.3 GB | Embeddings (RAG / future Mem0) |
| `qwen2.5-coder:14b-instruct-q4_K_M` | 9.0 GB | Primary coding + future Mem0 LLM |
| `deepseek-r1:14b-qwen-distill-q4_K_M` | 9.0 GB | Reasoning |
| `qwen3:14b-q4_K_M` | 9.3 GB | Hybrid thinking/chat |
| `gemma3:12b-it-qat` | 8.1 GB | General (QAT preserves quality) |
| `gemma4:e4b-it-qat` | 6.1 GB | Efficient multimodal (same model as `gemma4:latest`) |
| `command-r7b-arabic:7b-02-2025-q4_K_M` | 5.1 GB | Arabic language |
| `llama3.1:8b-instruct-q4_K_M` | 4.9 GB | General baseline |
| `hermes3:8b-llama3.1-q4_K_M` | 4.9 GB | Quick tasks / function calling |
| `phi4-mini-reasoning:3.8b-q4_K_M` | 3.2 GB | Small reasoning |
| `smallthinker:3b-preview-q4_K_M` | 2.1 GB | Tiny reasoning |

Note: "Qwen3.6-27B-Dense" from prior planning does not exist on Ollama. All `qwen3:30b` variants are MoE, not dense, and at 19 GB exceed 12 GB VRAM.

Verify pulls completed with:
```bash
docker exec ollama ollama list
```

Re-run any that failed:
```bash
docker exec ollama sh -c "
  ollama pull nomic-embed-text ;
  ollama pull qwen2.5-coder:14b-instruct-q4_K_M ;
  ollama pull deepseek-r1:14b-qwen-distill-q4_K_M ;
  ollama pull qwen3:14b-q4_K_M ;
  ollama pull gemma3:12b-it-qat ;
  ollama pull gemma4:e4b-it-qat ;
  ollama pull command-r7b-arabic:7b-02-2025-q4_K_M ;
  ollama pull llama3.1:8b-instruct-q4_K_M ;
  ollama pull hermes3:8b-llama3.1-q4_K_M ;
  ollama pull phi4-mini-reasoning:3.8b-q4_K_M ;
  ollama pull smallthinker:3b-preview-q4_K_M
"
```

## Current container state

All containers should be running after `docker compose up -d`. Verify with `docker compose ps`.

Known issue: `ai-authentik-worker` may still be absent — see item 2 below.

## Pending items (priority order)

### 1. Verify OIDC login end-to-end (HIGH)
Never actually clicked through the login flow. Must confirm:
- "Continue with Authentik" → Authentik consent screen → redirect back to Open WebUI
- `mursadmin` lands as admin role
- `murs` or `alaa` lands as regular user role
- Role mapping env vars: `OAUTH_ADMIN_ROLES: ai-admins`, `OAUTH_ALLOWED_ROLES: ai-admins,ai-users`

### 2. Fix authentik-worker not starting (HIGH)
`authentik-server` `start_period` is 60s in `compose.yml` — too short for fresh DB migrations. Worker is blocked by `service_healthy` dependency.

Fix in `compose.yml`:
```yaml
authentik-server:
  healthcheck:
    start_period: 120s   # was 60s
```

Then:
```bash
docker compose up -d authentik-worker
```

### 3. Confirm model pulls completed
```bash
docker exec ollama ollama list
```
Re-run the pull command above for any missing models.

### 4. Pre-warm Speaches
First TTS/STT request triggers a slow HuggingFace download. Pre-warm from the server:
```bash
curl -s http://$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' ai-speaches):8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{"model":"speaches-ai/Kokoro-82M-v1.0-ONNX","voice":"af_bella","input":"Warming up."}' \
  --output /dev/null
```

### 5. Write Open WebUI user manual
Screenshots 23–24 in `.scratch/manual/` cover the login screen. Need to walk through the full UI (model selection, chat, settings, admin panel) and capture more screenshots. Manual should be saved to `docs/OPEN-WEBUI-GUIDE.md`.

### 6. Add missing healthchecks to compose.yml
- `portainer` — no healthcheck
- `authentik-worker` — no healthcheck

### 7. Git push to GitHub
No commits have been pushed to `https://github.com/muradDeveloper/local-ai-appliance.git`.
Changes to commit include: `compose.yml` (`internal: true` removal, any healthcheck fixes), `docs/AUTHENTIK-SETUP.md`, `docs/handoffs/`.

Use `/commit-commands:commit-push-pr` skill.

## Key files

| File | Purpose |
|---|---|
| `compose.yml` | Full service definitions — `ai_backend` no longer internal |
| `docs/AUTHENTIK-SETUP.md` | Authentik OIDC setup manual (complete) |
| `docs/handoffs/2026-07-26-initial-deployment.md` | Previous session handoff |
| `.scratch/manual/` | 24 screenshots — 01–22 Authentik setup, 23–24 Open WebUI landing |
| `.env` / `env_var.cfg` | Identical — `OAUTH_CLIENT_SECRET` set correctly |

## Architectural notes

- `ai_database` network remains `internal: true` — Postgres and Redis have no need for internet
- `ai_backend` network is now internet-capable — required for Ollama model pulls and Speaches HuggingFace downloads
- All services still unexposed externally; only Traefik publishes ports 80/443

## Suggested skills

- `/handoff` — if continuing across another session
- `/commit-commands:commit-push-pr` — to push accumulated changes once OIDC login is verified
- `/context7-mcp` — before touching any image version or config schema
