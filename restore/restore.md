# Restore procedure

Never restore directly over a running production stack.

1. Restore the repository and `.env` from the encrypted backup.
2. Create a new Ubuntu VM or an isolated restore VM.
3. Install Docker, NVIDIA Container Toolkit and Restic.
4. Start PostgreSQL only:
   ```bash
   docker compose up -d postgres
   ```
5. Restore the two PostgreSQL dumps with `pg_restore`.
6. Restore Open WebUI, Authentik and knowledge volumes/files.
7. Start the full stack.
8. Re-download models listed in `model-inventory.txt`.
9. Verify Authentik login, Open WebUI RBAC, private chats and RAG.
10. Only then replace the failed production VM or update DNS.

See `docs/BACKUP-RESTORE.md` for detailed commands.
