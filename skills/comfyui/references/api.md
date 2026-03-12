# ComfyUI REST API Reference

Base URL: `http://localhost:8188` (env: `COMFY_URL`)
Version in use: 0.16.1 | GPU: RTX 3080 Ti (12GB VRAM) | PyTorch 2.10+cu130

---

## Workflow Submission

### POST /prompt
Submit a workflow for execution.

```json
{ "prompt": { "<node_id>": { "class_type": "NodeName", "inputs": {...} } } }
```

Response:
```json
{ "prompt_id": "uuid", "number": 22, "node_errors": {} }
```

- `node_errors`: non-empty if nodes have invalid inputs (still queues if non-fatal)
- Node links use `[source_node_id, output_index]` arrays, e.g. `"clip": ["3", 0]`
- Node IDs are arbitrary strings (ComfyUI uses integers; group nodes use `"parent:child"`)

### GET /history/{prompt_id}
Poll for results after submission.

```json
{
  "uuid": {
    "status": { "status_str": "success", "completed": true, "messages": [...] },
    "outputs": {
      "node_id": {
        "images": [{ "filename": "out_00001_.png", "subfolder": "", "type": "output" }]
      }
    }
  }
}
```

- Poll every 1-2s until `outputs` is non-empty or `status.completed == true`
- `status_str` values: `"success"`, `"error"`, `"executing"`
- Asset types in outputs: `images`, `gifs`, `audio`, `video` (list of dicts with `filename`)

### GET /history?max_items=N
Last N completed prompts.

### POST /interrupt
Cancel currently running prompt (no body needed).

---

## File Access

### GET /view?filename=F&subfolder=S&type=output
Download a generated file. Add `&_=<timestamp>` to avoid caching.

### POST /upload/image
Upload a reference image to ComfyUI's input directory.

```bash
curl -X POST \
  -F "image=@/path/to/file.jpg;filename=ref.jpg" \
  -F "type=output" \
  -F "subfolder=" \
 http://localhost:8188/upload/image
```

Response: `{ "name": "ref.jpg", "subfolder": "", "type": "input" }`

Use the returned `name` as `LoadImage.image` input value.

---

## Model Discovery

### GET /models
Returns list of model type folder names:
`checkpoints`, `loras`, `vae`, `diffusion_models`, `text_encoders`, `clip_vision`, `controlnet`, `upscale_models`, `audio_encoders`, etc.

### GET /models/{type}
Returns list of file paths for that model type.

```bash
curl http://localhost:8188/models/loras
# ["ltx-2-19b-lora-camera-control-dolly-in.safetensors", ...]
```

### GET /object_info/{NodeClass}
Full input schema for a node including all available values for enum inputs.

```bash
curl http://localhost:8188/object_info/LoraLoader
```

```json
{
  "LoraLoader": {
    "input": {
      "required": {
        "lora_name": [["file1.safetensors", "file2.safetensors"], {"tooltip": "..."}],
        "strength_model": ["FLOAT", {"default": 1.0, "min": -100.0, "max": 100.0}]
      }
    },
    "category": "loaders",
    "output": ["MODEL", "CLIP"],
    "output_name": ["MODEL", "CLIP"]
  }
}
```

### GET /object_info
All node types (1500+ nodes). Large response; prefer per-node queries.

---

## Server Status

### GET /system_stats
```json
{
  "system": { "comfyui_version": "0.16.1", "ram_free": ..., "ram_total": ... },
  "devices": [{ "name": "cuda:0 NVIDIA RTX 3080 Ti", "vram_total": 12491292672, "vram_free": ... }]
}
```

### GET /queue
```json
{ "queue_running": [[number, prompt_id, ...]], "queue_pending": [...] }
```

---

## Available Models (as of 2026-03-12)

### Diffusion models (UNETs)
- `flux-2-klein-4b-fp8.safetensors` — Flux2 Klein 4B, fast (default for image)
- `flux-2-klein-9b-fp8.safetensors` — Flux2 Klein 9B, higher quality (use for video)
- `qwen_image_2512_fp8_e4m3fn.safetensors` — Qwen image editing
- `z_image_turbo_bf16.safetensors` — fast turbo style
- `wan2.2_i2v_high_noise_14B_fp8_scaled.safetensors` — WAN 2.2 image-to-video
- `wan2.2_fun_camera_high_noise_14B_fp8_scaled.safetensors` — WAN 2.2 with camera control
- `Wan2_2-Animate-14B_fp8_scaled_e5m2_KJ_v2.safetensors` — WAN 2.2 Animate

### VAEs
- `ae.safetensors` — standard Flux1 VAE
- `flux2-vae.safetensors` — Flux2 image VAE
- `LTX2_video_vae_bf16.safetensors` — LTX2 video VAE
- `qwen-image/qwen_image_vae.safetensors` — Qwen image VAE
- `Wan2_1_VAE_bf16.safetensors` — WAN video VAE

### LoRAs (19 total)
**Camera control (LTX2 video):**
- `ltx-2-19b-lora-camera-control-dolly-in.safetensors`
- `ltx-2-19b-lora-camera-control-dolly-out.safetensors`
- `ltx-2-19b-lora-camera-control-dolly-left.safetensors`
- `ltx-2-19b-lora-camera-control-dolly-right.safetensors`
- `ltx-2-19b-lora-camera-control-jib-up.safetensors`
- `ltx-2-19b-lora-camera-control-jib-down.safetensors`
- `ltx-2-19b-lora-camera-control-static.safetensors`

**LTX2 enhancers:**
- `ltx-2-19b-distilled-lora-384.safetensors` — distilled 4-step generation
- `ltx-2-19b-ic-lora-detailer.safetensors` — detail enhancer

**Style / other:**
- `pixel_art_style_z_image_turbo.safetensors`
- `qwen-image-lightning/Qwen-Image-Lightning-{4,8}steps-*.safetensors` (4 variants)
- `WanAnimate_relight_lora_fp16.safetensors`
- `lightx2v_I2V_14B_480p_cfg_step_distill_rank64_bf16.safetensors`
- `wan2.2_i2v_lightx2v_4steps_lora_v1_{high,low}_noise.safetensors`

---

## Workflow Node Graph Structure

ComfyUI workflows are dicts where each key is a node ID:

```python
{
    "1": {
        "class_type": "UNETLoader",
        "inputs": {
            "unet_name": "flux-2-klein-4b-fp8.safetensors",
            "weight_dtype": "default"
        }
    },
    "2": {
        "class_type": "CLIPTextEncode",
        "inputs": {
            "text": "a red apple",
            "clip": ["3", 0]      # link: output 0 of node "3"
        }
    }
}
```

- **Literal inputs**: strings, ints, floats, bools
- **Link inputs**: `[source_node_id, output_index]` — both elements required
- **Node output order** matches `output_name` from `/object_info` (index 0, 1, 2...)
- Nodes with no inputs (like `RandomNoise`, `EmptyLatentImage`) still need an `"inputs": {}` key
- Multiple outputs: `VAEDecode` → output 0 is IMAGE; `LoraLoader` → output 0 is MODEL, output 1 is CLIP

## Key Node Pairs

| Source node | Output idx | → Target node input |
|---|---|---|
| UNETLoader | 0 (MODEL) | CFGGuider.model, LoraLoader.model |
| CLIPLoader | 0 (CLIP) | CLIPTextEncode.clip, LoraLoader.clip |
| LoraLoader | 0 (MODEL), 1 (CLIP) | further loaders or guider/text encoder |
| CLIPTextEncode | 0 (CONDITIONING) | CFGGuider.positive/negative, ReferenceLatent.conditioning |
| VAELoader | 0 (VAE) | VAEDecode.vae, VAEEncode.vae |
| VAEEncode | 0 (LATENT) | ReferenceLatent.latent, SamplerCustomAdvanced.latent_image |
| EmptyFlux2LatentImage | 0 (LATENT) | SamplerCustomAdvanced.latent_image |
| SamplerCustomAdvanced | 0 (LATENT) | VAEDecode.samples |
| VAEDecode | 0 (IMAGE) | SaveImage.images, SaveVideo.images |
| KSamplerSelect | 0 (SAMPLER) | SamplerCustomAdvanced.sampler |
| Flux2Scheduler | 0 (SIGMAS) | SamplerCustomAdvanced.sigmas |
| RandomNoise | 0 (NOISE) | SamplerCustomAdvanced.noise |
| CFGGuider | 0 (GUIDER) | SamplerCustomAdvanced.guider |
