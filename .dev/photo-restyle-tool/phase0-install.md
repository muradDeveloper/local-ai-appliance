# Phase 0 - Install & Download Checklist

Run all commands **on the Proxmox VM host** (not in the container). Host `/mnt/ai-files/comfyui`
maps into the container at `/root/ComfyUI`. URLs verified 2026-08-04; re-check if a download 404s.

Base: `/mnt/ai-files/comfyui`  (from `AI_FILES_BASE=/mnt/ai-files`)

---

## 0. Create target directories
```bash
cd /mnt/ai-files/comfyui
mkdir -p models/instantid \
         models/controlnet \
         models/insightface/models/antelopev2 \
         models/checkpoints \
         models/pulid \
         models/unet \
         models/loras \
         models/ultralytics/bbox \
         models/sams \
         custom_nodes
```

---

## 1. InstantID (Phase 1 - anime + realistic)

### Custom node
```bash
git clone https://github.com/cubiq/ComfyUI_InstantID \
  /mnt/ai-files/comfyui/custom_nodes/ComfyUI_InstantID
```

### Models
```bash
# IP-Adapter (InstantID main model)
wget -O /mnt/ai-files/comfyui/models/instantid/ip-adapter.bin \
  "https://huggingface.co/InstantX/InstantID/resolve/main/ip-adapter.bin?download=true"

# InstantID ControlNet
wget -O /mnt/ai-files/comfyui/models/controlnet/instantid_control.safetensors \
  "https://huggingface.co/InstantX/InstantID/resolve/main/ControlNetModel/diffusion_pytorch_model.safetensors?download=true"

# antelopev2 insightface (zip -> 5 .onnx files)
wget -O /tmp/antelopev2.zip \
  "https://huggingface.co/MonsterMMORPG/tools/resolve/main/antelopev2.zip"
unzip -o /tmp/antelopev2.zip -d /mnt/ai-files/comfyui/models/insightface/models/antelopev2/
```
> **CHECK:** after unzip the 5 `.onnx` files must sit **directly** in
> `models/insightface/models/antelopev2/` -- NOT in a nested `antelopev2/antelopev2/`.
> Verify: `ls /mnt/ai-files/comfyui/models/insightface/models/antelopev2/*.onnx` (expect 5 files).

---

## 2. RealVisXL V5.0 (Phase 1 - realistic checkpoint, ~6.9 GB)
```bash
wget -O /mnt/ai-files/comfyui/models/checkpoints/RealVisXL_V5.0_fp16.safetensors \
  "https://huggingface.co/SG161222/RealVisXL_V5.0/resolve/main/RealVisXL_V5.0_fp16.safetensors?download=true"
```
Anime checkpoints (animagine / illustrious) are already present.

---

## 3. PuLID-FLUX (Phase 2 - hyper-realistic)

### Custom node
```bash
git clone https://github.com/balazik/ComfyUI-PuLID-Flux \
  /mnt/ai-files/comfyui/custom_nodes/ComfyUI-PuLID-Flux
```

### PuLID model (~1.1 GB)
```bash
wget -O /mnt/ai-files/comfyui/models/pulid/pulid_flux_v0.9.1.safetensors \
  "https://huggingface.co/guozinan/PuLID/resolve/main/pulid_flux_v0.9.1.safetensors"
```
> VERIFY the `guozinan/PuLID` path; mirrors also exist (Tenofas/ComfyUI, fofr/comfyui).

### FLUX.1-dev weights -- DO NOT DOWNLOAD YET
> Open question: does PuLID-Flux work acceptably with the **Schnell fp8** you already have?
> Test that first. If it needs **dev**, decide fp8-e4m3fn vs GGUF (for 12 GB) at build time.
> The BFL `black-forest-labs/FLUX.1-dev` repo is gated (needs an HF token + licence accept);
> Comfy-Org mirrors are not. Left as a build-time decision -- ~17-23 GB, non-commercial licence.

---

## 4. OPTIONAL - future "beautify" tool (download now, not wired into Phase 1)
```bash
# Impact Pack (FaceDetailer) + Subpack
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack \
  /mnt/ai-files/comfyui/custom_nodes/ComfyUI-Impact-Pack
git clone https://github.com/ltdrdata/ComfyUI-Impact-Subpack \
  /mnt/ai-files/comfyui/custom_nodes/ComfyUI-Impact-Subpack

# Face detection model
wget -O /mnt/ai-files/comfyui/models/ultralytics/bbox/face_yolov8m.pt \
  "https://huggingface.co/Bingsu/adetailer/resolve/main/face_yolov8m.pt"

# SAM (optional, for segmentation)
wget -O /mnt/ai-files/comfyui/models/sams/sam_vit_b_01ec64.pth \
  "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_b_01ec64.pth"
```
> Beauty/detail LoRA(s): pick specific files at build time (mostly Civitai) -> `models/loras/`.

---

## 4b. OPTIONAL - depth ControlNet for photo_restyle (locks head proportions)
Enabled by the `use_depth_controlnet` valve (default off). Download models OFFLINE and pre-place
them -- nothing should auto-download at runtime.
```bash
# Depth preprocessor node
git clone https://github.com/Fannovel16/comfyui_controlnet_aux \
  /mnt/ai-files/comfyui/custom_nodes/comfyui_controlnet_aux
# (its Python deps install via pre-start.sh; model weights are placed manually below)

# Depth SDXL ControlNet model (~2.5 GB) -> models/controlnet/, renamed to match the valve
wget -O /mnt/ai-files/comfyui/models/controlnet/xinsir-controlnet-depth-sdxl-1.0.safetensors \
  "https://huggingface.co/xinsir/controlnet-depth-sdxl-1.0/resolve/main/diffusion_pytorch_model.safetensors"

# Depth-Anything-V2 preprocessor weights (place offline; do NOT let the node auto-download)
#   file: depth_anything_v2_vitl.pth  (matches the depth_preprocessor_ckpt valve)
#   source: https://huggingface.co/depth-anything/Depth-Anything-V2-Large
#   VERIFY the target dir for YOUR comfyui_controlnet_aux version -- typically:
#     /mnt/ai-files/comfyui/custom_nodes/comfyui_controlnet_aux/ckpts/depth-anything/
```
> After placing them, flip the `use_depth_controlnet` valve on and re-run. If the
> `DepthAnythingV2Preprocessor` reports a missing model, the ckpt dir is wrong -- move the .pth
> to the path the node logs, no re-download needed.

---

## 5. Custom-node Python deps -- installed on every boot via pre-start.sh hook
A build-time (Dockerfile) install does NOT work on this image: there is no `python` on PATH at
build (the venv only exists at runtime). Instead the image runs `pre-start.sh` on every boot,
inside the live venv. Deploy the repo copy to the mounted hook dir, then recreate.
```bash
# 1. Confirm the exact hook path (container is already running):
docker exec ai-comfyui find /root -name 'pre-start.sh' 2>/dev/null
#    -> if it prints something OTHER than /root/user-scripts/pre-start.sh,
#       change the user-scripts volume mount in compose.yml to match.

# 2. Deploy the hook + make it executable:
mkdir -p /mnt/ai-files/comfyui/user-scripts
cp compose/comfyui/user-scripts/pre-start.sh /mnt/ai-files/comfyui/user-scripts/pre-start.sh
chmod +x /mnt/ai-files/comfyui/user-scripts/pre-start.sh

# 3. Recreate ComfyUI (no build step):
docker compose --env-file env_var.cfg up -d comfyui
docker logs -f ai-comfyui   # watch "[pre-start] installing custom-node deps ..." then nodes load
```
If a FUTURE node needs another package, add it to `pre-start.sh` (version-controlled, no rebuild).
The now-unused `compose/comfyui/Dockerfile` can be deleted: `rm compose/comfyui/Dockerfile`.

---

## 6. Verify
- ComfyUI loads with no red "IMPORT FAILED" nodes (check logs or Manager).
- `ls` each target dir has the expected file(s).
- InstantID + antelopev2 paths correct (the CHECK above).

## Notes
- All large HF files: `wget` follows the CDN redirect automatically.
- Permissions: container runs as root; host files under `/mnt/ai-files/comfyui` should be readable
  by it. If a node can't read a model, check ownership/mode.
- Total download (Phase 1 + PuLID node/model + beautify): roughly 12-14 GB; FLUX-dev (if needed
  later) adds ~17 GB.
