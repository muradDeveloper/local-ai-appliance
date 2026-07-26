# Troubleshooting

## GPU is not visible

```bash
nvidia-smi
docker run --rm --gpus all ubuntu:24.04 nvidia-smi
docker inspect ollama --format '{{json .HostConfig.DeviceRequests}}'
```

If the second command fails, fix NVIDIA Container Toolkit before investigating Ollama.

## Open WebUI cannot reach Ollama

```bash
docker exec ai-open-webui getent hosts ollama
docker exec ai-open-webui python - <<'PY'
import urllib.request
print(urllib.request.urlopen("http://ollama:11434/api/tags", timeout=5).read().decode())
PY
```

Confirm both containers share `ai_backend`.

## Authentik fails to start or cannot bind port

Authentik 2026.5.x changed its default listening address to `[::]` (IPv6 only). On systems with IPv6 disabled this causes a bind failure.

Fix: ensure these are set in `.env` and the compose environment:

```text
AUTHENTIK_LISTEN__HTTP: 0.0.0.0:9000
AUTHENTIK_LISTEN__HTTPS: 0.0.0.0:9443
```

Check logs:

```bash
docker compose logs authentik-server --tail=50
```

## OIDC redirect loop

Check:

- browser trusts the TLS certificate;
- Authentik issuer URL matches `OPENID_PROVIDER_URL`;
- redirect URI is exactly `https://ai.murs-local.net/oauth/oidc/callback`;
- clocks and time zone are correct;
- DNS resolves both `ai.murs-local.net` and `auth.murs-local.net` to the AI VM;
- Open WebUI `WEBUI_URL` was set before SSO use.

## Traefik returns 404

```bash
docker compose logs traefik --tail=200
docker inspect ai-open-webui --format '{{json .Config.Labels}}'
docker network inspect ai_proxy
```

Confirm the host rule and Docker network label.

## PostgreSQL authentication failure

```bash
docker compose logs postgres --tail=200
docker exec ai-postgres psql -U postgres -c '\l'
```

The database initialisation scripts run only on a new empty data directory. Editing credentials after initial creation does not automatically change database users.

## STT not working (faster-whisper)

```bash
# Check the service is healthy.
docker compose ps faster-whisper

# Check logs for model load errors.
docker compose logs faster-whisper --tail=50

# Confirm the container is on ai_backend.
docker network inspect ai_backend | grep faster-whisper
```

Verify Open WebUI environment variables:

```text
AUDIO_STT_ENGINE=openai
AUDIO_STT_OPENAI_API_BASE_URL=http://faster-whisper:8000/v1
AUDIO_STT_MODEL=Systran/faster-whisper-medium
```

## TTS not working (Kokoro)

Kokoro downloads voice models on first start. The healthcheck has a 60-second start period — wait for it to pass before testing.

```bash
# Check healthcheck status.
docker compose ps kokoro

# Check download/startup progress.
docker compose logs kokoro --tail=100
```

Verify Open WebUI environment variables:

```text
AUDIO_TTS_ENGINE=openai
AUDIO_TTS_OPENAI_API_BASE_URL=http://kokoro:8880/v1
AUDIO_TTS_MODEL=tts-1
AUDIO_TTS_VOICE=af_bella
```

Test the endpoint directly from inside the stack:

```bash
docker exec ai-open-webui curl -fs http://kokoro:8880/v1/audio/voices
```

## Mem0 not saving memories

```bash
# Check service status.
docker compose ps mem0
docker compose logs mem0 --tail=50

# Confirm pgvector extension exists in the mem0 database.
docker exec ai-postgres psql -U postgres -d mem0 -c '\dx'

# Confirm Mem0 can reach Ollama.
docker exec ai-mem0 curl -fs http://ollama:11434/api/tags
```

If the `vector` extension is missing, the PostgreSQL init script did not run (data directory was not empty on first start). Drop and recreate the `mem0` database in an isolated environment and restart.

## Out of VRAM

- reduce context;
- use a smaller quantisation;
- stop parallel generations;
- unload the current model (`docker exec ollama ollama stop MODEL_NAME`);
- use only one model;
- restart Ollama after confirming no valuable request is running.

Note: Qwen3.6-27B Q3_K_M intentionally offloads ~1.5 GB to CPU RAM. This is expected and not an error. Check `ollama ps` to distinguish planned offload from unexpected VRAM exhaustion.

## Slow responses

Check whether the model is partly CPU-offloaded:

```bash
docker exec ollama ollama ps
nvidia-smi
docker stats
```

Large contexts and 27B models will show partial CPU offload. Generation speed for offloaded layers is reduced — this is a deliberate trade-off for quality over a full 12 GB GPU fit. If speed is critical, switch to a smaller model (Gemma 4 10B or Hermes 3 8B).
