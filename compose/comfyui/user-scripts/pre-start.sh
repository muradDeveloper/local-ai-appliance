#!/usr/bin/env bash
# yanwk/comfyui-boot user-scripts hook: runs on every boot, just before ComfyUI starts,
# INSIDE the live container where ComfyUI's Python venv is already active.
#
# Installs custom-node Python deps so they survive container recreation. A build-time
# (Dockerfile) install fails on this image -- there is no `python` on PATH at build,
# the interpreter only exists at runtime.
#   InstantID / PuLID-Flux -> insightface, onnxruntime, facexlib
#   Impact Pack (future)    -> ultralytics
#
# pip is idempotent: already-satisfied packages are skipped, so warm boots are fast;
# only a fresh/recreated container does the full install.

PYBIN="$(command -v python || command -v python3)"
if [ -z "$PYBIN" ]; then
  echo "[pre-start] no python interpreter found on PATH; skipping dep install"
  exit 0
fi

echo "[pre-start] installing custom-node deps with $PYBIN ..."
"$PYBIN" -m pip install --no-cache-dir \
  insightface \
  onnxruntime \
  facexlib \
  ultralytics \
  || echo "[pre-start] pip install failed; custom nodes may not load"

# NOTE: do NOT blindly `pip install -r comfyui_controlnet_aux/requirements.txt` here -- its
# unpinned deps pull numpy 2.x, which breaks the image's bundled PyTorch ("PyTorch is not
# installed"). The optional depth ControlNet's deps must be installed with numpy pinned < 2
# (handled separately, only when that feature is enabled).
