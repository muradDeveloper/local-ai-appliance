# Server Directory Layout

The stack uses two root locations on the Proxmox Ubuntu VM:

| Path | Purpose |
|---|---|
| `/opt/local-ai-appliance/` | Project files — compose, scripts, config, docs |
| `/mnt/ai-files/` | Persistent data volumes — one subdirectory per service |

`/mnt/ai-files/` should be on a separate disk or ZFS dataset from the OS.

---

## Project directory — `/opt/local-ai-appliance/`

SFTP the repo contents here. This is where you run all commands from.

```
/opt/local-ai-appliance/
├── compose.yml               # docker compose up -d
├── .env                      # secrets — never commit (copy from env_var.cfg)
├── backup/
│   └── backup.sh
├── restore/
│   └── restore.md
├── scripts/
│   ├── preflight.sh          # run before first boot
│   ├── generate-secrets.sh
│   ├── health-check.sh
│   ├── update.sh
│   └── various-commands.sh
├── compose/
│   ├── traefik/certs/        # local TLS certs if not using ACME
│   └── postgres/init/
│       └── 01-create-databases.sh   # copied to /mnt/ai-files/postgres/init/
├── config/
│   └── examples/
│       └── traefik-tls.yml.example
├── docs/
└── knowledge/
```

---

## Data directory — `/mnt/ai-files/`

### Create all directories

```bash
mkdir -p /mnt/ai-files/{traefik/{dynamic,acme},redis/data,postgres/init,ollama/data,speaches/models,authentik/{media,templates,certs},open-webui/{data,knowledge},portainer/data}
```

### Directory reference

```
/mnt/ai-files/
├── traefik/
│   ├── dynamic/          # Traefik dynamic config files (e.g. TLS cert config)
│   └── acme/             # Let's Encrypt ACME storage (acme.json — see below)
├── redis/
│   └── data/             # Redis AOF/RDB persistence
├── postgres/
│   ├── 18/               # PostgreSQL 18 data files — created automatically by PG18
│   └── init/             # Initialisation scripts run once on first startup
│                         # Copy compose/postgres/init/01-create-databases.sh here
│                         # Note: mount is /mnt/ai-files/postgres:/var/lib/postgresql
│                         # PG18+ manages its own versioned subdirectory
├── ollama/
│   └── data/             # Ollama model blobs and manifests
├── speaches/
│   └── models/           # Speaches HuggingFace model cache (Whisper + Kokoro)
│                         # Downloaded automatically on first request
├── authentik/
│   ├── media/            # Authentik uploaded media (avatars, icons)
│   ├── templates/        # Custom Authentik email/UI templates
│   └── certs/            # Authentik worker signing certificates
├── open-webui/
│   ├── data/             # Open WebUI app data (Chroma vector store, uploads)
│   └── knowledge/        # Knowledge documents mounted read-only into Open WebUI
└── portainer/
    └── data/             # Portainer state and TLS certificates
```

### Files to copy after creating directories

| Source (repo) | Destination (server) |
|---|---|
| `compose/postgres/init/01-create-databases.sh` | `/mnt/ai-files/postgres/init/01-create-databases.sh` |
| `config/examples/traefik-tls.yml.example` | `/mnt/ai-files/traefik/dynamic/tls.yml` *(only if using local certs instead of ACME)* |

### acme.json permissions

Traefik requires `acme.json` to be pre-created with strict permissions or it will refuse to start:

```bash
touch /mnt/ai-files/traefik/acme/acme.json
chmod 600 /mnt/ai-files/traefik/acme/acme.json
```

---

## Backup target

The restic backup repository is separate from application data:

```
/mnt/tower-backups/
└── ai-backups/           # Restic repository — typically a CIFS/NFS share from the tower
```

Ensure this share is mounted before running `backup/backup.sh`.
