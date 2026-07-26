# Local AI Appliance

A private, two-user local LLM platform designed for a Proxmox homelab with:

- AMD Ryzen 5 5500
- NVIDIA GeForce RTX 3060 12 GB
- 32 GB DDR4 RAM
- Ubuntu Server VM on Proxmox
- Docker Compose
- Traefik for internal HTTPS and container routing
- Authentik for OIDC SSO, groups and optional MFA
- Open WebUI for the user interface, application RBAC, chat history, personal memory and RAG
- Ollama for local GPU-backed inference
- PostgreSQL for durable application data
- Synology application backups plus Proxmox Backup Server VM backups

![Architecture](docs/images/architecture.png)

## Design goals

1. No direct Internet exposure.
2. Only trusted internal users or users connected through an approved VPN.
3. Two users maximum, with an administrator and a standard-user role.
4. Authentik performs authentication; Open WebUI enforces application permissions.
5. Ollama and PostgreSQL are never published to the LAN.
6. Chat history, memory and knowledge data are persistently stored and backed up.
7. The installation is reproducible and recoverable without backing up downloadable model blobs.
8. Configuration lives in Git; secrets do not.

## Repository status

This repository is a **deployment scaffold and operations manual**. Before first deployment:

- choose real internal DNS names;
- create or supply internal TLS certificates;
- pin tested image versions;
- generate strong secrets;
- review the example Compose file;
- verify PCIe passthrough on the target Proxmox host.

See [Installation Guide](docs/INSTALLATION.md).

## Quick start

```bash
git clone <your-repository-url> local-ai-appliance
cd local-ai-appliance

cp .env.example .env
cp config/examples/traefik-tls.yml.example compose/traefik/dynamic/tls.yml

./scripts/generate-secrets.sh
nano .env

docker compose config
docker compose up -d
```

Do not run the stack before completing the Proxmox, GPU, DNS and TLS sections of the installation guide.

## Documentation map

| Document | Purpose |
|---|---|
| [INSTALLATION.md](docs/INSTALLATION.md) | Complete installation procedure |
| [INSTALLATION.html](docs/INSTALLATION.html) | Styled offline installation guide |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, trust boundaries and data flows |
| [DECISIONS.md](docs/DECISIONS.md) | Consolidated decision record |
| [SECURITY.md](docs/SECURITY.md) | Security controls and firewall policy |
| [BACKUP-RESTORE.md](docs/BACKUP-RESTORE.md) | Backup, retention and recovery |
| [OPERATIONS.md](docs/OPERATIONS.md) | Routine administration |
| [MODEL-GUIDE.md](docs/MODEL-GUIDE.md) | Model sizing for a 12 GB RTX 3060 |
| [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) | Common failures and diagnostic commands |
| [CLAUDE.md](CLAUDE.md) | Instructions for Claude Code |
| [AGENTS.md](AGENTS.md) | Repository rules for coding agents |

## Directory structure

```text
local-ai-appliance/
├── .env.example
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── LICENSE
├── README.md
├── compose.yml
├── backup/
├── compose/
│   ├── authentik/
│   ├── ollama/
│   ├── open-webui/
│   ├── postgres/
│   └── traefik/
├── config/examples/
├── docs/
│   ├── decisions/
│   ├── images/
│   ├── reference/
│   ├── runbooks/
│   └── security/
├── restore/
└── scripts/
```

## Important operational rule

Run only one active model initially and use an 8K context. Two users may be logged in concurrently, but begin with one generation at a time to avoid VRAM pressure.

## Licence

MIT. See [LICENSE](LICENSE).
