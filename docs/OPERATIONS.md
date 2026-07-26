# Operations

## Daily

- Confirm Open WebUI login works.
- Review container health only when alerted.
- Confirm nightly backup completed.
- Confirm STT/TTS voice pipeline health (faster-whisper and Kokoro containers show healthy in `docker compose ps`).

## Weekly

```bash
docker compose ps
./scripts/health-check.sh
restic snapshots
docker compose logs faster-whisper --tail=50
docker compose logs kokoro --tail=50
```

Review disk consumption:

```bash
df -h
docker system df
```

Note: the Kokoro image includes pre-downloaded voice models (~5 GB). On first start after a fresh pull it may take up to 60 seconds to become healthy.

## Monthly

- Install Ubuntu security updates.
- Review Authentik users and group membership.
- Review Open WebUI model and knowledge permissions.
- Remove unused models.
- Review failed login events.
- Confirm PBS retention.
- Review Mem0 memory growth in the PostgreSQL `mem0` database.

## Upgrade procedure

1. Read release notes.
2. Create application backup.
3. Trigger PBS backup.
4. Pin intended image tags.
5. Pull images.
6. Start with one Open WebUI worker.
7. Check migrations and logs.
8. Verify OIDC, RBAC, chat and RAG.
9. Retain old backup until the next successful backup cycle.

```bash
./backup/backup.sh
./scripts/update.sh
docker compose logs --tail=200
```

## Model management

```bash
# List installed models.
docker exec ollama ollama list

# Pull required models for Mem0.
docker exec ollama ollama pull qwen2.5-coder:14b-instruct-q4_K_M
docker exec ollama ollama pull nomic-embed-text:latest

# Remove an unused model.
docker exec ollama ollama rm MODEL_NAME
```

See `docs/MODEL-GUIDE.md` for the full inference model roster and VRAM profiles.

## Voice pipeline

Both voice services run on CPU. No GPU interaction is required to check them.

Check faster-whisper (STT):

```bash
# Should return {"status":"ok"} or similar.
docker exec ai-faster-whisper curl -fs http://localhost:8000/health
```

Check Kokoro (TTS):

```bash
# Should return a JSON list of available voices.
docker exec ai-kokoro curl -fs http://localhost:8880/v1/audio/voices
```

If Kokoro is unhealthy on first start, wait up to 60 seconds. The container downloads voice model files before it begins accepting requests. Check progress with:

```bash
docker compose logs kokoro --tail=100
```

## User lifecycle

### Add

1. Create user in Authentik.
2. Add user to `ai-users`.
3. Confirm Open WebUI account creation through OIDC.
4. Apply Open WebUI group/model/knowledge permissions.
5. Test with the user.

### Remove

1. Disable the Authentik user.
2. Revoke sessions.
3. Decide whether to export or delete their Open WebUI data.
4. Remove group bindings.
5. Record the action.
