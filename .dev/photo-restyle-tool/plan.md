# Plan: Photo Restyle Tool (LinkedIn headshot editor)

_Created 2026-08-04. Multi-session build. Read this first on any continuation._

## Goal
A new Open WebUI tool that takes an **uploaded photo** and regenerates the person as either
(a) an **anime representation** or (b) a **hyper-realistic professional headshot**, with a
**prompt-driven background** (professional vs casual), while **preserving the person's identity**.
Primary use case: LinkedIn profile photos.

## Architecture decisions
- **Input:** uploaded images arrive via the `__messages__` reserved arg (NOT `__files__`, which is
  documents only). Extract the image (data-URI or `/api/v1/files/...` URL) from the latest user
  message, then POST it to ComfyUI `/upload/image` and reference it from a `LoadImage` node.
- **Approach:** regenerate-from-face (identity preservation), not plain img2img.
  - Anime mode -> **InstantID (SDXL)** + anime SDXL checkpoint (animagine / illustrious already present).
  - Realistic mode -> Phase 1 uses **InstantID + photoreal SDXL (RealVisXL)**; Phase 2 optionally
    upgrades to **PuLID-FLUX**.
- **Background:** prompt-driven (regeneration paints the background), e.g. "corporate office, soft
  bokeh" vs "neutral grey studio" vs "casual outdoor". No segmentation needed for regenerate.
- **Output:** reuse the existing tool's patterns -- `embeds` iframe + ComfyUI `/view` link
  (`COMFYUI_PUBLIC_URL` constant).

## Phases
- **Phase 0 - Prerequisites (user action on the VM):** install custom nodes + download models.
- **Phase 1 - InstantID tool (anime + realistic-SDXL):** fully 12 GB-feasible, no FLUX-dev needed.
- **Phase 2 - PuLID-FLUX realistic mode:** only if Phase 1 realism is insufficient.

## Install requirements (verified via web 2026-08-04; re-verify exact URLs at build time)
### InstantID (Phase 1)
- Node: `cubiq/ComfyUI_InstantID`
- insightface `antelopev2` -> `models/insightface/models/antelopev2/` (NOT nested twice)
- InstantID IP-Adapter (`ip-adapter.bin`) -> `models/instantid/`
- InstantID ControlNet -> `models/controlnet/`
- Photoreal SDXL checkpoint: **RealVisXL V5.0** (primary), **Juggernaut XL XI** (alt) -> `models/checkpoints/`
- Anime SDXL checkpoints: animagine / illustrious (already present)
- Optional stylised-avatar checkpoint: DreamShaper XL

## Checkpoint selection + skin-tone handling (darker skin tones)
Confirmed via external research (ChatGPT, 2026-08-04) and cross-checked against this stack:
- Realistic LinkedIn: **RealVisXL V5.0** > Juggernaut XL XI. FLUX.1-dev (Phase 2) for premium.
- Anime: Animagine XL 4.0 / Illustrious (present). Stylised avatar: DreamShaper XL (optional).
- Skin tone in the restyle tool is carried primarily by the **uploaded face** (InstantID/PuLID
  preserve complexion from the reference), reinforced by:
  - complexion-preserving positives: "rich dark brown skin, natural warm undertones, accurate
    complexion, realistic skin texture, balanced exposure"
  - negatives that push against washing-out: "light skin, pale skin, lightened, eurocentric
    features" (mirrors the existing `_gender_negative_prefix` in the text2image tool)
  - the PRIMARY tool **avoids** beauty LoRAs and heavy FaceDetailer smoothing (both lighten/flatten
    dark skin). The models are still downloaded now (storage permitting) for a SEPARATE future
    "beautify" tool aimed at users who want the polished/smoothed look -- see Future work.
  - nuance: FaceDetailer at LOW denoise with NO beauty LoRA only sharpens face detail (safe for all
    skin tones); the lightening comes specifically from beauty LoRAs + high-denoise smoothing.
- NOTE: ChatGPT's "denoise 0.15-0.30" advice is for img2img photo-ENHANCEMENT (keep original
  photo), NOT our regenerate-from-face pipeline. InstantID runs denoise ~1.0. Low-denoise only
  applies to an OPTIONAL refinement pass layered on InstantID output.

### PuLID-FLUX (Phase 2)
- Node: `ComfyUI-PuLID-Flux` (confirm exact fork/variant at build)
- PuLID model -> `models/pulid/`
- `antelopev2` (shared with InstantID), `facexlib` dependency
- FLUX: **confirm Schnell vs dev** (likely dev -> extra download + non-commercial licence)

### Optional -- for the future "beautify" tool (download now, storage permitting)
- Node: `ltdrdata/ComfyUI-Impact-Pack` (FaceDetailer) + `ComfyUI-Impact-Subpack` (verify at build)
- Face detection: `face_yolov8m.pt` -> `models/ultralytics/bbox/`
- SAM (optional segmentation): `sam_vit_b` -> `models/sams/`
- Beauty / detail LoRA(s): specific files TBD at build -> `models/loras/`
- Used ONLY by the future beautify tool, NOT the primary skin-accurate tool.

## Open questions (resolve before the relevant phase)
- [ ] PuLID-Flux: does it work acceptably with FLUX Schnell (present) or require FLUX-dev?
- [ ] Exact, current model download URLs (verify at build).
- [ ] `__messages__` image format: data-URI vs file-URL vs list-of-parts (test early on the VM).

## Risks
- `__messages__` image extraction format may vary by Open WebUI version -> validate first.
- PuLID-FLUX VRAM on the 12 GB 3060 is at the documented minimum -> may be slow / need offload.
- FLUX-dev non-commercial licence (personal use likely fine; user to confirm comfort).

## Future work (separate tools, not this build)
- **Beautify / smooth tool:** a distinct tool using beauty/detail LoRAs + aggressive FaceDetailer
  (Impact Pack) for users who want a polished/smoothed look. Kept separate so the primary tool
  stays skin-tone-accurate. Its models are pulled in Phase 0 (optional section) so they are ready.

## Status
- [x] Phase 0 COMPLETE (2026-08-04): InstantID + PuLID-Flux nodes installed, RealVisXL V5.0 +
      InstantID/antelopev2 + PuLID models downloaded, custom-node deps installing via the
      `pre-start.sh` hook (build-time Dockerfile install was impossible -- no python at build).
- [x] Image probe COMPLETE (2026-08-04): uploaded photo arrives as an inline **base64 data URI**
      (`data:image/jpeg;base64,...`) in the newest user message of `__messages__`. Decode -> POST
      to ComfyUI `/upload/image` -> reference via LoadImage. No files-API round-trip needed.
- [x] Phase 1 tool DRAFTED (2026-08-04): `.dev/photo-restyle-tool/photo_restyle.py` (compiles).
      InstantID graph, data-URI input -> /upload/image -> LoadImage, style/background/orientation
      params, complexion-preserving prompts, embed + /view link. Pending first real run to confirm
      exact node input keys + model filenames.
- [ ] Phase 1 validation: run against a real photo; fix any node/input-key mismatches.
- [ ] Phase 2: PuLID-FLUX realistic path (after confirming Schnell vs dev).

## Deps persistence mechanism (yanwk/comfyui-boot)
- NO python on PATH at build -> Dockerfile `RUN pip install` fails (exit 127). Use the runtime
  `pre-start.sh` user-scripts hook instead (mounted at /root/user-scripts), which runs in the
  live venv on every boot. Repo copy: `compose/comfyui/user-scripts/pre-start.sh`.

## Next step
Get the image-probe result (input format), then build the Phase 1 InstantID tool. If the probe
is skipped, write defensive extraction handling both data-URI and /api/v1/files URLs.
