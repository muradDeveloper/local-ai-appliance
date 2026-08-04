# Design: ComfyUI Negative Prompt Auto-Generation Tool

**Date:** 2026-08-04  
**Status:** Approved — ready for implementation  
**File:** `compose/comfyui/tools/image_negative_prompt_gen.py`

---

## Problem

Open WebUI's built-in ComfyUI integration only populates the positive prompt (node 6). The negative prompt node (node 7) stays hardcoded at the workflow default — a generic artefact list that is not tailored to the subject being drawn. This limits image quality for anime/illustration models (Animagine XL, Illustrious XL) that respond strongly to contextual negative prompts.

## Goal

Replace the generic hardcoded negative prompt with one automatically generated from the positive prompt, using the same LLM already in VRAM, with no model swap and no new services.

---

## Architecture

### Integration point

An Open WebUI **Tool** (Python plugin, no Docker changes). Gemma4 calls the tool when the user requests an image. The tool handles both negative prompt generation and ComfyUI submission internally.

### Data flow

```
User: "draw an anime girl reading in a rainy library"
        ↓
  Gemma4 → calls generate_anime_image(positive_prompt="...")
        ↓
  Tool step 1: GET /api/ps → discover loaded model name
  Tool step 2: POST /api/generate to Ollama
               system: <negative_prompt_system valve>
               prompt: <positive_prompt>
               stream: false
               → negative_prompt: "lowres, bad anatomy, extra fingers, ..."
        ↓
  Tool step 3: POST /prompt to ComfyUI
               node 6 ← positive_prompt
               node 7 ← negative_prompt
        ↓
  Tool step 4: poll /history until complete, fetch image bytes
        ↓
  HTMLResponse: inline image + collapsible details (both prompts, seed, size, steps)
```

### Why this approach

- **Same model, no eviction.** Gemma4 is already loaded from the chat turn that triggered the tool. The internal Ollama call hits the same model — no swap, ~3–8 s added latency.
- **Deterministic.** Negative prompt always runs regardless of what the LLM decides to include in the tool call.
- **No new services.** Tool lives in Open WebUI's database. Ollama and ComfyUI are already running.
- **Configurable without code changes.** Key parameters are exposed as valves editable from the Open WebUI admin UI.

---

## Valves

| Valve | Default | Purpose |
|---|---|---|
| `comfyui_url` | `http://comfyui:8188` | ComfyUI endpoint |
| `ollama_url` | `http://ollama:11434` | Ollama endpoint (backend network) |
| `ollama_model` | `""` | Override model name; empty = auto-detect via `/api/ps` |
| `negative_prompt_system` | *(see below)* | System prompt for negative generation — tune from admin UI |
| `negative_prompt_fallback` | `"lowres, bad anatomy, bad hands, extra fingers, missing fingers, blurry, worst quality, low quality, watermark, signature, text"` | Used verbatim if Ollama call fails |
| `default_checkpoint` | `animagine-xl-4.0-opt.safetensors` | ComfyUI checkpoint filename |
| `default_width` | `1024` | Image width |
| `default_height` | `1024` | Image height |
| `default_steps` | `28` | Sampling steps |
| `default_cfg` | `5.0` | CFG guidance scale |
| `sampler_name` | `euler_ancestral` | KSampler sampler |
| `scheduler` | `normal` | KSampler scheduler |
| `request_timeout_seconds` | `30` | HTTP timeout for ComfyUI/Ollama requests |
| `generation_timeout_seconds` | `300` | Max wait for ComfyUI to complete |
| `poll_interval_seconds` | `1.0` | ComfyUI history poll interval |

**Default `negative_prompt_system`:**
```
You are a Stable Diffusion prompt engineer. Given a positive image prompt,
output ONLY a comma-separated negative prompt with no explanation or preamble.
Exclude: anatomy defects (bad anatomy, bad hands, extra fingers, missing fingers,
fused limbs), quality defects (lowres, blurry, jpeg artifacts, noise, worst quality),
and unwanted content (text, watermark, signature, logo, username).
Also exclude traits that contradict the style, mood, or subject in the positive prompt.
Never negate a trait that was explicitly requested.
```

---

## Tool signature

```python
async def generate_anime_image(
    self,
    positive_prompt: str,
    checkpoint: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    steps: Optional[int] = None,
    cfg: Optional[float] = None,
    seed: Optional[int] = None,
    __event_emitter__: Optional[Callable] = None,
) -> HTMLResponse:
```

`negative_prompt` is **not** a parameter — the LLM never supplies it. It is generated inside the tool from `positive_prompt`.

---

## Key internal methods

### `_get_loaded_model`

```python
async def _get_loaded_model(self, client: httpx.AsyncClient) -> str:
    r = await client.get(f"{self.valves.ollama_url}/api/ps")
    models = r.json().get("models", [])
    if models:
        return models[0]["name"]
    if self.valves.ollama_model:
        return self.valves.ollama_model
    raise RuntimeError("No model loaded in Ollama and ollama_model valve is not set.")
```

### `_generate_negative_prompt`

```python
async def _generate_negative_prompt(self, client: httpx.AsyncClient, positive_prompt: str) -> str:
    model = await self._get_loaded_model(client)
    r = await client.post(
        f"{self.valves.ollama_url}/api/generate",
        json={
            "model": model,
            "system": self.valves.negative_prompt_system,
            "prompt": positive_prompt,
            "stream": False,
        },
        timeout=httpx.Timeout(30.0),
    )
    r.raise_for_status()
    return r.json()["response"].strip()
```

---

## Error handling

| Failure | Behaviour |
|---|---|
| Ollama unreachable or `/api/ps` fails | Emit warning, use `negative_prompt_fallback`, continue |
| Ollama returns empty/malformed response | Emit warning, use `negative_prompt_fallback`, continue |
| ComfyUI unreachable | Emit error, raise — no image returned |
| ComfyUI workflow rejected | Emit error, raise — no image returned |

Image generation is never blocked by a failure in the negative prompt step. The fallback produces the same result as the current hardcoded node 7.

---

## Status messages (emitted to chat)

1. `"Generating negative prompt…"`
2. `"Submitting workflow to ComfyUI…"`
3. `"Generating image (seed XXXXXX)…"`
4. `"Image generated successfully."` or error message

---

## ComfyUI workflow

Inline in the tool — same node structure as `animagine-xl-4.0-workflow.json`:

| Node | Type | Source |
|---|---|---|
| `4` | CheckpointLoaderSimple | `checkpoint` valve |
| `5` | EmptyLatentImage | `width` / `height` valves |
| `6` | CLIPTextEncode (Positive) | `positive_prompt` from LLM |
| `7` | CLIPTextEncode (Negative) | auto-generated by tool |
| `8` | KSampler | `steps`, `cfg`, `seed`, `sampler_name`, `scheduler` |
| `9` | VAEDecode | — |
| `10` | SaveImage | prefix `open-webui/anime` |

---

## Deployment

1. Update `compose/comfyui/tools/image_negative_prompt_gen.py` with the final implementation.
2. In Open WebUI admin UI: **Workspace → Tools → Create new tool** → paste file content.
3. Set `ollama_url` and `comfyui_url` valves via the tool settings panel.
4. In Open WebUI admin UI: **Workspace → Models → Gemma4** → enable this tool.
5. Test: ask Gemma4 to generate an image; confirm both prompts appear in the collapsible "Generation details" section of the response.

**No Docker or compose changes required.**  
The existing built-in image generation (`.cfg` files, `prompt_node = 6`) is unaffected — it is a separate code path used by the native image button.

---

## What is not in scope

- Replacing the built-in image generation integration.
- Supporting multiple simultaneous image requests.
- Negative prompt caching or reuse across requests.
- Supporting workflows other than the animagine-xl-4.0 node layout (though the node structure is identical across all three existing workflows).
