"""
title: ComfyUI Custom Image Generator
author: Murad
description: Generate anime/illustration/photorealistic images through ComfyUI. ethnicity and
  gender are REQUIRED enums on every call -- the tool builds the morphological profile from them.
  Auto-generates a negative prompt via Ollama (SDXL) and applies per-model quality tags.
requirements: httpx
version: 2.1.0
"""

import asyncio
import base64
import random
import re
import time
import urllib.parse
import uuid
from typing import Awaitable, Callable, Literal, Optional, TypedDict, cast, get_args

import httpx
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Deployment-specific: browser-reachable ComfyUI base URL, used to build the
# clickable image link returned to the user. Edit this for your host.
# ---------------------------------------------------------------------------
COMFYUI_PUBLIC_URL = "https://comfyui.murs-local.net"

# ---------------------------------------------------------------------------
# TypedDicts for structured YAML and API data
# ---------------------------------------------------------------------------


class _ModelPreset(TypedDict, total=False):
    quality: str
    cfg: float
    steps: int
    sampler: str
    scheduler: str
    family: str      # "sdxl" (default) or "flux" -- selects the workflow builder
    guidance: float  # flux only: CLIPTextEncodeFlux guidance value


class _IdentityContext(TypedDict, total=False):
    ancestry_or_cultural_context: str


class _Morphology(TypedDict, total=False):
    face_shape: str
    eye_geometry: str
    nose_geometry: str
    lip_geometry: str


class _SurfaceAppearance(TypedDict, total=False):
    fitzpatrick_type: str
    undertone: str
    skin_texture: str


class _Profile(TypedDict, total=False):
    profile_id: str
    gender_presentation: str
    identity_context: _IdentityContext
    morphology: _Morphology
    surface_appearance: _SurfaceAppearance


class _ImageInfo(TypedDict, total=False):
    filename: str
    subfolder: str
    type: str


class _NodeOutput(TypedDict, total=False):
    images: list[_ImageInfo]


class _HistoryItem(TypedDict, total=False):
    outputs: dict[str, _NodeOutput]
    status: dict[str, object]


# ---------------------------------------------------------------------------
# Model-specific defaults
# ---------------------------------------------------------------------------

_MODEL_PRESETS: dict[str, _ModelPreset] = {
    "animagine-xl-4.0-opt.safetensors": {
        "quality": "masterpiece, high score, great score, absurdres",
        "cfg": 5.0, "steps": 28, "sampler": "euler_ancestral", "scheduler": "normal",
        "family": "sdxl",
    },
    "Illustrious-XL-v2.0.safetensors": {
        "quality": "score_9, score_8_up, score_7_up, masterpiece, absurdres",
        "cfg": 5.0, "steps": 28, "sampler": "euler_ancestral", "scheduler": "normal",
        "family": "sdxl",
    },
    "sd_xl_base_1.0.safetensors": {
        "quality": "masterpiece, best quality, highly detailed, photorealistic, cinematic",
        "cfg": 7.0, "steps": 28, "sampler": "euler_ancestral", "scheduler": "normal",
        "family": "sdxl",
    },
    # FLUX.1 Schnell -- guidance-distilled (CFG 1), 8 steps per flux-schnell.cfg.
    # Ignores negative prompts and prefers natural-language over danbooru tags.
    "flux1-schnell-fp8.safetensors": {
        "quality": "", "cfg": 1.0, "steps": 8, "sampler": "euler", "scheduler": "simple",
        "family": "flux", "guidance": 3.5,
    },
}
_DEFAULT_PRESET: _ModelPreset = _MODEL_PRESETS["sd_xl_base_1.0.safetensors"]

# Short alias -> exact checkpoint filename
_CHECKPOINT_ALIASES = {
    "sdxl": "sd_xl_base_1.0.safetensors",
    "animagine": "animagine-xl-4.0-opt.safetensors",
    "illustrious": "Illustrious-XL-v2.0.safetensors",
    "flux": "flux1-schnell-fp8.safetensors",
    "flux-schnell": "flux1-schnell-fp8.safetensors",
}

# ---------------------------------------------------------------------------
# Orientation -> (width, height)
# ---------------------------------------------------------------------------

# SDXL-native buckets (~1MP, the resolutions these models were trained on); FLUX
# handles them too. The "other" orientation uses a caller-supplied custom_size instead.
_ORIENTATION = {
    "portrait": (832, 1216),
    "landscape": (1216, 832),
    "square": (1024, 1024),
    "wide": (1344, 768),
    "tall": (768, 1344),
}

# ---------------------------------------------------------------------------
# Enumerated tool parameters
# ---------------------------------------------------------------------------

# Ethnicity tokens must match the top-level group keys in all_profiles.yml.
# "none" means no specific person (a scene / environment). "diverse" means a mixed
# group of people of various ethnicities, with no single morphology profile.
Ethnicity = Literal[
    "none", "diverse",
    "west_african", "east_african", "south_african", "north_african", "arab",
    "southeast_asian", "east_asian", "indian", "iranian", "chinese",
    "latin_american", "european", "australian", "native_american", "aboriginal",
    "north_american", "south_american",
]
Gender = Literal["none", "male", "female"]
Orientation = Literal["portrait", "landscape", "square", "wide", "tall", "other"]

_ETHNICITIES: tuple[str, ...] = get_args(Ethnicity)
_GENDERS: tuple[str, ...] = get_args(Gender)

# Friendly variants normalised to the canonical enum value before validation.
_GENDER_ALIASES = {
    "man": "male", "woman": "female",
}


class Tools:
    class Valves(BaseModel):
        comfyui_url: str = Field(
            default="http://comfyui:8188",
            description="ComfyUI URL reachable from Open WebUI (container-to-container).",
        )
        comfyui_public_url: str = Field(
            default=COMFYUI_PUBLIC_URL,
            description=(
                "Browser-reachable ComfyUI base URL used to build the clickable image link. "
                "Defaults to the COMFYUI_PUBLIC_URL constant at the top of this file. Clear it "
                "to fall back to comfyui_url, which is usually NOT reachable from a browser."
            ),
        )
        ollama_url: str = Field(
            default="http://ollama:11434",
            description="Ollama endpoint reachable from Open WebUI.",
        )
        ollama_model: str = Field(
            default="",
            description="Override model for negative prompt generation. Empty = auto-detect from /api/ps.",
        )
        default_checkpoint: str = Field(
            default="sd_xl_base_1.0.safetensors",
            description="Exact checkpoint filename used when the per-call checkpoint param is empty.",
        )
        flux_unet: str = Field(
            default="flux1-schnell-fp8.safetensors",
            description="FLUX diffusion model filename in ComfyUI models/unet/.",
        )
        flux_weight_dtype: str = Field(
            default="fp8_e4m3fn",
            description="weight_dtype for the FLUX UNETLoader. fp8_e4m3fn keeps a 12GB GPU within budget.",
        )
        flux_clip_l: str = Field(
            default="clip_l.safetensors",
            description="FLUX clip_l text encoder filename in models/text_encoders/.",
        )
        flux_t5xxl: str = Field(
            default="t5xxl_fp8_e4m3fn.safetensors",
            description="FLUX t5xxl text encoder filename in models/text_encoders/.",
        )
        flux_vae: str = Field(
            default="ae.safetensors",
            description="FLUX VAE filename in models/vae/.",
        )
        profiles_path: str = Field(
            default="/app/profiles/all_profiles.yml",
            description="Path inside the Open WebUI container where all_profiles.yml is mounted.",
        )
        generation_steps: int = Field(
            default=28,
            description="Sampling steps. Overrides the model preset when non-zero.",
        )
        negative_prompt_system: str = Field(
            default=(
                "You are a Stable Diffusion prompt engineer. Given a positive image prompt, "
                "output ONLY a comma-separated negative prompt with no explanation or preamble. "
                "Exclude: anatomy defects (bad anatomy, bad hands, extra fingers, missing fingers, "
                "fused limbs), quality defects (lowres, blurry, jpeg artifacts, noise, worst quality), "
                "and unwanted content (text, watermark, signature, logo, username). "
                "Also exclude traits that contradict the style, mood, or subject in the positive prompt. "
                "Never negate a trait that was explicitly requested."
            ),
            description="System prompt sent to Ollama when generating the negative prompt.",
        )
        negative_prompt_fallback: str = Field(
            default=(
                "lowres, bad anatomy, bad hands, extra fingers, missing fingers, "
                "blurry, worst quality, low quality, watermark, signature, text"
            ),
            description="Negative prompt used verbatim if the Ollama call fails.",
        )
        request_timeout_seconds: int = Field(default=30)
        generation_timeout_seconds: int = Field(default=300)
        poll_interval_seconds: float = Field(default=1.0)

    def __init__(self):
        self.valves = self.Valves()

    # -----------------------------------------------------------------------
    # Profiles
    # -----------------------------------------------------------------------

    def _load_profiles(self) -> dict[str, _Profile]:
        """Return flat dict of profile_id -> profile, or {} on any error."""
        try:
            import yaml
            with open(self.valves.profiles_path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            result: dict[str, _Profile] = {}
            for group in data.get("profiles", {}).values():
                if isinstance(group, list):
                    for p in group:
                        profile_entry = cast(_Profile, p)
                        pid = profile_entry.get("profile_id")
                        if pid:
                            result[pid] = profile_entry
            return result
        except Exception:
            return {}

    @staticmethod
    def _resolve_profile(
        ethnicity: str, gender: str, profiles: dict[str, _Profile]
    ) -> tuple[Optional[_Profile], str]:
        """Pick a random stored morphology variant for (ethnicity, gender).

        Returns (profile, profile_id) or (None, "") if none is available.
        """
        if not profiles:
            return None, ""
        suffix = "m" if gender == "male" else "f"
        pattern = re.compile(rf"^{re.escape(ethnicity)}_{suffix}\d+$")
        candidates = sorted(pid for pid in profiles if pattern.match(pid))
        if not candidates:
            return None, ""
        chosen = random.choice(candidates)
        return profiles[chosen], chosen

    @staticmethod
    def _profile_to_prompt_parts(profile: _Profile) -> tuple[str, str, str]:
        """Return (gender_token, ancestry_term, morphology_string)."""
        gender_pres = profile.get("gender_presentation", "")
        ctx = profile.get("identity_context", {})
        ancestry = ctx.get("ancestry_or_cultural_context", "")

        if "female" in gender_pres.lower():
            gender_token = "1girl, female focus"
            suffix = "woman"
        else:
            gender_token = "1boy, male focus"
            suffix = "man"

        ancestry_term = f"{ancestry} {suffix}".strip() if ancestry else ""

        m = profile.get("morphology", {})
        s = profile.get("surface_appearance", {})

        _fitzpatrick_desc = {
            "I":   "Fitzpatrick Type I skin, very fair pale complexion, pale skin",
            "II":  "Fitzpatrick Type II skin, fair complexion, fair skin",
            "III": "Fitzpatrick Type III skin, medium complexion, medium skin",
            "IV":  "Fitzpatrick Type IV skin, olive complexion, olive skin",
            "V":   "Fitzpatrick Type V skin, brown complexion, dark skin",
            "VI":  "Fitzpatrick Type VI skin, dark brown complexion, very dark skin, dark skin",
        }

        parts: list[str] = []
        for key in ("face_shape", "eye_geometry", "nose_geometry", "lip_geometry"):
            val = m.get(key)
            if val:
                parts.append(val)
        fitz = s.get("fitzpatrick_type")
        if fitz and str(fitz) in _fitzpatrick_desc:
            parts.append(_fitzpatrick_desc[str(fitz)])
        undertone = s.get("undertone")
        if undertone:
            parts.append(f"{undertone} undertone")
        skin_texture = s.get("skin_texture")
        if skin_texture:
            parts.append(f"{skin_texture} skin")

        return gender_token, ancestry_term, ", ".join(parts)

    @staticmethod
    def _gender_negative_prefix(gender_token: str) -> str:
        if "1girl" in gender_token:
            return (
                "1boy, male, man, masculine, beard, "
                "light skin, pale skin, caucasian, eurocentric features, "
                "narrow nose, thin lips, "
            )
        return (
            "1girl, female, woman, girl, feminine, "
            "light skin, pale skin, caucasian, eurocentric features, "
            "narrow nose, thin lips, "
        )

    # -----------------------------------------------------------------------
    # Checkpoint / preset resolution
    # -----------------------------------------------------------------------

    def _resolve_checkpoint(self, checkpoint_param: str) -> str:
        if not checkpoint_param:
            return self.valves.default_checkpoint
        key = checkpoint_param.strip().lower()
        if key in _CHECKPOINT_ALIASES:
            return _CHECKPOINT_ALIASES[key]
        if checkpoint_param.endswith(".safetensors"):
            return checkpoint_param
        for alias, filename in _CHECKPOINT_ALIASES.items():
            if key in alias or alias in key:
                return filename
        return self.valves.default_checkpoint

    @staticmethod
    def _get_preset(checkpoint: str) -> _ModelPreset:
        return _MODEL_PRESETS.get(checkpoint, _DEFAULT_PRESET)

    @staticmethod
    def _parse_custom_size(spec: str) -> tuple[int, int]:
        """Parse 'WIDTHxHEIGHT' (e.g. '832x1216') into (width, height).

        Each side must be 256-1536; values are snapped down to a multiple of 8 (the
        latent grid requirement). Raises ValueError with a clear message on bad input.
        """
        m = re.match(r"^\s*(\d{2,4})\s*[xX*]\s*(\d{2,4})\s*$", spec or "")
        if not m:
            raise ValueError(
                "custom_size: invalid -- use WIDTHxHEIGHT in pixels, e.g. 832x1216"
            )
        w, h = int(m.group(1)), int(m.group(2))
        for label, value in (("width", w), ("height", h)):
            if value < 256 or value > 1536:
                raise ValueError(
                    f"custom_size: {label} {value} out of range -- must be 256 to 1536"
                )
        return w - (w % 8), h - (h % 8)

    def _build_flux_positive(
        self, prompt: str, profile: Optional[_Profile], forced_gender: Optional[str]
    ) -> str:
        """Natural-language positive prompt for FLUX (no danbooru or quality tags).

        FLUX responds to plain-English descriptions, so the profile's ancestry and
        morphology are injected as prose rather than the tag-style tokens used for SDXL.
        """
        if not profile:
            return prompt
        _gender_token, ancestry_term, morphology = self._profile_to_prompt_parts(profile)
        # ancestry_term already carries the gendered noun ("Nigerian woman").
        word = "woman" if forced_gender == "female" else "man"
        subject = ancestry_term if ancestry_term else f"a young {word}"
        parts = [subject]
        if morphology:
            parts.append(morphology)
        parts.append(prompt)
        return ", ".join(parts)

    # -----------------------------------------------------------------------
    # Ollama
    # -----------------------------------------------------------------------

    async def _get_loaded_model(self, client: httpx.AsyncClient) -> str:
        r = await client.get(f"{self.valves.ollama_url}/api/ps")
        models = r.json().get("models", [])
        if models:
            return models[0]["name"]
        if self.valves.ollama_model:
            return self.valves.ollama_model
        raise RuntimeError("No model loaded in Ollama and ollama_model valve is not set.")

    async def _generate_negative_prompt(
        self, client: httpx.AsyncClient, positive: str, prefix: str
    ) -> str:
        model = await self._get_loaded_model(client)
        r = await client.post(
            f"{self.valves.ollama_url}/api/generate",
            json={
                "model": model,
                "system": self.valves.negative_prompt_system,
                "prompt": positive,
                "stream": False,
            },
            timeout=httpx.Timeout(self.valves.request_timeout_seconds),
        )
        r.raise_for_status()
        generated = r.json()["response"].strip()
        return (prefix + generated) if generated else prefix + self.valves.negative_prompt_fallback

    # -----------------------------------------------------------------------
    # ComfyUI workflow
    # -----------------------------------------------------------------------

    @staticmethod
    def _workflow(
        positive: str, negative: str, checkpoint: str,
        width: int, height: int, steps: int, cfg: float,
        seed: int, sampler: str, scheduler: str,
    ) -> dict[str, dict[str, object]]:
        return {
            "4": {
                "inputs": {"ckpt_name": checkpoint},
                "class_type": "CheckpointLoaderSimple",
                "_meta": {"title": "Load Checkpoint"},
            },
            "5": {
                "inputs": {"width": width, "height": height, "batch_size": 1},
                "class_type": "EmptyLatentImage",
                "_meta": {"title": "Empty Latent Image"},
            },
            "6": {
                "inputs": {"text": positive, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Positive Prompt"},
            },
            "7": {
                "inputs": {"text": negative, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Negative Prompt"},
            },
            "8": {
                "inputs": {
                    "seed": seed, "steps": steps, "cfg": cfg,
                    "sampler_name": sampler, "scheduler": scheduler, "denoise": 1.0,
                    "model": ["4", 0], "positive": ["6", 0], "negative": ["7", 0],
                    "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"},
            },
            "9": {
                "inputs": {"samples": ["8", 0], "vae": ["4", 2]},
                "class_type": "VAEDecode",
                "_meta": {"title": "VAE Decode"},
            },
            "10": {
                "inputs": {"filename_prefix": "open-webui/anime", "images": ["9", 0]},
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"},
            },
        }

    @staticmethod
    def _flux_workflow(
        positive: str, width: int, height: int, steps: int, seed: int, guidance: float,
        unet: str, weight_dtype: str, clip_l: str, t5xxl: str, vae: str,
    ) -> dict[str, dict[str, object]]:
        """FLUX Schnell graph: UNET/DualCLIP/VAE loaders + CLIPTextEncodeFlux, CFG 1.

        Ported from compose/comfyui/workflows/flux-schnell-workflow.json. No negative
        conditioning -- Schnell is guidance-distilled, so KSampler runs at CFG 1 with the
        positive conditioning wired into both the positive and negative slots.
        """
        return {
            "1": {
                "inputs": {"unet_name": unet, "weight_dtype": weight_dtype},
                "class_type": "UNETLoader",
                "_meta": {"title": "Load Diffusion Model"},
            },
            "2": {
                "inputs": {"clip_name1": clip_l, "clip_name2": t5xxl, "type": "flux"},
                "class_type": "DualCLIPLoader",
                "_meta": {"title": "DualCLIPLoader"},
            },
            "3": {
                "inputs": {"vae_name": vae},
                "class_type": "VAELoader",
                "_meta": {"title": "Load VAE"},
            },
            "4": {
                "inputs": {
                    "clip_l": positive, "t5xxl": positive,
                    "guidance": guidance, "clip": ["2", 0],
                },
                "class_type": "CLIPTextEncodeFlux",
                "_meta": {"title": "CLIP Text Encode (Flux)"},
            },
            "5": {
                "inputs": {"width": width, "height": height, "batch_size": 1},
                "class_type": "EmptySD3LatentImage",
                "_meta": {"title": "EmptySD3LatentImage"},
            },
            "6": {
                "inputs": {
                    "seed": seed, "steps": steps, "cfg": 1.0,
                    "sampler_name": "euler", "scheduler": "simple", "denoise": 1.0,
                    "model": ["1", 0], "positive": ["4", 0],
                    "negative": ["4", 0], "latent_image": ["5", 0],
                },
                "class_type": "KSampler",
                "_meta": {"title": "KSampler"},
            },
            "7": {
                "inputs": {"samples": ["6", 0], "vae": ["3", 0]},
                "class_type": "VAEDecode",
                "_meta": {"title": "VAE Decode"},
            },
            "8": {
                "inputs": {"filename_prefix": "open-webui/flux", "images": ["7", 0]},
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"},
            },
        }

    @staticmethod
    def _extract_first_image(history_item: _HistoryItem) -> _ImageInfo:
        for node_output in history_item.get("outputs", {}).values():
            images = node_output.get("images", [])
            if images:
                return images[0]
        raise RuntimeError("ComfyUI completed but returned no image output.")

    # -----------------------------------------------------------------------
    # Public tool function
    # -----------------------------------------------------------------------

    async def generate_custom_image(
        self,
        prompt: str,
        gender: Gender,
        orientation: Orientation,
        checkpoint: str,
        ethnicity: Ethnicity = "east_african",
        custom_size: str = "",
        seed: Optional[int] = None,
        __event_emitter__: Optional[Callable[..., Awaitable[None]]] = None,
    ):
        """
        Generate a custom image via ComfyUI whenever the user asks to create, draw, or generate an image, illustration, artwork, anime character, group of people, scene, landscape, or photo; the tool auto-generates the negative prompt and quality tags, so do not supply them

        :param prompt: Plain-language description of the image such as subject, style, mood, clothing, pose, setting, and lighting; do NOT add quality tags, the tool prepends them automatically -- REQUIRED
        :param ethnicity: Ethnic and morphological group for a person's face, one of none, diverse, west_african, east_african, south_african, north_african, arab, southeast_asian, east_asian, indian, iranian, chinese, latin_american, european, australian, native_american, aboriginal, north_american, south_american; use none for a scene with no person, use diverse for a mixed group of people, otherwise the closest to the user description, and if the user does not specify a person's ethnicity leave it as the default east_african -- OPTIONAL
        :param gender: Subject gender, one of none, male, or female; use none for a scene or landscape with no specific person -- REQUIRED
        :param orientation: Canvas shape, one of portrait (832x1216 single character), landscape (1216x832 scenes and groups), square (1024x1024 balanced default), wide (1344x768 cinematic scenery), tall (768x1344 full body), or other (a custom size supplied in custom_size) -- REQUIRED
        :param custom_size: Custom image size as WIDTHxHEIGHT in pixels such as 832x1216, used only when orientation is other, each side between 256 and 1536 -- OPTIONAL
        :param checkpoint: Model style, one of animagine or illustrious for anime and illustration, or sdxl or flux for photorealistic and cinematic images; if several styles could fit the request reuse the same checkpoint as the previous image in this conversation, and only change it when the user explicitly requests a different style -- REQUIRED
        :param seed: Integer seed for reproducibility, omit for a random seed -- OPTIONAL
        :return: Short confirmation that the image was generated and already displayed to the user (with seed, checkpoint, size, a direct link to the image, plus the negative prompt for SDXL models); the image is shown to the user automatically, so do not try to render, re-generate, or describe it again
        """
        errors: list[str] = []
        if not prompt or not prompt.strip():
            errors.append("prompt: cannot be empty.")

        eth = (ethnicity or "").strip().lower().replace(" ", "_").replace("-", "_")
        if eth not in _ETHNICITIES:
            errors.append(
                "ethnicity: invalid -- must be EXACTLY one of: " + ", ".join(_ETHNICITIES) + "."
            )

        gen = (gender or "").strip().lower()
        gen = _GENDER_ALIASES.get(gen, gen)
        if gen not in _GENDERS:
            errors.append(
                "gender: invalid -- must be EXACTLY one of: " + ", ".join(_GENDERS) + "."
            )

        ori_key = (orientation or "").strip().lower()
        custom_wh: Optional[tuple[int, int]] = None
        if ori_key == "other":
            try:
                custom_wh = self._parse_custom_size(custom_size)
            except ValueError as exc:
                errors.append(str(exc))
        elif ori_key not in _ORIENTATION:
            errors.append(
                "orientation: invalid -- must be one of "
                + ", ".join(list(_ORIENTATION) + ["other"]) + "."
            )
        if not checkpoint or not checkpoint.strip():
            errors.append(
                "checkpoint: required -- must be one of: animagine, illustrious, sdxl, flux."
            )
        if errors:
            raise ValueError("Missing or invalid parameters:\n" + "\n".join(f"  - {e}" for e in errors))
        prompt = prompt.strip()

        # Resolve checkpoint and preset
        ckpt = self._resolve_checkpoint(checkpoint)
        preset = self._get_preset(ckpt)
        family = preset.get("family", "sdxl")

        # Resolve orientation (ori_key / custom_wh were validated above)
        if ori_key == "other" and custom_wh is not None:
            width, height = custom_wh
        else:
            width, height = _ORIENTATION.get(ori_key, _ORIENTATION["square"])

        # Steps: FLUX Schnell is a distilled few-step model, so its preset steps are
        # authoritative. For SDXL-family models the generation_steps valve overrides.
        if family == "flux":
            steps = preset["steps"]
        else:
            steps = self.valves.generation_steps if self.valves.generation_steps > 0 else preset["steps"]

        seed = seed if seed is not None else random.randint(0, 2**63 - 1)

        _forced_gender = gen if gen in ("male", "female") else None  # "none" -> None

        # Inject a morphology profile only for a single specific person (a real ethnicity
        # AND a concrete gender). "none" (scene) and "diverse" (group) skip the profile.
        if eth not in ("none", "diverse") and _forced_gender is not None:
            profiles = self._load_profiles()
            profile, _resolved_pid = self._resolve_profile(eth, gen, profiles)
        else:
            profile = None

        # Build positive prompt
        if family == "flux":
            if eth == "diverse":
                positive = f"a diverse group of people of various ethnicities and skin tones, {prompt}"
            else:
                positive = self._build_flux_positive(prompt, profile, _forced_gender)
            negative_prefix = ""
        else:
            quality_tags = preset["quality"]
            if eth == "diverse":
                # Mixed group: no single morphology, no "solo" token.
                negative_prefix = ""
                positive = f"{quality_tags}, multiple people, diverse group of people, various ethnicities, mixed skin tones, {prompt}"
            elif profile:
                gender_token, ancestry_term, morphology = self._profile_to_prompt_parts(profile)
                if _forced_gender == "female":
                    gender_token = "1girl, female focus"
                else:
                    gender_token = "1boy, male focus"
                negative_prefix = self._gender_negative_prefix(gender_token)
                parts = [quality_tags, gender_token, "solo", "young adult"]
                if ancestry_term:
                    parts.append(ancestry_term)
                if morphology:
                    parts.append(morphology)
                parts.append(prompt)
                positive = ", ".join(parts)
            elif _forced_gender == "female":
                # Concrete gender but no ethnicity profile: bare gender token, no scene.
                negative_prefix = self._gender_negative_prefix("1girl")
                positive = f"{quality_tags}, 1girl, female focus, solo, {prompt}"
            elif _forced_gender == "male":
                negative_prefix = self._gender_negative_prefix("1boy")
                positive = f"{quality_tags}, 1boy, male focus, solo, {prompt}"
            else:
                # Scene / no specific person.
                negative_prefix = ""
                positive = f"{quality_tags}, {prompt}"

        base_url = self.valves.comfyui_url.rstrip("/")
        http_timeout = httpx.Timeout(self.valves.request_timeout_seconds)

        async def emit(description: str, done: bool = False):
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": description, "done": done}})

        async with httpx.AsyncClient(timeout=http_timeout) as client:

            if family == "flux":
                # FLUX Schnell is guidance-distilled (CFG 1) and ignores negative
                # prompts, so the Ollama negative-prompt step is skipped entirely.
                negative = ""
                workflow = self._flux_workflow(
                    positive, width, height, steps, seed,
                    float(preset.get("guidance", 3.5)),
                    self.valves.flux_unet, self.valves.flux_weight_dtype,
                    self.valves.flux_clip_l, self.valves.flux_t5xxl, self.valves.flux_vae,
                )
            else:
                # Negative prompt via Ollama
                await emit("Generating negative prompt...")
                try:
                    negative = await self._generate_negative_prompt(client, positive, negative_prefix)
                    if not negative:
                        raise ValueError("Empty response from Ollama.")
                except Exception as exc:
                    await emit(f"Negative prompt generation failed ({exc}), using fallback.")
                    negative = negative_prefix + self.valves.negative_prompt_fallback

                workflow = self._workflow(
                    positive, negative, ckpt, width, height,
                    steps, preset["cfg"], seed, preset["sampler"], preset["scheduler"],
                )

            # ComfyUI health check
            await emit("Submitting workflow to ComfyUI...")
            try:
                r = await client.get(f"{base_url}/system_stats")
                r.raise_for_status()
            except Exception as exc:
                await emit("Could not reach ComfyUI.", done=True)
                raise RuntimeError(f"Cannot reach ComfyUI at {base_url}: {exc}") from exc

            # Submit workflow
            r = await client.post(
                f"{base_url}/prompt",
                json={"prompt": workflow, "client_id": str(uuid.uuid4())},
            )
            if r.status_code >= 400:
                raise RuntimeError(f"ComfyUI rejected the workflow: {r.status_code} {r.text[:2000]}")
            prompt_id = r.json().get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI returned no prompt_id: {r.text}")

            # Poll until done
            await emit(f"Generating image (seed {seed})...")
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

            # Fetch the generated image
            image_info = self._extract_first_image(history_item)
            img_r = await client.get(
                f"{base_url}/view",
                params={
                    "filename": image_info.get("filename", ""),
                    "subfolder": image_info.get("subfolder", ""),
                    "type": image_info.get("type", "output"),
                },
            )
            img_r.raise_for_status()
            image_bytes = img_r.content
            mime_type = img_r.headers.get("content-type", "image/png").split(";")[0]

            # ComfyUI's own /view URL for the image. It only returns the filename parts,
            # so assemble the endpoint; use the browser-reachable base when configured.
            view_base = (self.valves.comfyui_public_url or "").rstrip("/") or base_url
            image_url = f"{view_base}/view?" + urllib.parse.urlencode({
                "filename": image_info.get("filename", ""),
                "subfolder": image_info.get("subfolder", ""),
                "type": image_info.get("type", "output"),
            })

        await emit("Image generated successfully.", done=True)

        encoded = base64.b64encode(image_bytes).decode("ascii")
        profile_note = f"<br><strong>Profile:</strong> {profile.get('profile_id', '')}" if profile else ""

        embed_html = f"""<!DOCTYPE html>
<html>
<head><style>
  body {{margin:0;padding:0;font-family:sans-serif;font-size:13px}}
  img {{display:block;width:100%;height:auto;border-radius:8px}}
  details {{margin-top:10px;line-height:1.5}}
  summary {{cursor:pointer;font-weight:bold}}
</style></head>
<body>
  <img id="gi" src="data:{mime_type};base64,{encoded}" alt="Generated image" />
  <details open>
    <summary>Generation details</summary>
    <strong>Checkpoint:</strong> {ckpt}<br>
    <strong>Seed:</strong> {seed}<br>
    <strong>Size:</strong> {width}x{height} ({ori_key})<br>
    <strong>Steps / CFG:</strong> {steps} / {preset['cfg']}{profile_note}
  </details>
  <a href="{image_url}" target="_blank" rel="noopener" style="display:inline-block;margin-top:8px;font-size:12px">Open full image</a>
  <script>
    function reportHeight() {{
      var h = document.documentElement.scrollHeight;
      parent.postMessage({{ type: 'iframe:height', height: h }}, '*');
    }}
    window.addEventListener('load', reportHeight);
    document.getElementById('gi').addEventListener('load', reportHeight);
    new ResizeObserver(reportHeight).observe(document.body);
  </script>
</body></html>"""

        if __event_emitter__:
            await __event_emitter__({"type": "embeds", "data": {"embeds": [embed_html]}})

        summary = f"Image generated. Seed: {seed}, Checkpoint: {ckpt}, Size: {width}x{height}."
        if negative:
            summary += f"\nNegative prompt: {negative}"
        summary += f"\nImage: {image_url}"
        return summary
