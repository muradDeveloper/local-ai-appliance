# Consolidated decisions

## Final platform

- Proxmox VE with a dedicated Ubuntu Server VM.
- Full PCIe passthrough of the RTX 3060.
- Docker Compose inside the VM.
- No LXC for the first AI deployment.

## Reverse proxy

Traefik was selected rather than Caddy or Nginx because the stack is Docker-based and benefits from label-driven discovery. It remains local to the AI VM and is not a public edge proxy.

Multiple Traefik instances may exist elsewhere on the LAN because each VM has its own IP and DNS names.

## TLS

Let's Encrypt DNS-01 via Cloudflare is used instead of a private CA or self-signed certificates. Traefik handles issuance and renewal automatically using a Cloudflare API token scoped to the zone. This eliminates manual certificate management and CA root installation on client machines. Internal DNS resolution is handled by Ubiquiti local DNS overrides pointing both FQDNs to the VM LAN address; records are not proxied through Cloudflare.

## External exposure

There is none.

- No public DNS.
- No router port-forwarding.
- No Cloudflare Tunnel.
- No direct Internet login.
- Remote use, if ever required, must enter through an approved VPN.

## Identity and RBAC

- Authentik provides OIDC authentication, group membership and optional MFA.
- Open WebUI provides application RBAC and resource permissions.
- Direct native OIDC is preferred over Authentik forward-auth because Open WebUI supports OIDC.
- Open WebUI native login form is disabled; the only login path is OIDC via Authentik.
- Groups: `ai-admins` and `ai-users`.
- Authentik passes a `groups` claim in the OIDC token; Open WebUI maps `ai-admins` to admin role and `ai-users` to standard user role automatically.
- Administrator controls models, global knowledge and configuration.
- Standard user accesses approved models, private chats, personal memory and authorised knowledge.

## Memory

Memory is divided into:

1. private chat history;
2. private personal long-term memory;
3. administrator-managed shared knowledge/RAG;
4. user-private knowledge/RAG.

Secrets and highly sensitive credentials must never be stored in LLM memory.

## Persistence

- PostgreSQL from day one.
- Redis for Authentik session and task queue.
- Original documents retained separately from vector indexes.
- Model files treated as replaceable downloads.
- Separate OS and AI data disks.

## Backup

- Nightly application-consistent PostgreSQL and file backup to Synology.
- Weekly whole-VM backup to PBS.
- Pre-upgrade backup.
- Quarterly restore test.
- Models are re-downloaded from an inventory rather than routinely backed up.

## Voice pipeline

- faster-whisper (medium, CPU) provides OpenAI-compatible speech-to-text at `http://faster-whisper:8000/v1`.
- Kokoro-FastAPI (82M, CPU) provides OpenAI-compatible text-to-speech at `http://kokoro:8880/v1`.
- Both run on CPU to keep the full 12 GB VRAM budget available to Ollama.
- Open WebUI is wired to both endpoints via environment variables. Default TTS voice: `af_bella`.
- Kokoro maps standard OpenAI voice names (alloy, echo, fable, etc.) to its own voice set automatically.

## Model operating limits

- Primary size: 7B–9B Q4.
- Secondary size: approximately 12B Q4.
- Default context: 32K (`OLLAMA_CONTEXT_LENGTH=32768`). Safe for a 7B Q4 model on the RTX 3060 12 GB with flash attention enabled. Increase further by setting `OLLAMA_KV_CACHE_TYPE=q8_0`.
- One loaded model.
- One parallel generation.
- Maximum two human users.
- Ollama cloud features (remote inference, web search) are disabled via `OLLAMA_NO_CLOUD=1`.
- Flash attention is enabled via `OLLAMA_FLASH_ATTENTION=1` to reduce KV cache VRAM usage.

See the ADR files for the full rationale.

## Known open items

These are deliberate deferrals, not oversights.

- **Traefik Docker socket proxy:** Traefik currently mounts the raw Docker socket (`/var/run/docker.sock:ro`). A restricted socket proxy (`tecnativa/docker-socket-proxy`) would reduce the blast radius of a Traefik compromise. Deferred until the stack is stable in production.
- **Traefik dashboard:** Disabled (`--api=false`). May be re-enabled behind an Authentik-protected route in a future revision. Requires a dedicated subdomain, router label, and forward-auth middleware.
- **Qdrant vector database:** Not added to the initial stack. Open WebUI currently uses embedded Chroma and Mem0 uses pgvector. Qdrant could replace one or both if vector search performance or dedicated collection management becomes a requirement. Open WebUI supports Qdrant via `VECTOR_DB=qdrant`; Mem0 supports it natively. Evaluate after the stack is stable in production.
- **Mem0 user isolation and RBAC:** Mem0 has no built-in authentication. User memory isolation currently relies on two controls: (1) network isolation — Mem0 is on `ai_backend` only, unreachable from the LAN; (2) the Open WebUI pipeline function must extract the authenticated user identity from the Open WebUI session (sourced from the Authentik OIDC token `sub` claim) and pass it as `user_id` to Mem0, preventing a user from querying another user's memories. Authentik can add an authentication gate via a Proxy Outpost in front of Mem0 (blocking unauthenticated callers), but cannot enforce per-user memory scoping without a thin wrapper that extracts the `sub` claim from the validated JWT and uses it as the forced `user_id`. The Proxy Outpost approach is worth adding only if Mem0 gains clients beyond Open WebUI. Priority order: pipeline-enforced user_id first; Authentik Proxy Outpost later if needed.
