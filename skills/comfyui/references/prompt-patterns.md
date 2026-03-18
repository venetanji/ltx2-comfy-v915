# Prompt Patterns and Examples

This file contains example prompts, negative prompts, and prompt templates to reuse in ComfyUI workflows.

## Example Prompts

1) Cinematic portrait
"Portrait of a young woman, cinematic lighting, soft film grain, golden hour backlight, Rembrandt lighting, ultra-detailed, photorealistic, 85mm, shallow depth of field, high dynamic range"

2) Fantasy landscape
"Vast fantasy landscape, floating islands, bioluminescent flora, neon highlights, volumetric fog, painterly, Studio Ghibli-inspired color palette, ultra wide-angle, dramatic clouds"

3) Cyberpunk street
"Rain-soaked neon street, cyberpunk city, reflective puddles, holographic signage, wide-angle, moody atmosphere, high contrast, photorealistic"

## Prompt templates

Portrait template:
"{subject}, {age}, {lighting}, {style}, {camera}, {detail}"

Landscape template:
"{scene}, {mood}, {palette}, {focal_point}, {technique}"

## Negative prompts
- "lowres, bad anatomy, deformed, extra limbs, blurry, watermark, JPEG artifacts, overexposed, underexposed"

## Notes
- Keep prompt templates short and swap tokens programmatically when doing batch runs.
- For progressive refinement, run with stronger samplers and fewer steps, then refine with high-step passes or upscalers.