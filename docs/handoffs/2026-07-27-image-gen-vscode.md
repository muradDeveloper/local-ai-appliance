# Handoff — Image Generation Workflows & VS Code Integration
**Date:** 27/07/2026  
**Branch:** `setup/initial-deployment`

---

## Context

Previous handoff: `docs/handoffs/2026-07-27-feature-additions.md`

This session completed the initial ComfyUI deployment and debugged image generation end-to-end. The next session focuses on:
1. Setting up a Flux schnell workflow in ComfyUI and wiring it to Open WebUI
2. Connecting VS Code to Ollama models (Continue extension or similar)

---

## What was done this session

### 1. ComfyUI deployed and working
- `comfyui` service is running (`ai-comfyui`, port 8188 internal, Traefik-routed to `comfyui.murs-local.net`)
- ComfyUI Manager is installed (`custom_nodes/ComfyUI-Manager`)
- Image generation is wired into Open WebUI (Admin Panel → Images → ComfyUI engine)

### 2. Image generation bug found and fixed
- **Root cause:** Open WebUI's Admin Panel saved `COMFYUI_BASE_URL` with a leading space (` http://comfyui:8188`). `get_image_data()` in `open_webui/routers/images.py` checks `data.startswith('http://')` — the leading space causes this to fail, falling into the base64 decoder which produces 38 bytes of garbage from the URL string.
- **Fix applied:** Retyped the URL cleanly in Admin Panel → Images → ComfyUI Base URL (no leading space). This is a UI data-entry issue, not a code bug. Fixed in DB only — will recur if the field is pasted carelessly.
- **Note for future:** Open WebUI strips trailing slashes on save (`form_data.COMFYUI_BASE_URL.strip('/')`) but does NOT strip whitespace. Always type the URL manually.

### 3. Models downloaded to VM
| Model | Path on VM | Size | Status |
|---|---|---|---|
| Flux schnell fp8 | `/mnt/ai-files/comfyui/models/checkpoints/FLUX1/flux1-schnell-fp8.safetensors` | 4.6GB | ✅ Ready |
| SDXL base 1.0 | `/mnt/ai-files/comfyui/models/checkpoints/sd_xl_base_1.0.safetensors` | 6.5GB | ✅ Ready |
| clip_l | `/mnt/ai-files/comfyui/models/text_encoders/clip_l.safetensors` | 235MB | ✅ Ready |
| t5xxl fp8 | `/mnt/ai-files/comfyui/models/text_encoders/t5xxl_fp8_e4m3fn.safetensors` | 4.4GB | ✅ Ready |
| ae.safetensors (VAE) | `/mnt/ai-files/comfyui/models/vae/` | **Missing** | ❌ Not downloaded |

### 4. Open WebUI currently wired to SDXL base
- Workflow JSON uploaded to Open WebUI uses `sd_xl_base_1.0.safetensors` (standard KSampler workflow)
- Node ID mappings: prompt=`6`, model=`4`, width=`5`, height=`5`, steps=`3`, seed=`3`
- Working — generates images, displays them inline in chat

### 5. Scripts created
- `scripts/pre-deployment.sh` — creates all `/mnt/ai-files/` host directories (including comfyui subdirs)
- `scripts/post-deployment.sh` — applies `vm.overcommit_memory=1` kernel fix (fixes Valkey warning)

### 6. SearXNG config updated
- Disabled Brave and Wikidata engines in `compose/searxng/settings.yml` (both block self-hosted instances)
- File updated in repo — needs copying to `/mnt/ai-files/searxng/config/settings.yml` on VM and `docker compose restart searxng`

---

## Outstanding / next steps

### Flux workflow for ComfyUI + Open WebUI

**Missing prerequisite:** `ae.safetensors` VAE — download on VM:
```bash
wget -c "https://huggingface.co/black-forest-labs/FLUX.1-schnell/resolve/main/ae.safetensors" \
  -O /mnt/ai-files/comfyui/models/vae/ae.safetensors
```
(~335MB, requires HuggingFace — may need `--header "Authorization: Bearer <HF_TOKEN>"` if gated)

**Flux workflow node structure** (differs from SDXL):
- `UNETLoader` — loads `FLUX1/flux1-schnell-fp8.safetensors`
- `DualCLIPLoader` — loads `clip_l.safetensors` + `t5xxl_fp8_e4m3fn.safetensors`
- `VAELoader` — loads `ae.safetensors`
- `CLIPTextEncodeFlux` (positive prompt only — Flux ignores negative)
- `EmptySD3LatentImage` — use 1024×1024
- `KSampler` — `euler` sampler, `simple` scheduler, 4 steps, cfg=1.0
- `VAEDecode` → `SaveImage`

**Steps:**
1. Download `ae.safetensors`
2. Build the Flux workflow in ComfyUI UI
3. Test run directly in ComfyUI (verify output in History)
4. Export as API format → upload to Open WebUI Admin Panel → Images → ComfyUI Workflow
5. Update node ID mappings in Open WebUI for the Flux node structure

**Note:** Open WebUI Admin Panel → Images → Model field should be set to `FLUX1/flux1-schnell-fp8.safetensors` for Flux, or `sd_xl_base_1.0.safetensors` for SDXL. You can only have one workflow active at a time.

### VS Code → Ollama integration

Two options:

**Option A — Continue extension (recommended)**
- Install [Continue](https://marketplace.visualstudio.com/items?itemName=Continue.continue) from VS Code marketplace
- Config file: `~/.continue/config.json` on the laptop
- Point it at `http://192.168.1.63:11434` — but Ollama port is NOT exposed externally (by design, see `CLAUDE.md` constraints)
- **Required first:** expose Ollama via Traefik with auth, OR use an SSH tunnel:
  ```powershell
  ssh -L 11434:ollama:11434 local-llm
  ```
  Then set Continue base URL to `http://localhost:11434`

**Option B — GitHub Copilot Chat with custom model**
- Requires GitHub Copilot subscription
- Supports custom OpenAI-compatible endpoints via settings

**Option C — Ollama VS Code extension**
- Simpler but less capable than Continue
- Same networking constraint applies

**Networking note:** Ollama is on the `ai_backend` network only. It is not Traefik-routed. To expose it safely: add a Traefik route for `ollama.murs-local.net` with Authentik forward-auth middleware, then Continue can use `https://ollama.murs-local.net` directly.

---

## Key files changed this session

| File | Change |
|---|---|
| `compose.yml` | Added `COMFYUI_BASE_URL: http://comfyui:8188` env var to open-webui service |
| `compose/searxng/settings.yml` | Disabled Brave and Wikidata engines |
| `scripts/pre-deployment.sh` | Created — all host directory mkdirs |
| `scripts/post-deployment.sh` | Created — vm.overcommit_memory=1 kernel fix |

---

## Environment notes
- GPU: RTX 3060 12GB — shared between Ollama and ComfyUI (ComfyUI releases VRAM when idle)
- VM IP: `192.168.1.63` (SSH alias: `local-llm`)
- Ollama port 11434 is NOT externally exposed — requires SSH tunnel or Traefik route for VS Code access
- Open WebUI: `v0.10.2` (latest as of 27/07/2026)

---

## Suggested skills for next session

- `/context7-mcp` — before configuring any new ComfyUI node type or Continue extension config schema
- `/handoff` — at end of next session
