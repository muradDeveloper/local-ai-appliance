"""
title: Photo Restyle (InstantID)
author: Murad
description: Upload a photo and regenerate it as a realistic professional headshot or an anime portrait, preserving the person's face via InstantID. Background and attire are prompt-driven. Built for LinkedIn-style profile photos.
requirements: httpx
version: 0.1.0
"""

import asyncio
import base64
import random
import time
import urllib.parse
import uuid
from typing import Awaitable, Callable, Literal, Optional, TypedDict

import httpx
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Deployment-specific: browser-reachable ComfyUI base URL for the image link.
# ---------------------------------------------------------------------------
COMFYUI_PUBLIC_URL = "https://comfyui.murs-local.net"

Style = Literal["realistic", "anime"]
Background = Literal["professional", "neutral", "casual"]
Orientation = Literal["portrait", "square", "landscape"]

_ORIENTATION = {
    "portrait": (832, 1216),
    "square": (1024, 1024),
    "landscape": (1216, 832),
}

# Background + attire descriptions injected into the positive prompt.
_BACKGROUND = {
    "professional": "modern corporate office interior softly blurred, business professional attire",
    "neutral": "clean neutral grey studio backdrop, even softbox lighting, smart professional attire",
    "casual": "bright casual outdoor setting with soft natural light and blurred background, smart casual attire",
}


# Shape of the Open WebUI messages passed via __messages__ (content is a plain
# string for text turns, or a list of parts when an image is attached).
class _ImageUrl(TypedDict, total=False):
    url: str


class _ContentPart(TypedDict, total=False):
    type: str
    image_url: _ImageUrl


class _Message(TypedDict, total=False):
    role: str
    content: "str | list[_ContentPart]"


# Shape of the ComfyUI /history response we consume.
class _ImageInfo(TypedDict, total=False):
    filename: str
    subfolder: str
    type: str


class _NodeOutput(TypedDict, total=False):
    images: list[_ImageInfo]


class _HistoryItem(TypedDict, total=False):
    outputs: dict[str, _NodeOutput]
    status: dict[str, object]


class Tools:
    class Valves(BaseModel):
        comfyui_url: str = Field(
            default="http://comfyui:8188",
            description="ComfyUI URL reachable from Open WebUI (container-to-container).",
        )
        comfyui_public_url: str = Field(
            default=COMFYUI_PUBLIC_URL,
            description="Browser-reachable ComfyUI base URL for the returned image link.",
        )
        realistic_checkpoint: str = Field(
            default="RealVisXL_V5.0_fp16.safetensors",
            description="SDXL photoreal checkpoint used for style=realistic.",
        )
        anime_checkpoint: str = Field(
            default="animagine-xl-4.0-opt.safetensors",
            description="SDXL anime checkpoint used for style=anime.",
        )
        instantid_file: str = Field(
            default="ip-adapter.bin",
            description="InstantID IP-Adapter file in models/instantid/.",
        )
        instantid_controlnet: str = Field(
            default="instantid_control.safetensors",
            description="InstantID ControlNet file in models/controlnet/.",
        )
        insightface_provider: str = Field(
            default="CPU",
            description="InsightFace execution provider (CPU is safe; CUDA needs a matching onnxruntime-gpu).",
        )
        steps: int = Field(default=30, description="Sampling steps.")
        cfg: float = Field(default=4.5, description="CFG scale (InstantID likes 4-5 to avoid burn).")
        instantid_weight: float = Field(default=0.8, description="InstantID identity strength (0-1).")
        sampler: str = Field(default="dpmpp_2m")
        scheduler: str = Field(default="karras")
        use_depth_controlnet: bool = Field(
            default=False,
            description="Add a depth ControlNet from the uploaded photo to lock head/face proportions. Requires the comfyui_controlnet_aux node + a depth SDXL ControlNet model installed.",
        )
        depth_controlnet: str = Field(
            default="xinsir-controlnet-depth-sdxl-1.0.safetensors",
            description="Depth SDXL ControlNet filename in models/controlnet/ (used only when use_depth_controlnet is on).",
        )
        depth_preprocessor_ckpt: str = Field(
            default="depth_anything_v2_vitl.pth",
            description="DepthAnythingV2Preprocessor checkpoint filename. Download it offline and place where comfyui_controlnet_aux expects (see phase0) -- do NOT rely on auto-download.",
        )
        depth_strength: float = Field(default=0.5, description="Depth ControlNet strength (0-1).")
        request_timeout_seconds: int = Field(default=60)
        generation_timeout_seconds: int = Field(default=420)
        poll_interval_seconds: float = Field(default=1.0)

    def __init__(self):
        self.valves = self.Valves()

    # -----------------------------------------------------------------------
    # Image input (uploaded photo arrives as a base64 data URI in __messages__)
    # -----------------------------------------------------------------------

    @staticmethod
    def _extract_image(messages: Optional[list[_Message]]) -> tuple[Optional[bytes], str]:
        """Return (bytes, mime) of the newest uploaded image, or (None, "")."""
        msgs: list[_Message] = messages or []
        for m in reversed(msgs):
            content = m.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if part.get("type") != "image_url":
                    continue
                image_url = part.get("image_url")
                url = image_url.get("url", "") if image_url else ""
                if url.startswith("data:"):
                    header, _, b64 = url.partition(",")
                    mime = header[5:].split(";")[0] or "image/png"
                    try:
                        return base64.b64decode(b64), mime
                    except Exception:
                        continue
        return None, ""

    async def _upload_image(
        self, client: httpx.AsyncClient, base_url: str, raw: bytes, mime: str
    ) -> str:
        """Upload bytes to ComfyUI /upload/image, return the reference name for LoadImage."""
        ext = "jpg" if "jpeg" in mime or "jpg" in mime else "png" if "png" in mime else "img"
        filename = f"owui_{uuid.uuid4().hex}.{ext}"
        r = await client.post(
            f"{base_url}/upload/image",
            files={"image": (filename, raw, mime or "image/jpeg")},
            data={"overwrite": "true"},
        )
        r.raise_for_status()
        j = r.json()
        name = j.get("name", filename)
        subfolder = j.get("subfolder", "")
        return f"{subfolder}/{name}" if subfolder else name

    # -----------------------------------------------------------------------
    # Prompt + workflow
    # -----------------------------------------------------------------------

    @staticmethod
    def _build_prompts(style: str, background: str, appearance: str, expression: str, extra: str) -> tuple[str, str]:
        bg = _BACKGROUND[background]
        appearance = appearance.strip()
        is_bald = any(kw in appearance.lower() for kw in ("bald", "shaved head", "no hair", "hairless"))
        # "bald" tends to render poorly; substitute "shaved head" wording in the prompt.
        appearance_prompt = appearance
        if is_bald:
            for word in ("bald head", "Bald head", "bald", "Bald"):
                appearance_prompt = appearance_prompt.replace(word, "shaved head")
        subject = f"the person ({appearance_prompt})" if appearance_prompt else "the person"
        # InstantID only pins the face via keypoints; the skull/scalp above is invented,
        # so guard head proportions explicitly in the negative.
        proportion_neg = (
            "deformed head, elongated head, oversized cranium, enlarged forehead, "
            "disproportionate head, macrocephaly, misshapen skull, wrong head proportions"
        )
        if style == "realistic":
            positive = (
                f"professional headshot portrait photo of {subject}, {bg}, "
                "natural head and face proportions, accurate natural skin tone matching the reference, "
                "realistic skin texture, sharp focus on the eyes, "
                "soft flattering lighting, 85mm lens, high detail, photorealistic"
            )
            negative = (
                "lowres, bad anatomy, deformed, disfigured, extra fingers, blurry, "
                "watermark, text, logo, oversaturated, plastic skin, waxy skin, "
                "airbrushed, inaccurate skin tone, skin tone shift, discolored skin, "
                f"cartoon, anime, 3d render, cgi, {proportion_neg}"
            )
        else:  # anime
            positive = (
                f"masterpiece, best quality, absurdres, anime portrait of {subject}, {bg}, "
                "natural head proportions, clean anime illustration, detailed eyes, "
                "clean lineart, soft shading, accurate skin tone matching the reference"
            )
            negative = (
                "lowres, bad anatomy, bad hands, extra fingers, missing fingers, blurry, "
                "worst quality, low quality, watermark, signature, text, inaccurate skin tone, "
                f"skin tone shift, discolored skin, realistic, photorealistic, 3d, {proportion_neg}"
            )
        # If the subject is bald, actively suppress invented scalp hair / stubble.
        if is_bald:
            negative += (
                ", hair on head, scalp hair, head stubble, stubble on scalp, hairline, "
                "receding hairline, buzz cut, short hair, toupee, wig, hairpiece, hair plugs"
            )
        if expression.strip():
            positive += f", {expression.strip()}"
        # Portraits skew stern by default -- always steer away from an angry look.
        negative += ", angry, frowning, scowl, stern harsh expression, grumpy, unfriendly face"
        if extra.strip():
            positive += f", {extra.strip()}"
        return positive, negative

    def _workflow(
        self, checkpoint: str, image_name: str, positive: str, negative: str,
        width: int, height: int, seed: int, use_depth: bool, variations: int,
    ) -> dict[str, dict[str, object]]:
        v = self.valves
        # KSampler reads conditioning from the depth ControlNet (node 15) when enabled,
        # otherwise straight from ApplyInstantID (node 8).
        pos_src: list[object] = ["15", 0] if use_depth else ["8", 1]
        neg_src: list[object] = ["15", 1] if use_depth else ["8", 2]
        wf: dict[str, dict[str, object]] = {
            "1": {
                "inputs": {"ckpt_name": checkpoint},
                "class_type": "CheckpointLoaderSimple",
                "_meta": {"title": "Load Checkpoint"},
            },
            "2": {
                "inputs": {"image": image_name},
                "class_type": "LoadImage",
                "_meta": {"title": "Reference Face"},
            },
            "3": {
                "inputs": {"instantid_file": v.instantid_file},
                "class_type": "InstantIDModelLoader",
                "_meta": {"title": "Load InstantID"},
            },
            "4": {
                "inputs": {"provider": v.insightface_provider},
                "class_type": "InstantIDFaceAnalysis",
                "_meta": {"title": "InstantID Face Analysis"},
            },
            "5": {
                "inputs": {"control_net_name": v.instantid_controlnet},
                "class_type": "ControlNetLoader",
                "_meta": {"title": "Load InstantID ControlNet"},
            },
            "6": {
                "inputs": {"text": positive, "clip": ["1", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Positive"},
            },
            "7": {
                "inputs": {"text": negative, "clip": ["1", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Negative"},
            },
            "8": {
                "inputs": {
                    "weight": v.instantid_weight, "start_at": 0.0, "end_at": 1.0,
                    "instantid": ["3", 0], "insightface": ["4", 0], "control_net": ["5", 0],
                    "image": ["2", 0], "model": ["1", 0],
                    "positive": ["6", 0], "negative": ["7", 0],
                },
                "class_type": "ApplyInstantID",
                "_meta": {"title": "Apply InstantID"},
            },
            "9": {
                "inputs": {"width": width, "height": height, "batch_size": variations},
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent"},
            },
            "10": {
                "inputs": {
                    "seed": seed, "steps": v.steps, "cfg": v.cfg,
                    "sampler_name": v.sampler, "scheduler": v.scheduler, "denoise": 1.0,
                    "model": ["8", 0], "positive": pos_src, "negative": neg_src,
                    "latent_image": ["9", 0],
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"},
            },
            "11": {
                "inputs": {"samples": ["10", 0], "vae": ["1", 2]},
                "class_type": "VAEDecode",
                "_meta": {"title": "VAE Decode"},
            },
            "12": {
                "inputs": {"filename_prefix": "open-webui/restyle", "images": ["11", 0]},
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"},
            },
        }
        if use_depth:
            # Depth ControlNet from the uploaded photo, applied after InstantID to lock
            # head/face proportions. Requires comfyui_controlnet_aux + a depth SDXL model.
            wf["13"] = {
                "inputs": {"control_net_name": v.depth_controlnet},
                "class_type": "ControlNetLoader",
                "_meta": {"title": "Load Depth ControlNet"},
            }
            wf["14"] = {
                "inputs": {
                    "image": ["2", 0],
                    "ckpt_name": v.depth_preprocessor_ckpt,
                    "resolution": 1024,
                },
                "class_type": "DepthAnythingV2Preprocessor",
                "_meta": {"title": "Depth Map"},
            }
            wf["15"] = {
                "inputs": {
                    "strength": v.depth_strength, "start_percent": 0.0, "end_percent": 1.0,
                    "positive": ["8", 1], "negative": ["8", 2],
                    "control_net": ["13", 0], "image": ["14", 0],
                },
                "class_type": "ControlNetApplyAdvanced",
                "_meta": {"title": "Apply Depth ControlNet"},
            }
        return wf

    @staticmethod
    def _all_images(history_item: _HistoryItem) -> list[_ImageInfo]:
        """All images ComfyUI produced (a batch can return several)."""
        images: list[_ImageInfo] = []
        outputs = history_item.get("outputs")
        if outputs:
            for node_output in outputs.values():
                images.extend(node_output.get("images") or [])
        return images

    # -----------------------------------------------------------------------
    # Public tool function
    # -----------------------------------------------------------------------

    async def restyle_photo(
        self,
        style: Style,
        background: Background,
        orientation: Orientation = "square",
        appearance: str = "",
        expression: str = "warm approachable expression with a slight friendly smile",
        extra_details: str = "",
        variations: int = 1,
        seed: Optional[int] = None,
        __messages__: Optional[list[_Message]] = None,
        __event_emitter__: Optional[Callable[..., Awaitable[None]]] = None,
    ):
        """
        Restyle the user's most recently uploaded photo into a new portrait, preserving their face via InstantID; use whenever the user uploads a photo and asks for a headshot, LinkedIn photo, anime version, or restyled portrait

        :param style: Output look, one of realistic (photorealistic professional headshot) or anime (anime illustration portrait); if the user does not specify the look, reuse the same style used for the previous image in this conversation -- REQUIRED
        :param background: Background and attire preset, one of professional (blurred office, business attire), neutral (grey studio backdrop), or casual (outdoor, smart casual) -- REQUIRED
        :param orientation: Canvas shape, one of portrait (832x1216), square (1024x1024), or landscape (1216x832) -- OPTIONAL
        :param appearance: Look at the uploaded photo and describe the person's real features to preserve, especially skin tone and complexion, hair or baldness, forehead size, and facial hair (e.g. deep rich brown skin, bald head, high large forehead, full black beard); always include the skin tone, and if they are bald say bald so no hair is added -- OPTIONAL
        :param expression: Facial expression, defaults to a warm approachable slight friendly smile; only change it if the user explicitly asks for a different expression such as neutral or serious -- OPTIONAL
        :param extra_details: Optional styling request such as wearing glasses, leave empty if none -- OPTIONAL
        :param variations: How many portrait options to generate at once, 1 to 4, default 1 -- OPTIONAL
        :param seed: Integer seed for reproducibility, omit for a random seed -- OPTIONAL
        """
        async def emit(description: str, done: bool = False):
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": description, "done": done}})

        # Validate enums
        errors: list[str] = []
        if style not in ("realistic", "anime"):
            errors.append("style: invalid -- must be one of: realistic, anime.")
        if background not in _BACKGROUND:
            errors.append("background: invalid -- must be one of: professional, neutral, casual.")
        ori_key = (orientation or "square").strip().lower()
        if ori_key not in _ORIENTATION:
            errors.append("orientation: invalid -- must be one of: portrait, square, landscape.")
        if errors:
            raise ValueError("Invalid parameters:\n" + "\n".join(f"  - {e}" for e in errors))

        # Extract uploaded photo
        raw, mime = self._extract_image(__messages__)
        if not raw:
            raise ValueError(
                "No uploaded photo found. Ask the user to attach a photo to their message, then retry."
            )

        checkpoint = self.valves.realistic_checkpoint if style == "realistic" else self.valves.anime_checkpoint
        width, height = _ORIENTATION[ori_key]
        seed = seed if seed is not None else random.randint(0, 2**63 - 1)
        variations = max(1, min(4, variations))
        positive, negative = self._build_prompts(
            style, background, appearance or "", expression or "", extra_details or ""
        )

        base_url = self.valves.comfyui_url.rstrip("/")
        http_timeout = httpx.Timeout(self.valves.request_timeout_seconds)

        async with httpx.AsyncClient(timeout=http_timeout) as client:
            await emit("Uploading your photo to ComfyUI...")
            image_name = await self._upload_image(client, base_url, raw, mime)

            await emit("Checking ComfyUI...")
            try:
                r = await client.get(f"{base_url}/system_stats")
                r.raise_for_status()
            except Exception as exc:
                await emit("Could not reach ComfyUI.", done=True)
                raise RuntimeError(f"Cannot reach ComfyUI at {base_url}: {exc}") from exc

            workflow = self._workflow(
                checkpoint, image_name, positive, negative, width, height, seed,
                self.valves.use_depth_controlnet, variations,
            )

            await emit(f"Generating {style} portrait (seed {seed})...")
            r = await client.post(
                f"{base_url}/prompt",
                json={"prompt": workflow, "client_id": str(uuid.uuid4())},
            )
            if r.status_code >= 400:
                raise RuntimeError(f"ComfyUI rejected the workflow: {r.status_code} {r.text[:2000]}")
            prompt_id = r.json().get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI returned no prompt_id: {r.text}")

            deadline = time.monotonic() + self.valves.generation_timeout_seconds
            history_item = None
            while time.monotonic() < deadline:
                h = await client.get(f"{base_url}/history/{prompt_id}")
                h.raise_for_status()
                history = h.json()
                if prompt_id in history:
                    history_item = history[prompt_id]
                    status = history_item.get("status", {})
                    if status.get("status_str") == "error":
                        raise RuntimeError(f"ComfyUI workflow failed: {status.get('messages', [])}")
                    if history_item.get("outputs"):
                        break
                await asyncio.sleep(self.valves.poll_interval_seconds)

            if not history_item or not history_item.get("outputs"):
                raise TimeoutError("Timed out waiting for ComfyUI.")

            view_base = (self.valves.comfyui_public_url or "").rstrip("/") or base_url
            image_infos = self._all_images(history_item)
            if not image_infos:
                raise RuntimeError("ComfyUI completed but returned no image output.")

            # (data_uri_src, public_view_url) for EVERY returned image, not just the first.
            gallery: list[tuple[str, str]] = []
            for info in image_infos:
                params: dict[str, str] = {
                    "filename": info.get("filename", ""),
                    "subfolder": info.get("subfolder", ""),
                    "type": info.get("type", "output"),
                }
                img_r = await client.get(f"{base_url}/view", params=params)
                img_r.raise_for_status()
                enc = base64.b64encode(img_r.content).decode("ascii")
                mime = img_r.headers.get("content-type", "image/png").split(";")[0]
                view_url = f"{view_base}/view?" + urllib.parse.urlencode(params)
                gallery.append((f"data:{mime};base64,{enc}", view_url))

        await emit(f"Generated {len(gallery)} portrait(s).", done=True)

        gallery_html = "".join(
            f'  <img src="{src}" alt="Restyled portrait {i + 1}" />\n'
            f'  <a href="{url}" target="_blank" rel="noopener">Open full image {i + 1}</a>\n'
            for i, (src, url) in enumerate(gallery)
        )
        embed_html = f"""<!DOCTYPE html>
<html>
<head><style>
  body {{margin:0;padding:0;font-family:sans-serif;font-size:13px}}
  img {{display:block;width:100%;height:auto;border-radius:8px;margin-top:8px}}
  a {{display:inline-block;margin:4px 0 12px;font-size:12px;color:#3b82f6;text-decoration:none}}
  details {{margin-top:10px;line-height:1.5}}
  summary {{cursor:pointer;font-weight:bold}}
</style></head>
<body>
{gallery_html}  <details open>
    <summary>Details</summary>
    <strong>Style:</strong> {style}<br>
    <strong>Background:</strong> {background}<br>
    <strong>Size:</strong> {width}x{height} ({ori_key})<br>
    <strong>Seed:</strong> {seed}<br>
    <strong>Variations:</strong> {len(gallery)}
  </details>
  <script>
    function reportHeight() {{
      var h = document.documentElement.scrollHeight;
      parent.postMessage({{ type: 'iframe:height', height: h }}, '*');
    }}
    window.addEventListener('load', reportHeight);
    document.querySelectorAll('img').forEach(function (im) {{ im.addEventListener('load', reportHeight); }});
    new ResizeObserver(reportHeight).observe(document.body);
  </script>
</body></html>"""

        if __event_emitter__:
            await __event_emitter__({"type": "embeds", "data": {"embeds": [embed_html]}})

        links = "; ".join(url for _, url in gallery)
        return (
            f"Generated {len(gallery)} portrait option(s) ({style}, {background} background, "
            f"{width}x{height}, seed {seed}). Shown to the user already. Images: {links}"
        )
