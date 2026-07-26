# Architecture

![Internal Local-AI Appliance](images/architecture.png)

## Physical platform

- Proxmox VE host
- AMD Ryzen 5 5500: 6 cores / 12 threads
- NVIDIA RTX 3060 12 GB
- 32 GB DDR4
- Ubiquiti gateway in front of the LAN
- Synology storage and Proxmox Backup Server available for backups

## VM boundary

The appliance runs in a dedicated Ubuntu Server VM:

| Resource | Initial allocation |
|---|---:|
| CPU type | host |
| vCPU | 8 |
| RAM | 24 GB, ballooning disabled |
| OS disk | 80 GB |
| Data disk | 500 GB–1 TB |
| GPU | Full PCIe passthrough |
| Firmware | OVMF/UEFI |
| Machine | q35 |

This intentionally leaves host resources available for Proxmox.

## Service responsibilities

### Traefik

- Only LAN-facing container.
- Terminates TLS; certificates issued and renewed automatically via Let's Encrypt DNS-01 (Cloudflare provider).
- Routes `ai.murs-local.net` to Open WebUI.
- Routes `auth.murs-local.net` to Authentik.
- Uses explicit opt-in labels with `exposedByDefault=false`.
- API and dashboard disabled.

### Authentik

- Identity provider.
- OIDC login for Open WebUI.
- Maintains users, groups and optional MFA.
- Does not decide which Open WebUI models or knowledge collections a user may access.

### Open WebUI

- User interface.
- OIDC-only login; native login form disabled.
- Application-level roles and groups; role assigned automatically from Authentik `groups` claim.
- Chat history.
- Per-user memory (supplemented by Mem0 long-term memory layer).
- Shared and private knowledge/RAG collections; knowledge volume mounted read-only.
- STT via faster-whisper; TTS via Kokoro — both over the private backend network.
- Connects to Ollama over a private Docker network.

### Ollama

- Local inference server.
- Uses the RTX 3060 through NVIDIA Container Toolkit.
- Not exposed to the LAN.
- Limited to one loaded model and one parallel generation.
- Default context 32K; flash attention enabled; cloud features disabled.

### Redis

- Session cache and task queue for Authentik.
- Private Docker network only.
- No published ports.

### PostgreSQL

- Durable state for Open WebUI, Authentik, and Mem0.
- Separate databases and credentials per application.
- Uses `pgvector/pgvector:pg17` image; the `vector` extension is enabled in the Mem0 database on initialisation.
- Private Docker network only.
- Backed up with `pg_dump`.

### faster-whisper

- OpenAI-compatible speech-to-text server.
- Runs on CPU; no GPU allocation.
- Accessible inside the stack at `http://faster-whisper:8000/v1`.
- Not reachable from the LAN.
- Model: `Systran/faster-whisper-medium`.

### Kokoro

- OpenAI-compatible text-to-speech server (Kokoro-82M).
- Runs on CPU; no GPU allocation. Voice models download on first start (~5 GB image).
- Accessible inside the stack at `http://kokoro:8880/v1`.
- Not reachable from the LAN.
- Default voice: `af_bella`. Supports standard OpenAI voice name aliases.

### Mem0

- Long-term memory layer for multi-session context.
- Uses Ollama for LLM-based memory extraction and nomic-embed-text for embeddings.
- Stores memories as vectors in the `mem0` PostgreSQL database via pgvector.
- Accessible inside the stack at `http://mem0:8000`.
- Not reachable from the LAN.

## Trust boundaries

1. **WAN boundary:** Ubiquiti denies inbound access; no port forwarding.
2. **LAN boundary:** only trusted LAN/VPN clients may reach TCP 443.
3. **Proxy boundary:** only explicitly labelled applications are routable.
4. **Identity boundary:** Authentik validates identity and group membership.
5. **Application boundary:** Open WebUI enforces model and knowledge access.
6. **Data boundary:** user-private memory and RAG are not shared.
7. **Backend boundary:** Ollama and PostgreSQL have no host-published ports.
8. **Backup boundary:** secrets and data leave the VM only inside encrypted backup storage.

## Data classification

| Data | Authority | Backup |
|---|---|---|
| Compose/configuration | Git repository | Git + encrypted backup |
| Secrets | `.env` / secret store | encrypted backup only |
| Open WebUI DB | PostgreSQL | nightly logical dump |
| Authentik DB | PostgreSQL | nightly logical dump |
| Original knowledge files | `knowledge/` | nightly |
| Embeddings/vector data | Open WebUI data | nightly |
| Mem0 memories (pgvector) | PostgreSQL | nightly logical dump |
| Ollama model blobs | Ollama volume | normally re-download |
| Model inventory | generated text file | nightly |
| Whole VM | Proxmox | weekly PBS |

## Growth path

Move Authentik to a separate infrastructure VM only when it protects several homelab services. Keep the AI VM self-contained initially because a separate identity VM does not improve availability when Open WebUI itself is unavailable.
