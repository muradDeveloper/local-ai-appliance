# CLAUDE.md

> **Global instructions take priority.** The user's global `~/.claude/CLAUDE.md` and all files under `~/.claude/rules/` apply first. Project-level guidance below extends or refines those rules but never overrides them.

Guidance for Claude Code when working in this repository.

## Project purpose

This repository deploys and documents an internal-only local AI appliance on a Proxmox Ubuntu VM. It is designed for two trusted users and an RTX 3060 12 GB GPU. The stack comprises Authentik, Open WebUI, Ollama, PostgreSQL, Redis, faster-whisper and Kokoro.

DNS routing and TLS termination are handled by an **external Traefik instance** (not managed in this repo). Services in this stack expose ports on the LAN IP so the external Traefik can proxy to them.

## Non-negotiable architectural constraints

- Do not expose any service directly to the public Internet — all external access goes through the external Traefik instance.
- Services that need to be reachable by the external Traefik must bind on the LAN IP (`192.168.1.63`) with explicit host ports. Do not bind on `0.0.0.0`.
- Ollama, PostgreSQL, Redis, faster-whisper and Kokoro must remain on private Docker networks with no host port binding.
- Authentik is the identity provider. Open WebUI remains the application authorisation boundary.
- Do not replace OIDC with proxy-header authentication unless an ADR explicitly approves it.
- Do not commit secrets, private keys, database dumps, access tokens or real hostnames.
- Do not introduce cloud LLM providers by default.
- Preserve separate persistent data for Open WebUI, Authentik, PostgreSQL, knowledge documents and Ollama.
- Backups must remain application-consistent and restorable independently of PBS VM backups.
- Do not remove `AUTHENTIK_LISTEN__HTTP` or `AUTHENTIK_LISTEN__HTTPS` from the Authentik service environment. Authentik 2026.5.x changed its default listen address to `[::]` (IPv6); these env vars restore the IPv4 binding required on IPv6-disabled hosts.

## Pre-change archiving

Only archive when the user explicitly asks. When asked, copy the current version of each file being modified to:

```
archive/backup-YYYY-MM-DD-before-<short-change-slug>/
```

- Use today's date in `YYYY-MM-DD` format.
- The slug should be kebab-case and describe what is about to change (e.g. `open-webui-native-auth`, `traefik-removal`, `postgres-upgrade`).
- Archive every file that will be modified in that change — at minimum `compose.yml` and any env file touched.
- One archive folder per logical change, not per file edit within a change.
- `archive/` is **not** gitignored at the folder level. Files inside it follow their own `.gitignore` rules — `env_var.cfg` copies are already gitignored by the root pattern and will not be committed. `compose.yml` copies will be committed and serve as a readable before-snapshot.
- Never commit secrets into the archive. If in doubt, check `.gitignore` before writing.

## Preferred change style

1. Read `README.md`, `docs/ARCHITECTURE.md` and `docs/DECISIONS.md`.
2. Make the smallest safe change.
3. Update documentation and examples in the same commit.
4. Validate Compose:
   ```bash
   docker compose --env-file env_var.cfg config >/dev/null
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
- Pin images to tested release tags before production. Reference the image via a variable in `.env` / `.env.example` (e.g. `image: ${SEARXNG_IMAGE}`). Never hardcode an image tag directly in `compose.yml`.
- Set `restart: unless-stopped`.
- Add health checks when the image provides a reliable endpoint.
- Use `expose` for purely internal ports. Use `ports` with a specific LAN IP (`192.168.1.63:<host>:<container>`) for any service that the external Traefik needs to reach. Never bind on `0.0.0.0`.
- Use named networks with clear trust boundaries.
- Avoid mounting the raw Docker socket into unrelated containers.

### Mandatory checklist for every new service block

1. **Image** — variable from `.env`: `image: ${SERVICE_IMAGE}` with a pinned tag in `.env.example`.
2. **Environment variables** — all values from `.env` via `${VAR}`. No literals for secrets or hostnames.
3. **Persistent volumes** — AI application data mounts under `/mnt/ai-files/<service>/` on the host (e.g. `- /mnt/ai-files/searxng/data:/var/cache/searxng`). Config-only mounts (e.g. `./searxng:/etc/searxng`) are fine as repo-relative paths.
4. **Health check** — required. Use `curl`, `wget`, or the image's own probe. Set `interval`, `timeout`, `retries`, and `start_period`.
5. **Networks** — join only the networks the service actually needs (`proxy` for LAN-reachable services, `backend` for app-tier, `database` only if it talks to Postgres/Redis).

## Secret handling

- `.env` is ignored by Git.
- `env_var.cfg` is the local environment file. `env_var.cfg` must never be committed.
- Generate secrets with `scripts/generate-secrets.sh`.
- Never echo secret values to logs.
- Backup secrets only into the encrypted backup repository.
- A secret rotation requires a documented rollback plan.

## Screenshots and screen captures

- Always save screenshots to `.scratch/` in the project root — never to system temp dirs or `scripts/`.
- Use a descriptive subdirectory name that reflects the purpose, e.g. `.scratch/oidc-manual/`, `.scratch/open-webui-manual/`, `.scratch/debug-YYYY-MM-DD/`.
- Within each subdirectory, name files sequentially with a short slug: `01-authentik-login.png`, `02-provider-create.png`, etc.
- Never reuse a subdirectory for a different topic — create a new one.
- `.scratch/` is gitignored; never commit screenshots.

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
- No replacing backups with VM snapshots.
- No claiming recovery works without a documented restore test.
- No disabling TLS on the external Traefik merely to fix an OIDC redirect.

---

## Archived (no longer active)

> These rules applied when this stack ran its own internal Traefik instance. TLS termination and routing are now handled by an external Traefik. Kept for reference if an internal Traefik is ever restored.

### Internal Traefik — architectural constraint (archived)

- Only the internal Traefik may publish LAN-facing ports, normally TCP 80 and 443.

### Internal Traefik — compose conventions (archived)

- Use `expose` for internal ports and `ports` only for the internal Traefik container.
- Set Traefik Docker provider `exposedByDefault=false`.
- Add `traefik.enable=true` only to intentionally routed services.
- Prefer a restricted socket proxy in a hardened production revision.

### Internal Traefik — mandatory checklist item (archived)

**Traefik labels** — required for any LAN-facing service when using an internal Traefik. Minimum set:
```yaml
labels:
  - traefik.enable=true
  - traefik.docker.network=ai_proxy
  - traefik.http.routers.<name>.rule=Host(`${<NAME>_FQDN}`)
  - traefik.http.routers.<name>.entrypoints=websecure
  - traefik.http.routers.<name>.tls=true
  - traefik.http.routers.<name>.tls.certresolver=letsencrypt
  - traefik.http.services.<name>.loadbalancer.server.port=<port>
```
Internal-only services omit Traefik labels entirely and must not join the `proxy` network.
