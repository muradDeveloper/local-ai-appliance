# AGENTS.md

Repository instructions for automated coding agents.

## Scope

These rules apply to the entire repository.

## Mission

Maintain a secure, reproducible, internal-only AI appliance for Proxmox. The target hardware is a Ryzen 5 5500, RTX 3060 12 GB and 32 GB system RAM. The stack comprises Traefik, Authentik, Open WebUI, Ollama, PostgreSQL, Redis, Mem0, faster-whisper and Kokoro.

## Required reading

Before editing:

1. `README.md`
2. `docs/ARCHITECTURE.md`
3. `docs/DECISIONS.md`
4. the relevant ADR under `docs/decisions/`
5. `docs/SECURITY.md` for any network, identity or secret change

## Safety invariants

- No WAN exposure.
- No anonymous signup.
- No direct LAN access to Ollama or databases.
- OIDC callback URLs must use HTTPS.
- Authentik groups identify users; Open WebUI permissions authorise resources.
- User-private memory and knowledge must not be intentionally shared.
- Shared knowledge is administrator-managed.
- Model files are replaceable artefacts; databases and source documents are authoritative data.
- Snapshots are not backups.
- Do not remove `AUTHENTIK_LISTEN__HTTP` or `AUTHENTIK_LISTEN__HTTPS` from the Authentik service environment. Authentik 2026.5.x changed its default listen address to `[::]` (IPv6); explicit IPv4 binding is required on IPv6-disabled hosts.
- Kokoro, faster-whisper and Mem0 must remain on private Docker networks with no published ports.

## Change checklist

- [ ] Change is within repository scope.
- [ ] No secret entered.
- [ ] Compose renders successfully.
- [ ] Shell scripts pass `bash -n`.
- [ ] Network exposure is unchanged or explicitly documented.
- [ ] Persistent volume implications are documented.
- [ ] Upgrade and rollback steps are included.
- [ ] Markdown and HTML installation docs remain aligned.
- [ ] Decision record updated where architecture changed.

## Commit guidance

Use concise conventional commit-style messages:

- `docs: clarify OIDC callback setup`
- `feat: add encrypted backup verification`
- `fix: keep Ollama API on backend network`
- `security: restrict Traefik dashboard`

## Review severity

Treat these as critical defects:

- committed secret;
- published Ollama or PostgreSQL port;
- open registration;
- Traefik API or dashboard enabled (`--api=false` is the required state);
- backup script that omits databases or the Open WebUI data volume;
- restore process that overwrites live data without confirmation;
- a routing rule that exposes the service beyond the intended LAN/VPN boundary.

## Known open items

These are deliberate deferrals, not oversights. Do not silently close them — raise with the owner before acting.

- **Traefik Docker socket proxy:** Traefik currently mounts the raw Docker socket (`/var/run/docker.sock:ro`). A restricted socket proxy (`tecnativa/docker-socket-proxy`) would reduce the blast radius of a Traefik compromise. Deferred until the stack is stable.
- **Traefik dashboard:** Disabled (`--api=false`). May be re-enabled behind an Authentik-protected route in a future revision. Requires a dedicated subdomain, router label, and forward-auth middleware.
- **Qdrant vector database:** Not added to the initial stack. Open WebUI currently uses embedded Chroma and Mem0 uses pgvector. Qdrant could replace one or both if vector search performance or dedicated collection management becomes a requirement. Evaluate after the stack is stable in production.
