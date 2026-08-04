# ComfyUI Negative Prompt Auto-Generation Tool — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update `image_negative_prompt_gen.py` so the tool auto-generates a contextual negative prompt via the already-loaded Ollama model, feeding both prompts to ComfyUI instead of relying on the LLM to supply a negative prompt.

**Architecture:** Single file edit — `compose/comfyui/tools/image_negative_prompt_gen.py`. Add 4 valves, 2 new async internal methods (`_get_loaded_model`, `_generate_negative_prompt`), and update `generate_anime_image` to remove `negative_prompt` as a parameter and call those methods internally, with a hardcoded fallback if Ollama is unavailable.

**Tech Stack:** Python 3.11+, httpx (already declared in tool requirements), pydantic, Open WebUI Tool API.

## Global Constraints

- Single file only: `compose/comfyui/tools/image_negative_prompt_gen.py` — no other project files modified.
- No new Docker services, no compose changes.
- `negative_prompt` must never appear as a parameter in the public tool signature — Gemma4 must not be prompted to supply it.
- Negative prompt generation must degrade gracefully to `negative_prompt_fallback` if Ollama is unreachable or returns empty.
- ComfyUI errors must still raise — no silent image generation failures.
- The file header docstring metadata block must be preserved exactly (title, author, description, required_open_webui_version, requirements, version, licence).
- ASCII-only strings in the Python source — no `×`, `—`, `…` or other non-ASCII characters (Windows cp1252 cannot encode them).

---

### Task 1: Add new valves and internal methods

**Files:**
- Modify: `compose/comfyui/tools/image_negative_prompt_gen.py`
- Test: `.scratch/tmp/test_neg_tool.py` (offline test, stdlib only — no httpx import needed)

**Interfaces:**
- Produces: `Tools._get_loaded_model(self, client) -> str`
- Produces: `Tools._generate_negative_prompt(self, client, positive_prompt: str) -> str`

- [ ] **Step 1: Write the offline tests**

Create `.scratch/tmp/test_neg_tool.py` with this exact content:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock


# Inline stubs matching the spec -- tested independently of the tool module
# (avoids needing httpx installed on the host).

async def _get_loaded_model(valves, client):
    r = await client.get(f"{valves.ollama_url}/api/ps")
    models = r.json().get("models", [])
    if models:
        return models[0]["name"]
    if valves.ollama_model:
        return valves.ollama_model
    raise RuntimeError("No model loaded in Ollama and ollama_model valve is not set.")


async def _generate_negative_prompt(valves, client, positive_prompt):
    model = await _get_loaded_model(valves, client)
    r = await client.post(
        f"{valves.ollama_url}/api/generate",
        json={
            "model": model,
            "system": valves.negative_prompt_system,
            "prompt": positive_prompt,
            "stream": False,
        },
    )
    r.raise_for_status()
    return r.json()["response"].strip()


def make_valves(ollama_model=""):
    v = MagicMock()
    v.ollama_url = "http://ollama:11434"
    v.ollama_model = ollama_model
    v.negative_prompt_system = "Output only a negative prompt."
    return v


def make_client_with_ps(model_name):
    client = AsyncMock()
    client.get.return_value.json.return_value = (
        {"models": [{"name": model_name}]} if model_name else {"models": []}
    )
    return client


async def test_get_loaded_model_from_ps():
    result = await _get_loaded_model(
        make_valves(), make_client_with_ps("gemma4:12b-instruct-qat")
    )
    assert result == "gemma4:12b-instruct-qat", f"got {result}"
    print("PASS test_get_loaded_model_from_ps")


async def test_get_loaded_model_fallback_to_valve():
    result = await _get_loaded_model(
        make_valves("gemma4:12b-instruct-qat"), make_client_with_ps(None)
    )
    assert result == "gemma4:12b-instruct-qat", f"got {result}"
    print("PASS test_get_loaded_model_fallback_to_valve")


async def test_get_loaded_model_raises_when_nothing_configured():
    try:
        await _get_loaded_model(make_valves(""), make_client_with_ps(None))
        assert False, "should have raised RuntimeError"
    except RuntimeError as e:
        assert "No model loaded" in str(e)
    print("PASS test_get_loaded_model_raises_when_nothing_configured")


async def test_generate_negative_prompt_returns_stripped_response():
    client = make_client_with_ps("gemma4:12b-instruct-qat")
    client.post.return_value.json.return_value = {"response": "  bad anatomy, blurry  "}
    result = await _generate_negative_prompt(make_valves(), client, "1girl, anime")
    assert result == "bad anatomy, blurry", f"got '{result}'"
    print("PASS test_generate_negative_prompt_returns_stripped_response")


async def test_generate_negative_prompt_raises_on_http_error():
    client = make_client_with_ps("gemma4:12b-instruct-qat")
    client.post.return_value.raise_for_status.side_effect = Exception("500 Server Error")
    try:
        await _generate_negative_prompt(make_valves(), client, "1girl, anime")
        assert False, "should have raised"
    except Exception as e:
        assert "500" in str(e)
    print("PASS test_generate_negative_prompt_raises_on_http_error")


if __name__ == "__main__":
    asyncio.run(test_get_loaded_model_from_ps())
    asyncio.run(test_get_loaded_model_fallback_to_valve())
    asyncio.run(test_get_loaded_model_raises_when_nothing_configured())
    asyncio.run(test_generate_negative_prompt_returns_stripped_response())
    asyncio.run(test_generate_negative_prompt_raises_on_http_error())
    print("All tests passed.")
```

- [ ] **Step 2: Run tests — all 5 must pass**

```
python C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance\.scratch\tmp\test_neg_tool.py
```

Expected output — exactly these lines, in order:
```
PASS test_get_loaded_model_from_ps
PASS test_get_loaded_model_fallback_to_valve
PASS test_get_loaded_model_raises_when_nothing_configured
PASS test_generate_negative_prompt_returns_stripped_response
PASS test_generate_negative_prompt_raises_on_http_error
All tests passed.
```

If any test fails, fix the stub in the test file (the stubs ARE the spec) and re-run before continuing.

- [ ] **Step 3: Add 4 new valves to the `Valves` class**

In `compose/comfyui/tools/image_negative_prompt_gen.py`, insert these 4 fields immediately after the `comfyui_url` field (line 29), before `default_checkpoint`:

```python
        ollama_url: str = Field(
            default="http://ollama:11434",
            description="Ollama endpoint reachable from Open WebUI, e.g. http://ollama:11434",
        )
        ollama_model: str = Field(
            default="",
            description="Override model name for negative prompt generation. Empty = auto-detect from /api/ps.",
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
```

- [ ] **Step 4: Add `_get_loaded_model` method**

Insert this method into the `Tools` class, immediately after `_extract_first_image` (after line 126):

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

- [ ] **Step 5: Add `_generate_negative_prompt` method**

Insert this method immediately after `_get_loaded_model`:

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
            timeout=httpx.Timeout(self.valves.request_timeout_seconds),
        )
        r.raise_for_status()
        return r.json()["response"].strip()
```

- [ ] **Step 6: Syntax check**

```
python -m py_compile C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance\compose\comfyui\tools\image_negative_prompt_gen.py
```

Expected: no output (silent = OK). Any output means a syntax error — fix before continuing.

- [ ] **Step 7: Commit**

```
git add compose/comfyui/tools/image_negative_prompt_gen.py .scratch/tmp/test_neg_tool.py
git commit -m "feat: add Ollama valves and negative prompt methods to ComfyUI tool"
```

---

### Task 2: Wire auto-generation into `generate_anime_image`

**Files:**
- Modify: `compose/comfyui/tools/image_negative_prompt_gen.py`

**Interfaces:**
- Consumes: `self._generate_negative_prompt(client, positive_prompt) -> str` (Task 1)
- Consumes: `self.valves.negative_prompt_fallback: str` (Task 1)

- [ ] **Step 1: Replace the entire `generate_anime_image` method**

The method currently starts at line 128 (`async def generate_anime_image`) and ends at line 283 (`return HTMLResponse(...)`). Replace it in its entirety with:

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
        """
        Generate one anime image from a positive prompt.

        Use this tool whenever the user asks to create an anime image or illustration.

        The positive prompt must preserve the user's requested subject count, gender,
        age, skin tone or ethnicity, clothing, cultural details, pose, framing,
        setting, lighting, mood and style. Begin with quality tags: masterpiece,
        high score, great score, absurdres.

        The negative prompt is generated automatically -- do not supply it.

        :param positive_prompt: Detailed comma-separated description of what should appear.
        :param checkpoint: Exact ComfyUI checkpoint filename; omit for the configured default.
        :param width: Width from 512 to 2048, divisible by 64.
        :param height: Height from 512 to 2048, divisible by 64.
        :param steps: Sampling steps, normally 20-40.
        :param cfg: Guidance strength, normally 4-7.
        :param seed: Optional deterministic seed; omit for random.
        """
        positive_prompt = positive_prompt.strip()
        if not positive_prompt:
            raise ValueError("positive_prompt cannot be empty.")

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
        timeout = httpx.Timeout(self.valves.request_timeout_seconds)

        async def emit_status(description: str, done: bool = False):
            if __event_emitter__:
                await __event_emitter__({
                    "type": "status",
                    "data": {"description": description, "done": done},
                })

        async with httpx.AsyncClient(timeout=timeout) as client:
            await emit_status("Generating negative prompt...")
            try:
                negative_prompt = await self._generate_negative_prompt(client, positive_prompt)
                if not negative_prompt:
                    raise ValueError("Empty response from Ollama.")
            except Exception as exc:
                await emit_status(f"Negative prompt generation failed ({exc}), using fallback.")
                negative_prompt = self.valves.negative_prompt_fallback

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

            await emit_status("Submitting workflow to ComfyUI...")
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

            await emit_status(f"Generating image (seed {seed})...")
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
              <strong>Size:</strong> {width} x {height}<br>
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
```

- [ ] **Step 2: Syntax check**

```
python -m py_compile C:\Users\murad.karrar\Documents\Codes_local\local-ai-appliance\compose\comfyui\tools\image_negative_prompt_gen.py
```

Expected: silent. Any output = syntax error, fix before continuing.

- [ ] **Step 3: Commit**

```
git add compose/comfyui/tools/image_negative_prompt_gen.py
git commit -m "feat: wire auto-generated negative prompt into generate_anime_image"
```

---

### Task 3: Deploy to Open WebUI and verify

This task is manual. No code changes.

- [ ] **Step 1: Open the final tool file**

Read `compose/comfyui/tools/image_negative_prompt_gen.py` and copy its entire contents to clipboard.

- [ ] **Step 2: Create the tool in Open WebUI**

1. Open WebUI admin UI → **Workspace → Tools**
2. Click **+** (Create new tool)
3. Paste the file content into the code editor
4. Click **Save**
5. Confirm: no red error banner appears in the editor

- [ ] **Step 3: Set valves**

In the tool's settings panel (gear/cog icon next to the tool):
- `comfyui_url`: `http://comfyui:8188`
- `ollama_url`: `http://ollama:11434`
- `ollama_model`: leave empty (auto-detect)
- All other valves: leave at defaults
- Save

- [ ] **Step 4: Enable the tool for Gemma4**

**Workspace → Models → Gemma4** → scroll to the Tools section → toggle on **ComfyUI Anime Generator** → Save

- [ ] **Step 5: Test — happy path**

Start a new chat with Gemma4 and send:

```
Draw an anime girl reading a book in a cosy rainy library, warm lighting, detailed background
```

Expected in order:
1. Status bubble: `Generating negative prompt...`
2. Status bubble: `Submitting workflow to ComfyUI...`
3. Status bubble: `Generating image (seed XXXXXXX)...`
4. Status bubble: `Image generated successfully.`
5. Inline image renders in the chat message
6. Expand **Generation details** — confirm:
   - **Positive prompt** is non-empty and matches what the LLM wrote
   - **Negative prompt** is non-empty and contextual (not just the fallback — look for subject-specific terms beyond the generic anatomy list)

- [ ] **Step 6: Test — Ollama fallback**

Temporarily set `ollama_url` valve to `http://invalid-host:11434`. Send another image request.

Expected:
1. Status bubble: `Negative prompt generation failed (...), using fallback.`
2. Status bubble: `Submitting workflow to ComfyUI...`
3. Image generates successfully
4. **Generation details** shows the fallback text: `lowres, bad anatomy, bad hands, extra fingers, missing fingers, blurry, worst quality, low quality, watermark, signature, text`

After confirming, restore `ollama_url` to `http://ollama:11434` and save.
