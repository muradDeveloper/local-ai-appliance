# local-ai-appliance — Implementation Plan

> **For agentic workers:** Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a private, GPU-accelerated AI appliance on a Proxmox Ubuntu VM — fully authenticated via Authentik OIDC, with persistent per-user memory, voice I/O, and verified nightly backups.

**Architecture:** Docker Compose on a single Ubuntu VM with PCIe GPU passthrough (RTX 3060 12 GB). Traefik handles TLS termination via Let's Encrypt DNS-01/Cloudflare. Authentik is the sole identity provider; all application login is OIDC-only. Mem0 provides long-term per-user memory injected into Open WebUI via a Filter plugin.

**Tech Stack:** Traefik v3.5, Authentik 2026.5.4, Open WebUI v0.10.1, Ollama 0.32.3, PostgreSQL 17 + pgvector, Redis 8, faster-whisper (CUDA), Kokoro-FastAPI (CPU), Mem0

## Global Constraints

- No WAN exposure — Traefik binds only to LAN IP `192.168.1.63`, ports 80/443
- Ollama, PostgreSQL, Redis, Mem0, faster-whisper, Kokoro must remain on private Docker networks
- OIDC only — native login form is disabled (`ENABLE_LOGIN_FORM: "false"`)
- No `:latest` tags in production — all images must be pinned before Phase 6
- `AUTHENTIK_LISTEN__HTTP: 0.0.0.0:9000` must remain — required on IPv6-disabled hosts (Authentik 2026.5.x changed default to `[::]`)
- Australian English in all documentation
- Markdown and HTML installation guides must stay in sync

---

## Pre-conditions

- Proxmox host running with RTX 3060 available for PCIe passthrough
- Cloudflare API token ready (DNS edit scope, zone `murs-local.net`)
- Ubiquiti local DNS overrides point `ai.murs-local.net` and `auth.murs-local.net` to `192.168.1.63`

---

## Phase −1 — Proxmox VM provisioning

**Goal:** Ubuntu Server VM running on Proxmox with static LAN IP, PCIe GPU passthrough active, Docker installed, and repository cloned.

**Minimum VM resource requirements:**

| Resource | Minimum | Notes |
|---|---|---|
| vCPUs | 8 | CPU type: `host` — required for GPU passthrough and AVX support |
| RAM | 32 GB | Ollama keeps models resident; Authentik and PostgreSQL each need headroom |
| OS disk | 32 GB | Thin-provisioned, local-lvm or ZFS |
| Data disk | 200 GB | Separate virtual disk mounted at `/var/lib/docker` — holds images, volumes, model weights |
| GPU | RTX 3060 12 GB | Full PCIe passthrough — not vGPU |
| Network | VirtIO | Static IP `192.168.1.63`; bridge to LAN |
| OS | Ubuntu Server 24.04 LTS | Minimal install; no desktop |

- [ ] **−1.1 Enable IOMMU on the Proxmox host**

  In `/etc/default/grub` on the Proxmox host add `intel_iommu=on iommu=pt` (Intel) or `amd_iommu=on iommu=pt` (AMD) to `GRUB_CMDLINE_LINUX_DEFAULT`, then:

  ```bash
  update-grub && reboot
  ```

  After reboot confirm IOMMU groups contain the RTX 3060:

  ```bash
  dmesg | grep -e DMAR -e IOMMU | head -20
  ```

- [ ] **−1.2 Create the VM in Proxmox**

  Via the Proxmox web UI or CLI:

  ```bash
  qm create 200 \
    --name ai-appliance \
    --cores 8 --cpu host \
    --memory 32768 \
    --net0 virtio,bridge=vmbr0 \
    --scsihw virtio-scsi-pci \
    --scsi0 local-lvm:32 \          # OS disk
    --scsi1 local-lvm:200 \         # Data disk
    --cdrom local:iso/ubuntu-24.04-live-server-amd64.iso \
    --boot order=ide2 \
    --ostype l26
  ```

  Adjust storage pool names to match your Proxmox configuration.

- [ ] **−1.3 Add PCIe passthrough for the RTX 3060**

  Find the PCI address of the GPU:

  ```bash
  lspci | grep -i nvidia
  ```

  Add the device to the VM (replace `01:00` with the address found above):

  ```bash
  qm set 200 --hostpci0 01:00,pcie=1,x-vga=0
  ```

  > `x-vga=0` keeps the Proxmox console on the host GPU. Set `x-vga=1` only if you intend this VM to own the display.

- [ ] **−1.4 Install Ubuntu Server 24.04 LTS**

  Start the VM and complete the Ubuntu installer:

  - Hostname: `ai-appliance`
  - Static IP: `192.168.1.63/24`, gateway `192.168.1.1`, DNS `192.168.1.1`
  - Install OpenSSH server
  - No additional snaps
  - Format the data disk (`/dev/sdb`) as ext4 and mount at `/var/lib/docker` during partitioning, or post-install:

    ```bash
    mkfs.ext4 /dev/sdb
    echo '/dev/sdb /var/lib/docker ext4 defaults 0 2' | sudo tee -a /etc/fstab
    sudo mkdir -p /var/lib/docker
    sudo mount -a
    ```

- [ ] **−1.5 Install NVIDIA drivers and Docker**

  ```bash
  # NVIDIA driver
  sudo apt update
  sudo apt install -y nvidia-driver-570 nvidia-utils-570

  # Docker Engine
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker $USER
  newgrp docker

  # NVIDIA Container Toolkit
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
    sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
  curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
  sudo apt update && sudo apt install -y nvidia-container-toolkit
  sudo nvidia-ctk runtime configure --runtime=docker
  sudo systemctl restart docker
  ```

- [ ] **−1.6 Verify GPU passthrough**

  ```bash
  nvidia-smi
  docker run --rm --gpus all ubuntu:24.04 nvidia-smi
  ```

  Both must show the RTX 3060 before proceeding.

- [ ] **−1.7 Clone the repository**

  ```bash
  git clone https://github.com/<your-org>/local-ai-appliance.git /opt/ai-appliance
  cd /opt/ai-appliance
  ```

  **Acceptance criteria:** VM reachable at `192.168.1.63`; `nvidia-smi` shows RTX 3060 12 GB; Docker container GPU test passes; repository cloned.

---

## Phase 0 — Pre-flight

**Goal:** Produce a valid `.env` in the project root with all secrets generated and no `CHANGE_ME` values. All scripts pass syntax check. `preflight.sh` exits 0.

**Files:**
- Modify: `scripts/generate-secrets.sh`
- Modify (manually): `.env.example`
- Produce: `.env` (from `compose/.env` + secret generation)

- [ ] **0.1 Move env file to project root**

  The working env file landed in `compose/.env` during the documentation sprint (dotfile restriction). Move it to where Docker Compose expects it:

  ```bash
  mv compose/.env .env
  ```

- [ ] **0.2 Add missing placeholders to `.env.example`**

  These keys exist in `compose.yml` but are absent from `.env.example`. Add them manually:

  ```
  ACME_EMAIL=CHANGE_ME
  CF_DNS_API_TOKEN=CHANGE_ME
  KOKORO_IMAGE=CHANGE_ME
  MEM0_IMAGE=CHANGE_ME
  MEM0_LLM_MODEL=CHANGE_ME
  MEM0_DB_NAME=CHANGE_ME
  MEM0_DB_USER=CHANGE_ME
  MEM0_DB_PASSWORD=CHANGE_ME
  ```

- [ ] **0.3 Add `MEM0_DB_PASSWORD` to `generate-secrets.sh`**

  Insert before the `chmod 600` line in `scripts/generate-secrets.sh`:

  ```bash
  replace_value MEM0_DB_PASSWORD "$(random_hex 24)"
  ```

  Validate syntax:

  ```bash
  bash -n scripts/generate-secrets.sh
  ```

- [ ] **0.4 Generate secrets and verify no `CHANGE_ME` values remain**

  ```bash
  ./scripts/generate-secrets.sh
  grep CHANGE_ME .env   # must return nothing
  ```

  Manually set any remaining env vars that `generate-secrets.sh` does not auto-generate:
  `ACME_EMAIL`, `CF_DNS_API_TOKEN`, `TRAEFIK_BIND_IP`, `AUTH_FQDN`, `AI_FQDN`,
  `OPENID_PROVIDER_URL`, `OPENID_REDIRECT_URI`, `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`.
  (OIDC values are filled after Phase 1.3.)

- [ ] **0.5 Pin `:latest` image tags**

  Check current release tags on each image registry, then set the pinned values in `.env`:

  | Variable | Image | Registry |
  |---|---|---|
  | `FASTER_WHISPER_IMAGE` | `fedirz/faster-whisper-server` | hub.docker.com |
  | `KOKORO_IMAGE` | `ghcr.io/remsky/kokoro-fastapi-cpu` | ghcr.io |
  | `MEM0_IMAGE` | `mem0ai/mem0` | hub.docker.com |

- [ ] **0.6 Run preflight and config validation**

  ```bash
  ./scripts/preflight.sh
  docker compose --env-file .env config >/dev/null
  bash -n scripts/*.sh backup/*.sh restore/*.sh
  ```

  **Acceptance criteria:** all three commands exit 0.

---

## Phase 1 — Core infrastructure

**Goal:** Traefik serves HTTPS with a valid Let's Encrypt certificate. Authentik UI reachable at `https://auth.murs-local.net`. PostgreSQL and Redis are healthy. OIDC provider configured and client credentials recorded in `.env`.

**Files:**
- No code changes — configuration and deployment only

- [ ] **1.1 Start infrastructure services**

  ```bash
  docker compose up -d traefik redis postgres authentik-server authentik-worker
  watch docker compose ps
  ```

  Wait for all services to reach `healthy`. Authentik has a 60 s start period.

- [ ] **1.2 Verify TLS certificate**

  Open `https://auth.murs-local.net`. Confirm:
  - Valid certificate issued by Let's Encrypt
  - Authentik initial setup wizard appears

  If certificate not issued within 2 minutes:

  ```bash
  docker compose logs traefik | grep -i acme
  ```

- [ ] **1.3 Complete Authentik initial configuration**

  In the Authentik admin UI:

  1. Create groups: `ai-admins` and `ai-users`
  2. Assign each user to the appropriate group
  3. Create OAuth2/OIDC provider `open-webui` — Client type: Confidential, Redirect URI: `https://ai.murs-local.net/oauth/oidc/callback`, Scopes: `openid email profile groups`
  4. Add groups scope mapping that emits `groups` as a list of group names; associate with provider
  5. Create application bound to the provider, accessible to both groups
  6. Note Client ID and Client Secret

  Update `.env` with OIDC values:

  ```
  OAUTH_CLIENT_ID=<client-id>
  OAUTH_CLIENT_SECRET=<client-secret>
  OPENID_PROVIDER_URL=https://auth.murs-local.net/application/o/<slug>/
  OPENID_REDIRECT_URI=https://ai.murs-local.net/oauth/oidc/callback
  ```

  Full walkthrough: `docs/INSTALLATION.md` section 7 and `docs/runbooks/USER-ONBOARDING.md`.

  **Acceptance criteria:** Authentik admin UI accessible; groups created; OIDC provider configured; client credentials in `.env`.

---

## Phase 2 — LLM inference

**Goal:** Ollama is running with confirmed GPU passthrough. Mem0 embedding and LLM models pulled and available. First inference model loaded and responding from GPU.

**Files:**
- No code changes — deployment and model pulls only

- [ ] **2.1 Confirm GPU passthrough**

  ```bash
  nvidia-smi
  docker run --rm --gpus all ubuntu:24.04 nvidia-smi
  ```

  Both must succeed before proceeding.

- [ ] **2.2 Start Ollama and confirm healthy**

  ```bash
  docker compose up -d ollama
  docker compose ps ollama
  ```

- [ ] **2.3 Pull Mem0-required models**

  ```bash
  docker exec ollama ollama pull nomic-embed-text
  docker exec ollama ollama pull qwen2.5-coder:14b-instruct-q4_K_M
  ```

  Set `MEM0_LLM_MODEL=qwen2.5-coder:14b-instruct-q4_K_M` in `.env`.

- [ ] **2.4 Pull first inference model and verify GPU allocation**

  ```bash
  docker exec ollama ollama pull hermes3:8b
  nvidia-smi
  docker exec ollama ollama ps
  ```

  > Verify Gemma 4 tag names on `ollama.com/library` before pulling any `gemma4` variant — tags were not confirmed during the planning session.

  **Acceptance criteria:** `ollama ps` shows a loaded model; `nvidia-smi` shows GPU memory allocated.

---

## Phase 3 — Open WebUI

**Goal:** Open WebUI reachable at `https://ai.murs-local.net`. Both users log in via OIDC with correct roles. At least one model usable.

**Files:**
- No code changes — deployment and OIDC configuration only

- [ ] **3.1 Start Open WebUI and confirm healthy**

  ```bash
  docker compose up -d open-webui
  docker compose ps open-webui
  ```

- [ ] **3.2 Verify OIDC login and role mapping**

  Open `https://ai.murs-local.net`:
  - Confirm only the OIDC button appears — no username/password form
  - Log in as admin user → confirm admin role in Open WebUI settings
  - Log in as standard user → confirm user role; admin panel not accessible

- [ ] **3.3 Configure models and shared knowledge**

  As admin: confirm Ollama models appear; set default model; upload shared knowledge documents to the shared knowledge collection.

  **Acceptance criteria:** both users logged in with correct roles; at least one model responds.

---

## Phase 4 — Voice pipeline

**Goal:** faster-whisper (STT) and Kokoro (TTS) healthy. In-browser voice transcription and audio playback functional.

**Files:**
- No code changes — deployment only

- [ ] **4.1 Start voice services and confirm healthy**

  ```bash
  docker compose up -d faster-whisper kokoro
  docker compose ps faster-whisper kokoro
  ```

  > Kokoro downloads voice model files on first start. Allow up to 60 s for the health check to pass.

- [ ] **4.2 Verify STT (speech-to-text)**

  In Open WebUI: enable microphone, record a short message, confirm transcription appears.

  If it fails:

  ```bash
  docker exec ai-open-webui curl -fs http://faster-whisper:8000/health
  ```

- [ ] **4.3 Verify TTS (text-to-speech)**

  In Open WebUI: enable TTS, send a message, confirm audio playback of the response.

  If it fails:

  ```bash
  docker exec ai-open-webui curl -fs http://kokoro:8880/v1/audio/voices
  ```

  **Acceptance criteria:** STT transcription and TTS playback both function in-browser.

---

## Phase 5 — Memory layer (Mem0)

**Goal:** Mem0 running and healthy. An Open WebUI Filter function injects per-user memories into the system prompt and saves new turns to Mem0 after each response. Per-user isolation verified.

**Files:**
- Create: `compose/open-webui/mem0-filter.py` (source for Open WebUI Functions UI paste)

- [ ] **5.1 Start Mem0 and confirm connectivity**

  ```bash
  docker compose up -d mem0
  docker compose ps mem0
  docker compose logs mem0 | head -40
  ```

  Confirm logs show successful connection to PostgreSQL and Ollama.

- [ ] **5.2 Create the Filter function file**

  Write `compose/open-webui/mem0-filter.py`:

  ```python
  from typing import Optional

  MEM0_BASE_URL = "http://mem0:8000"


  class Filter:
      async def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
          if not __user__:
              return body
          user_id = __user__["id"]  # stable OWI UUID created from OIDC sub on first login
          messages = body.get("messages", [])
          last_user_msg = next(
              (m["content"] for m in reversed(messages) if m.get("role") == "user"),
              None,
          )
          if not last_user_msg:
              return body

          import httpx
          try:
              resp = httpx.post(
                  f"{MEM0_BASE_URL}/search",
                  json={"query": last_user_msg, "filters": {"user_id": user_id}, "top_k": 10},
                  timeout=5.0,
              )
              results = resp.json().get("results", [])
          except Exception:
              return body  # memory unavailable — degrade gracefully

          if results:
              memory_text = "\n".join(f"- {r['memory']}" for r in results)
              body.setdefault("messages", []).insert(0, {
                  "role": "system",
                  "content": f"Relevant memories about this user:\n{memory_text}",
              })
          return body

      async def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
          if not __user__:
              return body
          user_id = __user__["id"]
          messages = body.get("messages", [])
          last_user = next(
              (m for m in reversed(messages) if m.get("role") == "user"), None
          )
          last_assistant = next(
              (m for m in reversed(messages) if m.get("role") == "assistant"), None
          )
          if not last_user or not last_assistant:
              return body

          import httpx
          try:
              httpx.post(
                  f"{MEM0_BASE_URL}/memories",
                  json={"messages": [last_user, last_assistant], "user_id": user_id},
                  timeout=5.0,
              )
          except Exception:
              pass  # fire-and-forget; save failure must not break the response
          return body
  ```

  **Design notes:**
  - `__user__["id"]` is Open WebUI's stable UUID — created from the OIDC `sub` claim on first login. It is the correct per-user isolation key for Mem0.
  - Mem0 `/search` uses `filters: {"user_id": "..."}` (top-level `user_id` is deprecated in current server).
  - `httpx` is available in the Open WebUI container.
  - Both `open-webui` and `mem0` are on `ai_backend`, so `http://mem0:8000` resolves.

- [ ] **5.3 Install and enable the Filter in Open WebUI**

  1. Admin → Functions → New Function
  2. Paste the contents of `compose/open-webui/mem0-filter.py`
  3. Enable the function globally (or per-model as preferred)
  4. Set Filter priority to `0` (runs before other system-prompt modifiers)

- [ ] **5.4 Verify per-user isolation**

  1. Log in as User A — send a message containing a memorable fact (e.g. "I prefer Python over JavaScript")
  2. Log in as User B — send a related question; confirm User A's fact does not appear
  3. Log back in as User A — send a follow-up; confirm the fact is recalled

  **Acceptance criteria:** memories persist across sessions per user; no cross-user memory leak.

---

## Phase 6 — Hardening and backups

**Goal:** Nightly backup running via systemd timer and verified restorable. All image tags pinned. Traefik socket proxy in place.

**Files:**
- Modify: `compose.yml` (add socket proxy service)
- Create: `docs/decisions/ADR-006-socket-proxy.md`

- [ ] **6.1 First backup run**

  ```bash
  ./backup/backup.sh
  restic -r <repo> snapshots
  ```

  Confirm a Restic snapshot appears.

- [ ] **6.2 Configure systemd timer for nightly backup**

  See `docs/INSTALLATION.md` backup scheduling section.

- [ ] **6.3 Configure PBS weekly VM backup**

  Configure weekly whole-VM backup in Proxmox Backup Server. See `docs/decisions/ADR-005-backups.md`.

- [ ] **6.4 Pin all remaining `:latest` tags**

  Replace any `:latest` in `.env` and `.env.example` with pinned release tags. Run `docker compose config` to confirm clean output.

- [ ] **6.5 Add Traefik socket proxy**

  1. Add `tecnativa/docker-socket-proxy` to `compose.yml` on the `proxy` network
  2. Set `DOCKER_HOST=tcp://socket-proxy:2375` in Traefik environment
  3. Remove `/var/run/docker.sock` volume mount from Traefik
  4. Write `docs/decisions/ADR-006-socket-proxy.md` recording the change

  Tracked as open item in `docs/DECISIONS.md` and `AGENTS.md`.

- [ ] **6.6 Schedule and document quarterly restore test**

  Record the first restore test date. See `docs/BACKUP-RESTORE.md` for the restore runbook.

  **Acceptance criteria:** nightly backup running; Restic snapshot restores cleanly; Traefik socket proxy active; all image tags pinned.

---

## Phase 7 — Operational baseline

**Goal:** Both users active. All acceptance tests from `docs/INSTALLATION.md` section 17 pass. System is ready for day-to-day use.

**Files:**
- No code changes — acceptance testing and user onboarding

- [ ] **7.1 Run acceptance tests**

  Execute all tests in `docs/INSTALLATION.md` section 17. Document results.

- [ ] **7.2 Onboard second user**

  Follow `docs/runbooks/USER-ONBOARDING.md`. Confirm:
  - OIDC login works
  - Role is `user` (not admin)
  - Private knowledge collections are separate
  - Memories do not cross between users (repeat Phase 5.4 with real accounts)

- [ ] **7.3 Operational documentation handover**

  Review `docs/OPERATIONS.md` with both users. Confirm:
  - Both users know how to pull new models
  - Both users know how to trigger a manual backup
  - Pre-upgrade runbook (`docs/runbooks/PRE-UPGRADE.md`) has been read

  **Acceptance criteria:** both users active; acceptance tests green; restore test documented.

---

## Open items carried from planning session

Do not close silently — raise with owner before acting.

| # | Item | Phase | Status |
|---|---|---|---|
| 1 | Traefik Docker socket proxy | Phase 6 | Deferred |
| 2 | Traefik dashboard (may re-enable behind Authentik forward-auth) | Post-production | Deferred |
| 3 | Qdrant (evaluate if vector search performance becomes a requirement) | Post-production | Deferred |
| 4 | Mem0 Authentik Proxy Outpost (only if Mem0 gains non-OWI clients) | Post-production | Deferred |
| 5 | Mem0 → Open WebUI Filter function | Phase 5 | Skeleton in Phase 5.2 — not yet installed |
| 6 | Pin `:latest` tags for faster-whisper, Kokoro, Mem0 | Phase 0 | Outstanding |
| 7 | `MEM0_DB_PASSWORD` missing from `generate-secrets.sh` | Phase 0 | Outstanding |
| 8 | `.env.example` missing Kokoro, Mem0, ACME entries | Phase 0 | Outstanding |
| 9 | Verify Gemma 4 tag names on `ollama.com/library` | Phase 2 | Outstanding |
| 10 | Move `compose/.env` → project root `.env` | Phase 0 | Outstanding |
