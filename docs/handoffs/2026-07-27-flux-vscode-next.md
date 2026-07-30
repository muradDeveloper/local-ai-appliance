# Handoff — Flux Schnell Working, VS Code Integration Next
**Date:** 27/07/2026  
**Branch:** `setup/initial-deployment`

---

## Context

Previous handoff: `docs/handoffs/2026-07-27-image-gen-vscode.md`

This session completed the Flux Schnell fp8 image generation pipeline end-to-end through Open WebUI. The next session focuses on VS Code → Ollama integration.

---

## What was done this session

### 1. Flux Schnell fp8 pipeline working end-to-end

Image generation now works in Open WebUI chat using Flux Schnell fp8 via ComfyUI.

**Model files on VM (final locations):**

| Model | Path on VM | Size |
|---|---|---|
| Flux schnell fp8 (UNet only) | `/mnt/ai-files/comfyui/models/unet/flux1-schnell-fp8.safetensors` | ~11GB |
| clip_l | `/mnt/ai-files/comfyui/models/text_encoders/clip_l.safetensors` | 235MB |
| t5xxl fp8 | `/mnt/ai-files/comfyui/models/text_encoders/t5xxl_fp8_e4m3fn.safetensors` | 4.4GB |
| ae.safetensors (VAE) | `/mnt/ai-files/comfyui/models/vae/ae.safetensors` | 335MB |
| SDXL base 1.0 | `/mnt/ai-files/comfyui/models/checkpoints/sd_xl_base_1.0.safetensors` | 6.5GB |

**Key lessons learned:**
- The 11GB Kijai fp8 file is a **UNet-only** file — requires `UNETLoader` + `DualCLIPLoader` + `VAELoader` separately. `CheckpointLoaderSimple` will fail with a shape error.
- `DualCLIPLoader` uses a single `type: "flux"` field (not `type1`/`type2`).
- `CLIPTextEncodeFlux` takes separate `clip_l` and `t5xxl` text inputs.
- Open WebUI model field must match exactly what the loader sees — `flux1-schnell-fp8.safetensors` not `FLUX1/flux1-schnell-fp8.safetensors`.
- JSON `_comment` fields at root level break ComfyUI validation (treated as node IDs). Use `_meta.title` for annotations instead.

### 2. ComfyUI compose config

`compose.yml` ComfyUI service: `CLI_ARGS` is currently `""` (no flag). Do not add `--lowvram` unless OOM errors appear — it causes the GPU to sit idle while streaming layers from RAM.

### 3. Workflow files created

All in `compose/comfyui/`:

| File | Purpose |
|---|---|
| `flux-schnell-workflow.json` | ComfyUI API-format workflow for Flux Schnell |
| `flux-schnell.cfg` | Open WebUI node mappings for Flux |
| `sdxl-base-workflow.json` | ComfyUI API-format workflow for SDXL base |
| `sdxl-base.cfg` | Open WebUI node mappings for SDXL |

### 4. Open WebUI — current active configuration (Flux Schnell)

Admin Panel → Images:
- Engine: ComfyUI
- Base URL: `http://comfyui:8188`
- Model: `flux1-schnell-fp8.safetensors`
- Image Size: `512x512` (note: workflow generates 1024×1024 — this field may be unused by ComfyUI engine)
- Steps: `8`

Node mappings:
| Field | Key | Node |
|---|---|---|
| Prompt | `t5xxl` | `4` |
| Model | `unet_name` | `1` |
| Width | `width` | `5` |
| Height | `height` | `5` |
| Steps | `steps` | `6` |
| Seed | `seed` | `6` |

### 5. Switching to SDXL

Upload `compose/comfyui/sdxl-base-workflow.json` and apply `compose/comfyui/sdxl-base.cfg` mappings. Node mappings for SDXL: prompt=`text`/`6`, model=`ckpt_name`/`4`, width/height=`5`, steps/seed=`3`.

### 6. HuggingFace token

A HF token was used this session to download models. **Revoke and regenerate it** — it was exposed in conversation. Token was stored in `env_var.cfg` on the VM at `/mnt/ai-files/scripts/env_var.cfg`. Do not commit this file.

---

## Outstanding / next steps

### VS Code → Ollama integration

From `docs/handoffs/2026-07-27-image-gen-vscode.md` (unchanged):

**Networking constraint:** Ollama is on `ai_backend` network only, not Traefik-routed. Port `11434` is not externally exposed. Two options to expose it:

**Option A — SSH tunnel (quickest):**
```powershell
ssh -L 11434:ollama:11434 local-llm
```
Then configure Continue extension base URL to `http://localhost:11434`.

**Option B — Traefik route with Authentik auth (proper):**
Add a Traefik route for `ollama.murs-local.net` with Authentik forward-auth middleware. Continue can then use `https://ollama.murs-local.net` directly without a tunnel.

**Continue extension setup:**
1. Install [Continue](https://marketplace.visualstudio.com/items?itemName=Continue.continue) from VS Code marketplace
2. Config file: `~/.continue/config.json` on the laptop
3. Set base URL per whichever networking option is chosen
4. Use Context7 before editing `config.json` to verify current schema — it changes between releases

---

## Key files changed this session

| File | Change |
|---|---|
| `compose.yml` | `CLI_ARGS` toggled between `""` and `"--lowvram"` — currently `""` |
| `compose/comfyui/flux-schnell-workflow.json` | Created — Flux Schnell ComfyUI workflow |
| `compose/comfyui/flux-schnell.cfg` | Created — Open WebUI node mappings for Flux |
| `compose/comfyui/sdxl-base-workflow.json` | Created — SDXL base ComfyUI workflow |
| `compose/comfyui/sdxl-base.cfg` | Created — Open WebUI node mappings for SDXL |

---

## Environment notes

- GPU: RTX 3060 12GB — Ollama and ComfyUI share it (ComfyUI releases VRAM when idle)
- VM IP: `192.168.1.63` (SSH alias: `local-llm`)
- Open WebUI: `v0.10.2` at `https://ai.murs-local.net`
- ComfyUI: `https://comfyui.murs-local.net`
- Ollama port 11434 NOT externally exposed

---

## Suggested skills for next session

- `/context7-mcp` — before editing `~/.continue/config.json` (schema changes frequently)
- `/handoff` — at end of next session
