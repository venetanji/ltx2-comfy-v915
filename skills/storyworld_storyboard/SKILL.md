---
name: storyworld_storyboard
description: "Generate production-ready storyboards and shot lists for PolyU Storyworld LTX-2.3 video workflows. Use when: creating a multi-shot scene for characters, planning a video sequence, generating per-shot i2v prompts from a narrative. Integrates with storyworld MCP for character context and reference images."
---

# storyworld_storyboard

Turns a narrative concept into a shot-ready package: timed shot list, LTX-2.3 prompts, character selections, reference images, and optional per-shot ComfyUI workflow drafts.

## Storyworld Resources
- Characters: `https://github.com/venetanji/polyu-storyworld` (YAML per character)
- Reference images: `https://huggingface.co/datasets/venetanji/polyu-storyworld-characters`
- MCP server: `https://polyu-storyworld.tail9683c.ts.net/mcp`

## Step 1 — Get Character Context (via mcporter)

```bash
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.get_character_context" code=6166r --output json
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.prepare_reference_image" code=6166r --output json
# → returns {"filename": "6166r_ref.png", "url": "https://polyu-storyworld.tail9683c.ts.net/outputs/6166r_ref.png"}
```

Always call `get_character_context` before `prepare_reference_image`.

## Step 2 — Generate Storyboard

```bash
python skills/storyworld_storyboard/scripts/generate_storyboard.py \
  --hf-dataset "https://huggingface.co/datasets/venetanji/polyu-storyworld-characters" \
  --repo "https://github.com/venetanji/polyu-storyworld" \
  --mcp "https://polyu-storyworld.tail9683c.ts.net/mcp" \
  --characters "6166r" \
  --duration 30 --shots 5 --seed 1234 \
  --out outputs/storyboard_athena
```

Output: `storyboard.json` + `storyboard.txt` in `--out` directory.

## Step 3 — Render Shots (LTX2.3 i2v)

For each shot in `storyboard.json`:

```bash
# Upload reference image for the shot
NAME=$(python skills/comfyui/scripts/comfy_graph.py upload outputs/storyboard_athena/refs/6166r_ref.png)

# Render shot (LTX2.3 default)
python skills/comfyui/scripts/comfy_graph.py i2v \
  --image "$NAME" \
  --prompt "SHOT_PROMPT_FROM_JSON" \
  --seconds 7 \
  --prefix "athena_shot_01" \
  --output-dir outputs/
# Output: MEDIA:C:\Users\user.V915-31\Documents\ltx2-comfy-v915\outputs\athena_shot_01_00001_.mp4
```

For chaining shots (last frame → next shot input):
```bash
python skills/comfyui/scripts/comfy_graph.py last_frame \
  --video "C:\Users\user.V915-31\Documents\ComfyUI\output\athena_shot_01_00001_.mp4" \
  --prefix athena_s1_last --output-dir outputs/
NAME=$(python skills/comfyui/scripts/comfy_graph.py upload outputs/athena_s1_last_00001_.png)
python skills/comfyui/scripts/comfy_graph.py i2v --image "$NAME" --prompt "..." --prefix athena_shot_02 --output-dir outputs/
```

## Prompt Writing Guidelines (LTX-2.3)

Write as a **single flowing paragraph** — no lists, no line breaks.

- **Present tense, cinematic verbs**: "A young woman walks across the rain-slick street..."
- **Explicit camera + framing**: "3/4 medium shot, 50mm, dolly forward to close-up"
- **Lighting + atmosphere**: "golden hour rim light from the left, soft fill, light fog"
- **Audio cues**: "muffled city traffic, distant thunder, slow piano motif building"
- **Character actions**: "she glances down, hesitant, fingers tracing a locket"
- **Style reference**: "in the photographic style of the provided ref image, soft film grain"

Example:
> Athena, goddess of wisdom, stands at the threshold of a vast ancient Greek temple at golden hour. Her silver armor catches the warm light as an owl lands on her outstretched arm. The camera slowly pulls back on a crane shot revealing towering marble columns, olive trees swaying in the distance. Audio: distant thunder rolling across clear skies, wind through olive leaves, a low resonant choir building slowly.

## Shot Duration Guidance
- Quick actions: 2–4s
- Traveling / dialogue: 5–7s  
- Establishing / emotional: 7–10s

## Shot JSON Schema
Each shot in `storyboard.json`:
```json
{
  "shot_index": 0,
  "duration": 7.0,
  "prompt": "...",
  "camera_move": "slow crane up",
  "characters": ["6166r"],
  "ref_images": ["outputs/storyboard_athena/refs/6166r_ref.png"],
  "transition_hint": "crossfade to wide establishing",
  "seed": 1234
}
```

## Notes
- LTX2.3 has no camera LoRA support — describe camera movement in the prompt
- Render one shot at a time to avoid VRAM conflicts
- After rendering, assemble shots in DaVinci Resolve / Premiere using `transition_hint`
- Save outputs with meaningful prefixes: `<project>_shot_<NN>`
