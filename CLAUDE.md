# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project purpose

This repository deploys and documents an internal-only local AI appliance on a Proxmox Ubuntu VM. It is designed for two trusted users and an RTX 3060 12 GB GPU. The stack comprises Traefik, Authentik, Open WebUI, Ollama, PostgreSQL, Redis, Mem0, faster-whisper and Kokoro.

## Non-negotiable architectural constraints

- Do not expose Open WebUI, Authentik, Traefik dashboard, Ollama, PostgreSQL, Redis, Mem0, faster-whisper or Kokoro directly to the public Internet.
- Only Traefik may publish LAN-facing ports, normally TCP 80 and 443.
- Ollama, PostgreSQL, Redis, Mem0, faster-whisper and Kokoro must remain on private Docker networks.
- Authentik is the identity provider. Open WebUI remains the application authorisation boundary.
- Do not replace OIDC with proxy-header authentication unless an ADR explicitly approves it.
- Do not commit secrets, private keys, database dumps, access tokens or real hostnames.
- Do not introduce cloud LLM providers by default.
- Preserve separate persistent data for Open WebUI, Authentik, PostgreSQL, knowledge documents and Ollama.
- Backups must remain application-consistent and restorable independently of PBS VM backups.
- Do not remove `AUTHENTIK_LISTEN__HTTP` or `AUTHENTIK_LISTEN__HTTPS` from the Authentik service environment. Authentik 2026.5.x changed its default listen address to `[::]` (IPv6); these env vars restore the IPv4 binding required on IPv6-disabled hosts.

## Preferred change style

1. Read `README.md`, `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`.
2. Make the smallest safe change.
3. Update documentation and examples in the same commit.
4. Validate Compose:
   ```bash
   docker compose --env-file .env.example config >/dev/null
   ```
5. Validate shell scripts:
   ```bash
   find scripts backup restore -type f -name '*.sh' -print0 | xargs -0 -n1 bash -n
   ```
6. Never silently broaden network exposure.
7. Use placeholders for environment-specific values.
8. Keep commands suitable for Ubuntu Server and Proxmox.

## Compose conventions

- Use Compose specification syntax without a top-level `version`.
- Pin images to tested release tags before production.
- Set `restart: unless-stopped`.
- Add health checks when the image provides a reliable endpoint.
- Use `expose` for internal ports and `ports` only for Traefik.
- Use named networks with clear trust boundaries.
- Set Traefik Docker provider `exposedByDefault=false`.
- Add `traefik.enable=true` only to intentionally routed services.
- Avoid mounting the raw Docker socket into unrelated containers.
- Prefer a restricted socket proxy in a hardened production revision.

## Secret handling

- `.env` is ignored by Git.
- `.env.example` contains placeholders only.
- Generate secrets with `scripts/generate-secrets.sh`.
- Never echo secret values to logs.
- Backup secrets only into the encrypted backup repository.
- A secret rotation requires a documented rollback plan.

## Documentation rules

- Australian English.
- Dates use `dd/mm/yyyy` where written for people.
- Shell commands should include short comments when they are not self-evident.
- Update both Markdown and HTML installation guides when changing installation steps.
- Record architectural changes in `docs/decisions/`.

## Testing expectations

At minimum:

```bash
docker compose config
bash -n scripts/*.sh backup/*.sh restore/*.sh
```

For network changes, confirm:

```bash
docker compose ps
docker network inspect ai_proxy
docker network inspect ai_backend
docker network inspect ai_database
```

For GPU changes, confirm:

```bash
nvidia-smi
docker run --rm --gpus all ubuntu:24.04 nvidia-smi
docker exec ollama ollama ps
```

## Forbidden shortcuts

- No `latest` tag in a production-ready pull request.
- No public `11434:11434`.
- No public PostgreSQL port.
- No default passwords.
- No disabling TLS merely to fix an OIDC redirect.
- No replacing backups with VM snapshots.
- No claiming recovery works without a documented restore test.
