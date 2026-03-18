---
name: comfyui
description: 'ComfyUI image/video/audio generation and delivery. Use for ANY request to generate, edit, or animate images or videos, or to produce speech audio. Handles the full flow: generate → download → present to user. Triggers on: "generate image", "make a video", "animate", "text to image", "comfyui", "flux", "ltx", "image from photo", "voice", "tts", "narrate", user sends a photo for editing/animation.'
---

# ComfyUI Skill

ComfyUI runs at `http://localhost:8188` (RTX 4070 Ti, 16GB VRAM).
All scripts live in `skills/comfyui/scripts/`. Run from workspace root (`/workspace`).
Output files are saved to `outputs/` (relative to CWD) — use `--output-dir outputs/` explicitly.

---

## Full Workflow: Generate → Download → Present

Every `comfy_graph.py` command automatically downloads outputs to `--output-dir` on success.
To present a file to the user, use the **absolute path** prefixed with `MEDIA:` (no backticks, no markdown):

```bash
# 1. Generate — files saved to outputs/
python skills/comfyui/scripts/comfy_graph.py t2i \
  --prompt "a red apple" --prefix apple --output-dir outputs/

# 2. File is at: outputs/apple_00001_.png
# 3. Present to user — use absolute path with MEDIA: prefix (no backticks):
#    MEDIA:C:\Users\user.V915-31\.openclaw\workspace\outputs\apple_00001_.png
#
#    ✅ MEDIA:C:\Users\user.V915-31\.openclaw\workspace\outputs\apple_00001_.png
#    ❌ outputs/apple_00001_.png  (relative path — does NOT work)
#    ❌ `MEDIA:...`               (backticks — breaks media delivery)
```

---

## Images (Flux2 Klein 4B, ~30s)

```bash
python skills/comfyui/scripts/comfy_graph.py t2i --prompt "a red apple" --output-dir outputs/
python skills/comfyui/scripts/comfy_graph.py i2i --image ref.jpg --prompt "in winter" --output-dir outputs/
python skills/comfyui/scripts/comfy_graph.py i2i2 --image1 char.jpg --image2 bg.jpg --prompt "character in scene" --output-dir outputs/
python skills/comfyui/scripts/comfy_graph.py angles --image char.jpg --prompts "front\nside\n3/4" --output-dir outputs/
```

## Video (LTX2, ~3-8min)

```bash
python skills/comfyui/scripts/comfy_graph.py t2v --prompt "wave crashing on rocks" --seconds 3 --output-dir outputs/
python skills/comfyui/scripts/comfy_graph.py i2v --image frame.jpg --prompt "..." --camera dolly-in --seconds 3 --output-dir outputs/
# camera: dolly-in dolly-out dolly-left dolly-right jib-up jib-down static

# Multiframe: guide frames at specific indices (idx=-1 = last frame)
python skills/comfyui/scripts/comfy_graph.py mf \
  --frames "first.jpg:0,last.jpg:-1" --prompt "..." --seconds 3 --output-dir outputs/

# Second pass: upscale 2× + refine (add --second-pass, set --seed to reproduce pass 1)
python skills/comfyui/scripts/comfy_graph.py i2v --image frame.jpg --prompt "..." --seed 12345 --second-pass --output-dir outputs/
```

## Audio in Video

```bash
# Default: LTX2 generates ambient audio automatically
python skills/comfyui/scripts/comfy_graph.py t2v --prompt "..." --output-dir outputs/

# With speech (two-step — avoids VRAM conflict on 12GB):
python skills/comfyui/scripts/comfy_graph.py tts \
  --text "The sun sets." --prefix narration --output-dir outputs/
AUDIO=$(python skills/comfyui/scripts/comfy_graph.py upload outputs/narration_00001_.mp3)
python skills/comfyui/scripts/comfy_graph.py t2v \
  --prompt "sunset" --audio-file "$AUDIO" --output-dir outputs/

# No audio track:
python skills/comfyui/scripts/comfy_graph.py t2v --prompt "..." --no-audio --output-dir outputs/
```

## Audio (standalone)

```bash
python skills/comfyui/scripts/comfy_graph.py tts --text "Hello" --voice "warm female voice" --output-dir outputs/
python skills/comfyui/scripts/comfy_graph.py clone --text "Hello" --voice-name gio --output-dir outputs/
# voice-name: gio (Giovanni's cloned voice, requires voice.mp3 in ComfyUI input dir)
```

## Upload a Reference Image

When a user sends an image via WhatsApp, Openclaw saves it to `media/inbound/`. Upload it first:

```bash
# Upload to ComfyUI input dir, prints server filename
NAME=$(python skills/comfyui/scripts/comfy_graph.py upload media/inbound/photo.jpg)
python skills/comfyui/scripts/comfy_graph.py i2i --image "$NAME" --prompt "in winter" --output-dir outputs/
python skills/comfyui/scripts/comfy_graph.py i2v --image "$NAME" --prompt "..." --seconds 3 --output-dir outputs/
```

## Video Chaining (longer videos via last-frame extraction)

```bash
# Extract last frame of a video (server-side path)
python skills/comfyui/scripts/comfy_graph.py last_frame \
  --video /app/ComfyUI/output/segment1_00001_.mp4 --prefix seg1_last --output-dir outputs/
# Upload the extracted frame as input for next segment
FRAME=$(python skills/comfyui/scripts/comfy_graph.py upload outputs/seg1_last_00001_.png)
python skills/comfyui/scripts/comfy_graph.py i2v --image "$FRAME" --prompt "continues walking..." --output-dir outputs/
```

---

## Model Management

Check and download missing models from any workflow JSON (reads embedded `models` metadata in loader nodes):

```bash
# Check what's missing (no download)
python skills/comfyui/scripts/comfy_models.py check --url https://pastebin.com/raw/XYZ
python skills/comfyui/scripts/comfy_models.py check --workflow path/to/flow.json

# List all models (present + missing)
python skills/comfyui/scripts/comfy_models.py list --url https://pastebin.com/raw/XYZ

# Download all missing models
python skills/comfyui/scripts/comfy_models.py download --url https://pastebin.com/raw/XYZ

# Download a single model manually
python skills/comfyui/scripts/comfy_models.py get \
  --url https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-dev.safetensors \
  --dir checkpoints
```

Models are saved to `~/Documents/comfyui-git/models/<directory>/`. Set `COMFYUI_MODELS_DIR` to override.
Set `HF_TOKEN` env var for gated HuggingFace models.

Always run `check` before starting a new workflow — missing models cause silent failures.

---

## Query / Debug

```bash
python skills/comfyui/scripts/comfy_query.py stats        # GPU/RAM/VRAM status
python skills/comfyui/scripts/comfy_query.py loras        # list LoRAs
python skills/comfyui/scripts/comfy_query.py models diffusion_models
python skills/comfyui/scripts/comfy_query.py queue
python skills/comfyui/scripts/comfy_query.py history [<prompt_id>]
python skills/comfyui/scripts/comfy_graph.py dump t2v --prompt "test"  # print JSON without submitting
```

---

## WorkflowGraph Library

```python
import sys; sys.path.insert(0, "skills/comfyui/scripts")
from comfy_graph import WorkflowGraph, flux2_text_to_image, ltx2_text_to_video, upload_image

# Upload inbound image then generate
server_name = upload_image("media/inbound/photo.jpg")
wf = flux2_text_to_image(prompt="in winter", width=1024, height=576)
```

Available builders: `flux2_text_to_image`, `flux2_single_image_edit`, `flux2_double_image_edit`,
`flux2_multiple_angles`, `ltx2_text_to_video`, `ltx2_image_to_video`, `ltx2_multiframe`,
`extract_last_frame`, `qwen_tts`, `qwen_voice_clone`, `upload_image`.

---

## Notes

- Output pattern: `<prefix>_00001_.png` / `.mp4` / `.mp3`
- Always use **absolute paths with `MEDIA:` prefix** (no backticks) when presenting files to user, e.g. `MEDIA:C:\Users\user.V915-31\.openclaw\workspace\outputs\file_00001_.png` — but send it without backticks in the actual reply
- VRAM limit: avoid submitting multiple workflows simultaneously — ComfyUI queues them but VRAM may not clear between runs
- Inline `--speech-text` OOMs on 12GB when LTX2 is cached; always use the two-step `tts` → `upload` → `--audio-file` pattern
- For video with LoRAs: always apply `ltx-2-19b-distilled-lora-384` first (strength -0.4), then camera LoRA
- API reference: `skills/comfyui/references/api.md`
