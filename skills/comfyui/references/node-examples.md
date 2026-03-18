# Node Graph Examples

Annotated examples for common ComfyUI workflows. Use these as building blocks or paste into your node graph editor.

## Text-to-Image (minimal)
- TextPrompt -> CLIPTextEncode -> CLIPCondition -> CheckpointLoader -> Sampler (DDIM/PLMS/K-LMS) -> VaeDecode -> SaveImage

## Image-to-Image (guided denoise)
- LoadImage -> Resize -> ImageToLatent -> NoiseSchedule -> Sampler (with strength control) -> VaeDecode -> SaveImage

## Inpainting (masked)
- LoadImage, LoadMask -> AlignMask -> ImageToLatent -> InpaintScheduler -> Sampler -> VaeDecode -> Composite -> SaveImage

## ControlNet (pose/example)
- ControlNetInput (pose) -> ControlNetNode (weight) -> ConditionMerge -> Sampler -> VaeDecode -> SaveImage

## Tips and common subgraphs
- Seed Scheduler: a small subgraph that produces deterministic seeds per batch using a base seed + offset.
- Prompt Embedding Cache: precompute CLIP embeddings for long prompts and reuse them across batches.
- Upscale + Denoise: run an initial pass at base resolution, then upscale with an ESRGAN/Real-ESRGAN node and run a light denoise/restore pass.

## Exporting
- Save node graph as JSON and include a README with the prompt, seed, checkpoint, LoRA weights, ControlNet models, and scheduler settings.


