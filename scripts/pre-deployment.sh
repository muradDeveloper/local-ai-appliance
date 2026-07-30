#!/usr/bin/env bash
# Run once on the VM before the first `docker compose up`.
# Creates all host directories required by volume mounts.
set -Eeuo pipefail

echo "==> Creating host directories..."

# Core services
mkdir -p /mnt/ai-files/traefik/{dynamic,acme}
mkdir -p /mnt/ai-files/redis/data
mkdir -p /mnt/ai-files/postgres/{data,init}
mkdir -p /mnt/ai-files/ollama/data
mkdir -p /mnt/ai-files/authentik/{media,templates,certs}
mkdir -p /mnt/ai-files/open-webui/{data,knowledge}
mkdir -p /mnt/ai-files/portainer/data
mkdir -p /mnt/ai-files/speaches/models

# SearXNG
mkdir -p /mnt/ai-files/searxng/config

# ComfyUI
mkdir -p /mnt/ai-files/comfyui/{models,output,input,custom_nodes,user}
mkdir -p /mnt/ai-files/comfyui/models/{checkpoints,loras,vae,controlnet,upscale_models,diffusion_models,text_encoders}

echo "==> Host directories created."
