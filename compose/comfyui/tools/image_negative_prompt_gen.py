"""
title: ComfyUI Anime Generator
author: OpenAI
description: Generate anime images through ComfyUI using separate positive and negative prompts.
required_open_webui_version: 0.6.0
requirements: httpx
version: 1.0.0
licence: MIT
"""

import asyncio
import base64
import html
import random
import time
import uuid
from typing import Callable, Optional

import httpx
from pydantic import BaseModel, Field
from starlette.responses import HTMLResponse


class Tools:
    class Valves(BaseModel):
        comfyui_url: str = Field(
            default="http://comfyui:8188",
            description="ComfyUI URL reachable from Open WebUI, e.g. http://comfyui:8188",
        )
        default_checkpoint: str = Field(
            default="animagine-xl-4.0-opt.safetensors",
            description="Exact checkpoint filename shown by ComfyUI.",
        )
        default_width: int = Field(default=1024)
        default_height: int = Field(default=1024)
        default_steps: int = Field(default=28)
        default_cfg: float = Field(default=5.0)
        sampler_name: str = Field(default="euler_ancestral")
        scheduler: str = Field(default="normal")
        request_timeout_seconds: int = Field(default=30)
        generation_timeout_seconds: int = Field(default=300)
        poll_interval_seconds: float = Field(default=1.0)

    def __init__(self):
        self.valves = self.Valves()

    @staticmethod
    def _workflow(
        positive_prompt: str,
        negative_prompt: str,
        checkpoint: str,
        width: int,
        height: int,
        steps: int,
        cfg: float,
        seed: int,
        sampler_name: str,
        scheduler: str,
    ) -> dict:
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
                "inputs": {"text": positive_prompt, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Positive Prompt"},
            },
            "7": {
                "inputs": {"text": negative_prompt, "clip": ["4", 1]},
                "class_type": "CLIPTextEncode",
                "_meta": {"title": "Negative Prompt"},
            },
            "8": {
                "inputs": {
                    "seed": seed,
                    "steps": steps,
                    "cfg": cfg,
                    "sampler_name": sampler_name,
                    "scheduler": scheduler,
                    "denoise": 1.0,
                    "model": ["4", 0],
                    "positive": ["6", 0],
                    "negative": ["7", 0],
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
                "inputs": {
                    "filename_prefix": "open-webui/anime",
                    "images": ["9", 0],
                },
                "class_type": "SaveImage",
                "_meta": {"title": "Save Image"},
            },
        }

    @staticmethod
    def _validate_dimension(value: int, name: str) -> int:
        if value < 512 or value > 2048:
            raise ValueError(f"{name} must be between 512 and 2048.")
        if value % 64 != 0:
            raise ValueError(f"{name} must be a multiple of 64.")
        return value

    @staticmethod
    def _extract_first_image(history_item: dict) -> dict:
        for node_output in history_item.get("outputs", {}).values():
            images = node_output.get("images", [])
            if images:
                return images[0]
        raise RuntimeError("ComfyUI completed but returned no image output.")

    async def generate_anime_image(
        self,
        positive_prompt: str,
        negative_prompt: str,
        checkpoint: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        steps: Optional[int] = None,
        cfg: Optional[float] = None,
        seed: Optional[int] = None,
        __event_emitter__: Optional[Callable] = None,
    ) -> HTMLResponse:
        """
        Generate one anime image with separate positive and negative prompts.

        Use this tool whenever the user asks to create an anime image.

        The positive prompt must preserve the user's requested subject count, gender,
        age, skin tone or ethnicity, clothing, cultural details, pose, framing,
        setting, lighting, mood and style.

        The negative prompt must exclude likely contradictions to the user's request,
        plus malformed anatomy, malformed hands, extra or missing fingers, text,
        logos, signatures, watermarks, blur and low quality. Never negate a requested trait.

        :param positive_prompt: Detailed comma-separated description of what should appear.
        :param negative_prompt: Targeted comma-separated description of what must not appear.
        :param checkpoint: Exact ComfyUI checkpoint filename; omit for the configured default.
        :param width: Width from 512 to 2048, divisible by 64.
        :param height: Height from 512 to 2048, divisible by 64.
        :param steps: Sampling steps, normally 20-40.
        :param cfg: Guidance strength, normally 4-7.
        :param seed: Optional deterministic seed; omit for random.
        """
        positive_prompt = positive_prompt.strip()
        negative_prompt = negative_prompt.strip()
        if not positive_prompt:
            raise ValueError("positive_prompt cannot be empty.")
        if not negative_prompt:
            raise ValueError("negative_prompt cannot be empty.")

        checkpoint = checkpoint or self.valves.default_checkpoint
        width = self._validate_dimension(width or self.valves.default_width, "width")
        height = self._validate_dimension(height or self.valves.default_height, "height")
        steps = steps or self.valves.default_steps
        cfg = cfg or self.valves.default_cfg
        seed = seed if seed is not None else random.randint(0, 2**63 - 1)

        if not 1 <= steps <= 100:
            raise ValueError("steps must be between 1 and 100.")
        if not 1.0 <= cfg <= 20.0:
            raise ValueError("cfg must be between 1.0 and 20.0.")

        base_url = self.valves.comfyui_url.rstrip("/")
        workflow = self._workflow(
            positive_prompt,
            negative_prompt,
            checkpoint,
            width,
            height,
            steps,
            cfg,
            seed,
            self.valves.sampler_name,
            self.valves.scheduler,
        )

        async def emit_status(description: str, done: bool = False):
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": description, "done": done},
                })

        await emit_status("Submitting workflow to ComfyUI…")
        timeout = httpx.Timeout(self.valves.request_timeout_seconds)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                r = await client.get(f"{base_url}/system_stats")
                r.raise_for_status()
            except Exception as exc:
                await emit_status("Could not reach ComfyUI.", done=True)
                raise RuntimeError(f"Cannot reach ComfyUI at {base_url}: {exc}") from exc

            r = await client.post(
                f"{base_url}/prompt",
                json={"prompt": workflow, "client_id": str(uuid.uuid4())},
            )
            if r.status_code >= 400:
                raise RuntimeError(
                    f"ComfyUI rejected the workflow: {r.status_code} {r.text[:2000]}"
                )

            prompt_id = r.json().get("prompt_id")
            if not prompt_id:
                raise RuntimeError(f"ComfyUI returned no prompt_id: {r.text}")

            await emit_status(f"Generating image in ComfyUI (seed {seed})…")
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
                        raise RuntimeError(
                            f"ComfyUI workflow failed: {status.get('messages', [])}"
                        )
                    if history_item.get("outputs"):
                        break
                await asyncio.sleep(self.valves.poll_interval_seconds)

            if not history_item or not history_item.get("outputs"):
                raise TimeoutError("Timed out waiting for ComfyUI.")

            image_info = self._extract_first_image(history_item)
            image_response = await client.get(
                f"{base_url}/view",
                params={
                    "filename": image_info["filename"],
                    "subfolder": image_info.get("subfolder", ""),
                    "type": image_info.get("type", "output"),
                },
            )
            image_response.raise_for_status()
            image_bytes = image_response.content
            mime_type = image_response.headers.get("content-type", "image/png").split(";")[0]

        await emit_status("Image generated successfully.", done=True)

        encoded = base64.b64encode(image_bytes).decode("ascii")
        body = f"""
        <div style="max-width:900px;margin:0 auto">
          <img src="data:{mime_type};base64,{encoded}" alt="Generated anime image"
               style="display:block;width:100%;height:auto;border-radius:12px" />
          <details style="margin-top:12px">
            <summary style="cursor:pointer">Generation details</summary>
            <div style="margin-top:8px;line-height:1.45">
              <strong>Checkpoint:</strong> {html.escape(checkpoint)}<br>
              <strong>Seed:</strong> {seed}<br>
              <strong>Size:</strong> {width} × {height}<br>
              <strong>Steps / CFG:</strong> {steps} / {cfg}<br><br>
              <strong>Positive prompt</strong>
              <div style="white-space:pre-wrap">{html.escape(positive_prompt)}</div><br>
              <strong>Negative prompt</strong>
              <div style="white-space:pre-wrap">{html.escape(negative_prompt)}</div>
            </div>
          </details>
        </div>
        """
        return HTMLResponse(content=body, headers={"Content-Disposition": "inline"})
