# Pre-upgrade runbook

- [ ] Read release notes.
- [ ] Check free disk space.
- [ ] Run `docker compose config`.
- [ ] Run application backup.
- [ ] Verify Restic snapshot.
- [ ] Trigger PBS backup.
- [ ] Record current image digests.
- [ ] Confirm rollback tags.
- [ ] Upgrade one layer at a time.
- [ ] Test OIDC, RBAC, model inference, memory and RAG.
- [ ] Test STT: record audio in Open WebUI and confirm transcription.
- [ ] Test TTS: send a message and confirm audio playback.
- [ ] Confirm Mem0 container is healthy and memories persist across sessions.
- [ ] Confirm Kokoro voice models are still loaded (check logs after restart — the container re-downloads models if the volume is absent).
