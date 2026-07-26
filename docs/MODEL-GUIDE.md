# Model guide for RTX 3060 12 GB

## VRAM budget

The full 12 GB is reserved for Ollama. faster-whisper (STT) and Kokoro (TTS) run on CPU so they consume no VRAM.

Only one model is loaded at a time. Ollama automatically evicts the current model when a different one is requested.

## Planned inference model roster

| Model | Quantisation | Est. VRAM | GPU fit |
|---|---|---|---|
| Qwen3.6-27B-Dense | Q3_K_M | ~13.5 GB | Partial — ~1.5 GB offloads to CPU RAM |
| Qwen3.6-27B-Dense | Q4_K_M | ~16.8 GB | Partial — ~4.8 GB offloads to CPU RAM (avoid) |
| Gemma 4 12B QAT | Q4 | ~7.5 GB | Fits fully |
| Gemma 4 10B | Q4 | ~6.5 GB | Fits fully |
| Hermes 3 8B | Q4 | ~5.0 GB | Fits fully |

Use Q3_K_M for Qwen3.6-27B. The Q4_K_M variant requires nearly 5 GB of CPU RAM offload, which measurably reduces generation speed for the offloaded layers.

## Supporting models

| Model | Purpose | Loaded by |
|---|---|---|
| `qwen2.5-coder:14b-instruct-q4_K_M` | Mem0 memory extraction LLM | Mem0 service |
| `nomic-embed-text:latest` | Mem0 vector embeddings | Mem0 service |

Both supporting models are loaded on demand by Mem0, not Open WebUI. They share the same Ollama instance and count against the one-model-at-a-time limit while active.

## Operating limits

```text
Context:              32768 tokens (OLLAMA_CONTEXT_LENGTH)
Loaded models:        1 (OLLAMA_MAX_LOADED_MODELS)
Parallel generations: 1 (OLLAMA_NUM_PARALLEL)
Users:                2
Keep-alive:           1h (OLLAMA_KEEP_ALIVE)
Flash attention:      enabled (OLLAMA_FLASH_ATTENTION=1)
Cloud features:       disabled (OLLAMA_NO_CLOUD=1)
```

## Pull commands

```bash
# Coding / Mem0 LLM
docker exec ollama ollama pull qwen2.5-coder:14b-instruct-q4_K_M

# Embeddings
docker exec ollama ollama pull nomic-embed-text:latest

# Large reasoning model (use Q3_K_M)
docker exec ollama ollama pull qwen3.6:27b-q3_K_M

# General purpose
docker exec ollama ollama pull gemma4:12b-instruct-qat
docker exec ollama ollama pull gemma4:10b-instruct-q4_K_M
docker exec ollama ollama pull hermes3:8b-q4_K_M
```

Model tags change. Verify current tags on ollama.com/library before pulling.

## Performance checks

```bash
# Confirm GPU is used and check VRAM allocation.
nvidia-smi

# Show currently loaded model and layer split.
docker exec ollama ollama ps

# Watch live memory and CPU usage across containers.
docker stats
```

If `ollama ps` shows `100% GPU` the model fits fully. A split (e.g. `75% GPU`) indicates CPU RAM offload — expected for Qwen3.6-27B at Q3_K_M, acceptable for the quality gain.

## Guidance for model selection

- **Quick tasks:** Hermes 3 8B or Gemma 4 10B — fastest response, full GPU.
- **Coding sessions:** Qwen3.6-27B-Dense Q3_K_M — best output quality; tolerate slightly slower generation on offloaded layers.
- **Balanced:** Gemma 4 12B QAT — strong quality, fits fully on GPU.

Increase context beyond 32K only after confirming VRAM headroom with `nvidia-smi` during a realistic workload.
