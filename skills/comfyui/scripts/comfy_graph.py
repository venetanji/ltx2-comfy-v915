#!/usr/bin/env python3
"""
comfy_graph.py — WorkflowGraph: programmatic ComfyUI workflow builder.

Library usage:
    from comfy_graph import WorkflowGraph, flux2_text_to_image, ltx2_image_to_video

CLI usage:
    # Images (Flux2 Klein)
    python comfy_graph.py t2i --prompt "..." [--width 1024] [--height 576] [--lora <name>]
    python comfy_graph.py i2i --image ref.jpg --prompt "..." [--width 1024] [--height 576]
    python comfy_graph.py i2i2 --image1 a.jpg --image2 b.jpg --prompt "..."
    python comfy_graph.py angles --image char.jpg --prompts "front view\nside view\n3/4 view"

    # Video (LTX2 GGUF distilled, with audio)
    python comfy_graph.py t2v --prompt "..." [--seconds 3] [--camera dolly-in] [--second-pass]
    python comfy_graph.py i2v --image frame.jpg --prompt "..." [--seconds 3] [--camera dolly-in] [--second-pass]
    python comfy_graph.py mf --frames "img1.jpg:0,img2.jpg:48,img3.jpg:-1" --prompt "..." [--seconds 3]

    # Audio
    python comfy_graph.py tts --text "Hello" [--voice "warm female voice"] [--lang Auto]
    python comfy_graph.py clone --text "Hello" --voice-name gio [--lang Auto]

    # Dump JSON without submitting
    python comfy_graph.py dump t2i --prompt "test"

Camera LoRAs: dolly-in dolly-out dolly-left dolly-right jib-up jib-down static
Voices: gio (Giovanni, reference: voice.mp3 in ComfyUI input dir)

Env: COMFY_URL (default: http://localhost:8188)
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE = os.environ.get("COMFY_URL", "http://localhost:8188").rstrip("/")

# Known voice profiles: name → reference audio filename in ComfyUI input dir
# reference_text: transcript of the audio (required unless x_vector_only=True)
# x_vector_only: True = skip text alignment (faster, lower quality cloning)
VOICE_LIBRARY = {
    "gio": {"file": "voice.mp3", "reference_text": "", "x_vector_only": True},
}

# ---------------------------------------------------------------------------
# Core graph types
# ---------------------------------------------------------------------------

class NodeRef:
    """Reference to a node output. Serializes to [node_id, output_index]."""
    def __init__(self, node_id: str, output_idx: int = 0):
        self.node_id = node_id
        self.output_idx = output_idx

    def __getitem__(self, idx: int) -> "NodeRef":
        return NodeRef(self.node_id, idx)

    def as_link(self) -> list:
        return [self.node_id, self.output_idx]

    def __repr__(self):
        return f"NodeRef({self.node_id!r}, {self.output_idx})"


class WorkflowGraph:
    """Builds a ComfyUI workflow dict by adding nodes with wired inputs."""
    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._counter = 0

    def node(self, class_type: str, **inputs) -> NodeRef:
        """Add a node and return a NodeRef to its first output."""
        node_id = str(self._counter)
        self._counter += 1
        processed = {}
        for k, v in inputs.items():
            if isinstance(v, NodeRef):
                processed[k] = v.as_link()
            else:
                processed[k] = v
        self._nodes[node_id] = {"class_type": class_type, "inputs": processed}
        return NodeRef(node_id)

    def to_dict(self) -> dict:
        return dict(self._nodes)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


# ---------------------------------------------------------------------------
# Flux2 fragments
# ---------------------------------------------------------------------------

def _flux2_backbone(g, unet_name="flux-2-klein-4b-fp8.safetensors",
                    vae_name="flux2-vae.safetensors", clip_name="qwen_3_4b.safetensors"):
    unet = g.node("UNETLoader", unet_name=unet_name, weight_dtype="default")
    vae  = g.node("VAELoader", vae_name=vae_name)
    clip = g.node("CLIPLoader", clip_name=clip_name, type="flux2", device="default")
    return unet, vae, clip

def _flux2_lora(g, unet, clip, lora_name, strength=1.0):
    lora = g.node("LoraLoader", model=unet[0], clip=clip[0],
                  lora_name=lora_name, strength_model=strength, strength_clip=strength)
    return lora[0], lora[1]

def _flux2_conditioning(g, clip, prompt):
    pos = g.node("CLIPTextEncode", text=prompt, clip=clip)
    neg = g.node("ConditioningZeroOut", conditioning=pos[0])
    return pos, neg

def _flux2_sample(g, unet, positive, negative, latent, steps=4, width=1024, height=576, seed=None):
    if seed is None:
        seed = int(time.time() * 1000) % (2**32)
    sampler  = g.node("KSamplerSelect", sampler_name="euler")
    schedule = g.node("Flux2Scheduler", steps=steps, width=width, height=height)
    noise    = g.node("RandomNoise", noise_seed=seed)
    guider   = g.node("CFGGuider", model=unet[0], positive=positive[0], negative=negative[0], cfg=1.0)
    return g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0],
                  sampler=sampler[0], sigmas=schedule[0], latent_image=latent[0])


# ---------------------------------------------------------------------------
# LTX2 fragments
# ---------------------------------------------------------------------------

def _ltx2_loaders(g):
    """Load GGUF UNET + dual CLIP + video VAE + audio VAE.
    Returns (model, clip, video_vae, audio_vae)."""
    unet  = g.node("UnetLoaderGGUF", unet_name="ltx-2-19b-distilled_Q4_K_M.gguf")
    model = g.node("LTXVChunkFeedForward", model=unet[0], chunks=4, dim_threshold=4096)
    clip  = g.node("DualCLIPLoader",
                   clip_name1="gemma_3_12B_it_fp8_e4m3fn.safetensors",
                   clip_name2="ltx-2-19b-embeddings_connector_distill_bf16.safetensors",
                   type="ltxv", device="default")
    video_vae = g.node("VAELoaderKJ", vae_name="LTX2_video_vae_bf16.safetensors",
                       device="main_device", weight_dtype="bf16")
    audio_vae = g.node("VAELoaderKJ", vae_name="LTX2_audio_vae_bf16.safetensors",
                       device="main_device", weight_dtype="bf16")
    return model, clip, video_vae, audio_vae

def _ltx2_apply_loras(g, model, loras: list[tuple[str, float]]):
    """Apply LoRAs via LoraLoaderModelOnly. loras: [(name, strength), ...]"""
    for name, strength in loras:
        model = g.node("LoraLoaderModelOnly", model=model[0], lora_name=name, strength_model=strength)
    return model

def _ltx2_condition(g, clip, positive_text, fps=24):
    """Encode prompt + apply LTXVConditioning.
    Returns cond NodeRef: cond[0]=positive, cond[1]=negative."""
    pos = g.node("CLIPTextEncode", text=positive_text, clip=clip)
    neg = g.node("CLIPTextEncode",
                 text="blurry, low quality, watermark, distorted, still frame",
                 clip=clip)
    return g.node("LTXVConditioning", positive=pos[0], negative=neg[0], frame_rate=float(fps))

def _ltx2_audio_latent(g, audio_vae, length, fps=24, audio_ref=None):
    """Return audio LATENT.
    audio_ref=None  → LTX-generated ambient audio (model denoises from empty latent).
    audio_ref=NodeRef(AUDIO) → encode provided audio (e.g. TTS output)."""
    if audio_ref is not None:
        return g.node("LTXVAudioVAEEncode", audio=audio_ref, audio_vae=audio_vae[0])
    return g.node("LTXVEmptyLatentAudio",
                  frames_number=int(length), frame_rate=int(fps),
                  audio_vae=audio_vae[0], batch_size=1)

def _ltx2_sample(g, model, cond, latent, steps=8, seed=None):
    """Single-pass sampling. latent may be video-only or AV."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**32)
    sampler  = g.node("KSamplerSelect", sampler_name="euler_ancestral")
    schedule = g.node("LTXVScheduler", steps=steps, max_shift=2.05, base_shift=0.95,
                      stretch=True, terminal=0.1, latent=latent)
    noise    = g.node("RandomNoise", noise_seed=seed)
    guider   = g.node("CFGGuider", model=model[0], positive=cond[0], negative=cond[1], cfg=1.0)
    return g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0],
                  sampler=sampler[0], sigmas=schedule[0], latent_image=latent)

def _ltx2_decode(g, latent_out, video_vae, audio_vae=None):
    """Decode video (and optionally audio).
    audio_vae=None → video-only decode (no audio track).
    Returns (images, audio_or_None, audio_latent_or_None)."""
    if audio_vae is not None:
        sep    = g.node("LTXVSeparateAVLatent", av_latent=latent_out)
        images = g.node("LTXVSpatioTemporalTiledVAEDecode", vae=video_vae[0], latents=sep[0],
                        spatial_tiles=4, spatial_overlap=1,
                        temporal_tile_length=16, temporal_overlap=1,
                        last_frame_fix=False, working_device="auto", working_dtype="auto")
        audio  = g.node("LTXVAudioVAEDecode", samples=sep[1], audio_vae=audio_vae[0])
        return images, audio, sep[1]
    else:
        images = g.node("LTXVSpatioTemporalTiledVAEDecode", vae=video_vae[0], latents=latent_out,
                        spatial_tiles=4, spatial_overlap=1,
                        temporal_tile_length=16, temporal_overlap=1,
                        last_frame_fix=False, working_device="auto", working_dtype="auto")
        return images, None, None

def _ltx2_second_pass(g, model, cond, images, audio_latent,
                       video_vae, audio_vae, width, height, length, seed=None):
    """Second pass: upscale 2×, re-encode, refine with low-noise sigmas.
    audio_latent=None → video-only (no audio).
    Returns (images_hires, audio_or_None)."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**32)
    # upscale the decoded image (pixel-space) first
    upscaled     = g.node("ImageScale", image=images[0], upscale_method="lanczos",
                          width=width * 2, height=height * 2, crop="disabled")
    # create a hires latent buffer and inject the upscaled image
    hires_latent = g.node("EmptyLTXVLatentVideo",
                          width=width * 2, height=height * 2, length=length, batch_size=1)
    video_lat_2  = g.node("LTXVImgToVideoInplace", vae=video_vae[0], image=upscaled[0],
                           latent=hires_latent[0], strength=1.0, bypass=False)

    # Use a learned latent upscaler (preferred) when available
    # The workflow's LatentUpscaleModelLoader typically provides the model filename
    # We attempt to load the common spatial upscaler name; if missing the loader will be ignored.
    upscaler_loader = g.node("LatentUpscaleModelLoader", model_name="ltx-2.3-spatial-upscaler-x2-1.0.safetensors")
    # LTXVLatentUpsampler expects: samples, vae, upscale_model
    try_up = g.node("LTXVLatentUpsampler", samples=video_lat_2[0], vae=video_vae[0], upscale_model=upscaler_loader[0])

    # If audio exists, concatenate AV latent, using the upsampled video latent
    if audio_latent is not None:
        latent_2 = g.node("LTXVConcatAVLatent",
                           video_latent=try_up[0], audio_latent=audio_latent)
    else:
        latent_2 = try_up
    sampler  = g.node("KSamplerSelect", sampler_name="euler_ancestral")
    sigmas   = g.node("ManualSigmas", sigmas="0.909375, 0.725, 0.421875, 0.0")
    noise    = g.node("RandomNoise", noise_seed=seed)
    guider   = g.node("CFGGuider", model=model[0], positive=cond[0], negative=cond[1], cfg=1.0)
    out_2    = g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0],
                      sampler=sampler[0], sigmas=sigmas[0], latent_image=latent_2)
    images_out, audio_out, _ = _ltx2_decode(g, out_2, video_vae,
                                             audio_vae if audio_latent is not None else None)
    return images_out, audio_out

def _ltx2_save(g, images, fps, filename_prefix, audio=None, raw_audio=None):
    """Save video. audio=decoded AUDIO NodeRef, raw_audio=LoadAudio NodeRef, both optional."""
    track = audio or raw_audio
    if track is not None:
        video = g.node("CreateVideo", images=images[0], fps=float(fps), audio=track[0])
    else:
        video = g.node("CreateVideo", images=images[0], fps=float(fps))
    g.node("SaveVideo", video=video[0], filename_prefix=filename_prefix,
           format="auto", codec="auto")

def _ltx2_default_loras(camera_lora=None):
    """Build default LoRA list: distilled (-0.4) + optional camera (+1.0)."""
    loras = [("ltx-2-19b-distilled-lora-384.safetensors", -0.4)]
    if camera_lora:
        loras.append((f"ltx-2-19b-lora-camera-control-{camera_lora}.safetensors", 1.0))
    return loras


# ---------------------------------------------------------------------------
# Voice fragments
# ---------------------------------------------------------------------------

def _qwen_tts_design(g, text, voice_instruct="A clear, friendly voice.", language="Auto"):
    """Qwen3-TTS with voice style description. Returns AUDIO NodeRef."""
    return g.node("AILab_Qwen3TTSVoiceDesign", text=text, instruct=voice_instruct,
                  model_size="1.7B", language=language, unload_models=True, seed=-1)

def _qwen_voice_clone_audio(g, text, voice_name="gio", language="Auto"):
    """Load reference audio, create VOICE, clone it. Returns AUDIO NodeRef."""
    voice_info = VOICE_LIBRARY.get(voice_name)
    if voice_info is None:
        raise ValueError(f"Unknown voice '{voice_name}'. Available: {list(VOICE_LIBRARY)}")
    ref_audio = g.node("VHS_LoadAudioUpload", audio=voice_info["file"])
    x_vector_only = voice_info.get("x_vector_only", not bool(voice_info.get("reference_text")))
    voice     = g.node("AILab_Qwen3TTSVoicesLibrary",
                       reference_audio=ref_audio[0],
                       reference_text=voice_info.get("reference_text", ""),
                       model_size="1.7B", device="auto", precision="bf16",
                       x_vector_only=x_vector_only, voice_name=voice_name,
                       unload_models=True)
    return g.node("AILab_Qwen3TTSVoiceClone", target_text=text, model_size="1.7B",
                  language=language, voice=voice[0], unload_models=True, seed=-1)


# ---------------------------------------------------------------------------
# Complete workflow builders
# ---------------------------------------------------------------------------

def flux2_text_to_image(prompt, width=1024, height=576, steps=4,
                         filename_prefix="flux2_t2i", lora=None, lora_strength=1.0, seed=None):
    """Flux2 text-to-image."""
    g = WorkflowGraph()
    unet, vae, clip = _flux2_backbone(g)
    if lora:
        unet, clip = _flux2_lora(g, unet, clip, lora, lora_strength)
    pos, neg = _flux2_conditioning(g, clip, prompt)
    latent   = g.node("EmptyFlux2LatentImage", width=width, height=height, batch_size=1)
    samples  = _flux2_sample(g, unet, pos, neg, latent, steps=steps, width=width, height=height, seed=seed)
    decoded  = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


def flux2_single_image_edit(image_filename, prompt, width=1024, height=576, steps=4,
                              filename_prefix="flux2_i2i", seed=None):
    """Flux2 single-image edit via reference latent conditioning."""
    g = WorkflowGraph()
    unet, vae, clip = _flux2_backbone(g)
    pos_text  = g.node("CLIPTextEncode", text=prompt, clip=clip)
    neg_text  = g.node("CLIPTextEncode", text="", clip=clip)
    ref       = g.node("LoadImage", image=image_filename)
    scaled    = g.node("ImageScaleToTotalPixels", image=ref[0],
                       upscale_method="nearest-exact", megapixels=1, resolution_steps=1)
    enc_ref   = g.node("VAEEncode", pixels=scaled[0], vae=vae[0])
    pos       = g.node("ReferenceLatent", conditioning=pos_text[0], latent=enc_ref[0])
    neg       = g.node("ReferenceLatent", conditioning=neg_text[0], latent=enc_ref[0])
    w_node    = g.node("PrimitiveInt", value=width)
    h_node    = g.node("PrimitiveInt", value=height)
    latent    = g.node("EmptyFlux2LatentImage", width=w_node[0], height=h_node[0], batch_size=1)
    samples   = _flux2_sample(g, unet, pos, neg, latent, steps=steps, width=width, height=height, seed=seed)
    decoded   = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


def flux2_double_image_edit(image1_filename, image2_filename, prompt,
                              width=1024, height=576, steps=4,
                              filename_prefix="flux2_i2i2", seed=None):
    """Flux2 two-reference-image edit."""
    g = WorkflowGraph()
    unet, vae, clip = _flux2_backbone(g)
    pos_text = g.node("CLIPTextEncode", text=prompt, clip=clip)
    neg_text = g.node("CLIPTextEncode", text="", clip=clip)

    def _enc(fname):
        ref    = g.node("LoadImage", image=fname)
        scaled = g.node("ImageScaleToTotalPixels", image=ref[0],
                        upscale_method="nearest-exact", megapixels=1, resolution_steps=1)
        return g.node("VAEEncode", pixels=scaled[0], vae=vae[0])

    merged = g.node("LatentBatch", samples1=_enc(image1_filename)[0], samples2=_enc(image2_filename)[0])
    pos    = g.node("ReferenceLatent", conditioning=pos_text[0], latent=merged[0])
    neg    = g.node("ReferenceLatent", conditioning=neg_text[0], latent=merged[0])
    w_node = g.node("PrimitiveInt", value=width)
    h_node = g.node("PrimitiveInt", value=height)
    latent  = g.node("EmptyFlux2LatentImage", width=w_node[0], height=h_node[0], batch_size=1)
    samples = _flux2_sample(g, unet, pos, neg, latent, steps=steps, width=width, height=height, seed=seed)
    decoded = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


def flux2_multiple_angles(image_filename, angle_prompts: list[str],
                           filename_prefix="flux2_angles"):
    """Generate multiple angles of a character/subject via SimplePromptBatcher.
    angle_prompts: list of angle descriptions (e.g. ['front view', 'side view']).
    Generates one image per prompt in a batch."""
    g = WorkflowGraph()
    unet, vae, clip = _flux2_backbone(g)
    # SimplePromptBatcher now requires prepend + prompts + append
    batcher = g.node("SimplePromptBatcher",
                     prepend="",
                     prompts="\n".join(angle_prompts) + "\n",
                     append="")
    pos_text  = g.node("CLIPTextEncode", text=batcher[0], clip=clip)
    neg_text  = g.node("ConditioningZeroOut", conditioning=pos_text[0])
    ref       = g.node("LoadImage", image=image_filename)
    scaled    = g.node("ImageScaleToTotalPixels", image=ref[0],
                       upscale_method="lanczos", megapixels=1, resolution_steps=1)
    size      = g.node("GetImageSize", image=scaled[0])
    enc_ref   = g.node("VAEEncode", pixels=scaled[0], vae=vae[0])
    pos       = g.node("ReferenceLatent", conditioning=pos_text[0], latent=enc_ref[0])
    neg       = g.node("ReferenceLatent", conditioning=neg_text[0], latent=enc_ref[0])
    latent    = g.node("EmptyFlux2LatentImage", width=size[0], height=size[1], batch_size=1)
    scheduler = g.node("Flux2Scheduler", steps=4, width=size[0], height=size[1])
    sampler   = g.node("KSamplerSelect", sampler_name="euler")
    noise     = g.node("RandomNoise", noise_seed=int(time.time() * 1000) % (2**32))
    guider    = g.node("CFGGuider", model=unet[0], positive=pos[0], negative=neg[0], cfg=1.0)
    samples   = g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0],
                       sampler=sampler[0], sigmas=scheduler[0], latent_image=latent[0])
    decoded   = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


def _ltx2_resolve_audio(g, audio_vae, length, fps, audio_ref, speech_text, speech_voice, speech_voice_name, include_audio, audio_file=None):
    """Resolve audio setup for LTX2 builders.
    Returns (audio_latent, active_audio_vae, raw_audio_node):
      - audio_file (str filename): raw_audio set, audio_latent=None — audio is attached directly
        to CreateVideo, bypassing the LTX2 latent pipeline so speech is preserved unchanged.
      - audio_ref (NodeRef AUDIO): goes through LTX2 audio latent pipeline (encode → sample → decode).
      - speech_text: inline TTS — OOMs on 12GB if LTX2 is cached; prefer two-step with audio_file.
      - include_audio=True with no inputs: LTX2 generates ambient audio via empty latent.
      - include_audio=False: no audio at all."""
    if not include_audio:
        return None, None, None
    # Pre-existing audio file: load and attach directly to CreateVideo (preserves audio as-is)
    if audio_file:
        raw_audio = g.node("LoadAudio", audio=audio_file)
        return None, None, raw_audio
    # Inline speech (same-workflow TTS — only works if LTX2 not already cached in VRAM)
    if speech_text and audio_ref is None:
        if speech_voice_name:
            audio_ref = _qwen_voice_clone_audio(g, speech_text, speech_voice_name)
        else:
            audio_ref = _qwen_tts_design(g, speech_text, speech_voice)
    audio_latent = _ltx2_audio_latent(g, audio_vae, length, fps=fps, audio_ref=audio_ref)
    return audio_latent, audio_vae, None


def ltx2_text_to_video(prompt, seconds=3, fps=24, camera_lora=None,
                        filename_prefix="ltx2_t2v", second_pass=False, seed=None,
                        audio_ref=None, audio_file=None, speech_text=None,
                        speech_voice="Clear, neutral voice", speech_voice_name=None,
                        include_audio=True):
    """LTX2 text-to-video.
    include_audio=True (default): LTX generates ambient audio.
    audio_file: filename of pre-generated audio in ComfyUI input dir (recommended for speech).
    speech_text: inline TTS — only works if LTX2 not already cached in VRAM (12GB limit).
    audio_ref: pre-built AUDIO NodeRef (advanced).
    include_audio=False: video only, no audio track."""
    g = WorkflowGraph()
    length = seconds * fps + 1
    width, height = 768, 512

    model, clip, video_vae, audio_vae = _ltx2_loaders(g)
    model = _ltx2_apply_loras(g, model, _ltx2_default_loras(camera_lora))
    cond  = _ltx2_condition(g, clip, prompt, fps=fps)

    video_latent = g.node("EmptyLTXVLatentVideo", width=width, height=height,
                          length=length, batch_size=1)
    audio_latent, active_audio_vae, raw_audio = _ltx2_resolve_audio(
        g, audio_vae, length, fps, audio_ref, speech_text, speech_voice, speech_voice_name, include_audio, audio_file=audio_file)
    if audio_latent is not None:
        latent = g.node("LTXVConcatAVLatent", video_latent=video_latent[0],
                        audio_latent=audio_latent)
    else:
        latent = video_latent

    av_out = _ltx2_sample(g, model, cond, latent, steps=8, seed=seed)

    if second_pass:
        images, audio, audio_lat = _ltx2_decode(g, av_out, video_vae, active_audio_vae)
        images, audio = _ltx2_second_pass(g, model, cond, images, audio_lat,
                                           video_vae, active_audio_vae, width, height, length, seed=seed)
    else:
        images, audio, _ = _ltx2_decode(g, av_out, video_vae, active_audio_vae)

    _ltx2_save(g, images, fps, filename_prefix, audio=audio, raw_audio=raw_audio)
    return g.to_dict()


def ltx2_image_to_video(image_filename, prompt, seconds=3, fps=24, camera_lora=None,
                         filename_prefix="ltx2_i2v", second_pass=False, seed=None,
                         audio_ref=None, audio_file=None, speech_text=None,
                         speech_voice="Clear, neutral voice", speech_voice_name=None,
                         include_audio=True):
    """LTX2 image-to-video. First frame baked via LTXVImgToVideoInplace.
    include_audio=True (default): LTX generates ambient audio.
    audio_file: filename of pre-generated audio in ComfyUI input dir (recommended for speech)."""
    g = WorkflowGraph()
    length = seconds * fps + 1
    width, height = 768, 512

    model, clip, video_vae, audio_vae = _ltx2_loaders(g)
    model = _ltx2_apply_loras(g, model, _ltx2_default_loras(camera_lora))
    cond  = _ltx2_condition(g, clip, prompt, fps=fps)

    frame   = g.node("LoadImage", image=image_filename)
    resized = g.node("ResizeImagesByLongerEdge", images=frame[0], longer_edge=1536)
    prep    = g.node("LTXVPreprocess", image=resized[0], img_compression=35)

    base_latent  = g.node("EmptyLTXVLatentVideo", width=width, height=height,
                          length=length, batch_size=1)
    video_latent = g.node("LTXVImgToVideoInplace", vae=video_vae[0], image=prep[0],
                          latent=base_latent[0], strength=1.0, bypass=False)

    audio_latent, active_audio_vae, raw_audio = _ltx2_resolve_audio(
        g, audio_vae, length, fps, audio_ref, speech_text, speech_voice, speech_voice_name, include_audio, audio_file=audio_file)
    if audio_latent is not None:
        latent = g.node("LTXVConcatAVLatent", video_latent=video_latent[0],
                        audio_latent=audio_latent)
    else:
        latent = video_latent

    av_out = _ltx2_sample(g, model, cond, latent, steps=8, seed=seed)

    if second_pass:
        images, audio, audio_lat = _ltx2_decode(g, av_out, video_vae, active_audio_vae)
        images, audio = _ltx2_second_pass(g, model, cond, images, audio_lat,
                                           video_vae, active_audio_vae, width, height, length, seed=seed)
    else:
        images, audio, _ = _ltx2_decode(g, av_out, video_vae, active_audio_vae)

    _ltx2_save(g, images, fps, filename_prefix, audio=audio, raw_audio=raw_audio)
    return g.to_dict()


def ltx2_multiframe(guide_frames: list[tuple[str, int, float]], prompt,
                     seconds=3, fps=24, filename_prefix="ltx2_mf",
                     second_pass=False, seed=None, audio_ref=None, audio_file=None,
                     speech_text=None, speech_voice="Clear, neutral voice",
                     speech_voice_name=None, include_audio=True):
    """LTX2 multiframe: guide the video with images at specific frame indices.
    guide_frames: list of (image_filename, frame_idx, strength).
      frame_idx=-1 means last frame. strength typically 0.6.
    Images are preprocessed with LTXVPreprocess.
    include_audio=True (default): LTX generates ambient audio.
    audio_file: filename of pre-generated audio in ComfyUI input dir (recommended for speech)."""
    g = WorkflowGraph()
    length = seconds * fps + 1
    width, height = 768, 512

    model, clip, video_vae, audio_vae = _ltx2_loaders(g)
    model = _ltx2_apply_loras(g, model, _ltx2_default_loras())
    cond  = _ltx2_condition(g, clip, prompt, fps=fps)

    base_latent = g.node("EmptyLTXVLatentVideo", width=width, height=height,
                         length=length, batch_size=1)

    # Chain LTXVAddGuide for each guide frame
    cur_pos    = cond[0]
    cur_neg    = cond[1]
    cur_latent = base_latent
    for img_file, frame_idx, strength in guide_frames:
        img    = g.node("LoadImage", image=img_file)
        resized = g.node("ResizeImagesByLongerEdge", images=img[0], longer_edge=1536)
        prep   = g.node("LTXVPreprocess", image=resized[0], img_compression=35)
        guided = g.node("LTXVAddGuide", positive=cur_pos, negative=cur_neg,
                        vae=video_vae[0], latent=cur_latent, image=prep[0],
                        frame_idx=frame_idx, strength=strength)
        cur_pos    = guided[0]
        cur_neg    = guided[1]
        cur_latent = guided[2]

    # Crop guides to finalize conditioning
    cropped      = g.node("LTXVCropGuides", positive=cur_pos, negative=cur_neg,
                          latent=cur_latent)
    final_pos    = cropped[0]
    final_neg    = cropped[1]
    final_latent = cropped[2]

    # Re-apply LTXVConditioning on cropped conditioning
    cond_cropped = g.node("LTXVConditioning", positive=final_pos, negative=final_neg,
                          frame_rate=float(fps))

    audio_latent, active_audio_vae, raw_audio = _ltx2_resolve_audio(
        g, audio_vae, length, fps, audio_ref, speech_text, speech_voice, speech_voice_name, include_audio, audio_file=audio_file)
    if audio_latent is not None:
        latent = g.node("LTXVConcatAVLatent", video_latent=final_latent,
                        audio_latent=audio_latent)
    else:
        latent = final_latent

    av_out = _ltx2_sample(g, model, cond_cropped, latent, steps=8, seed=seed)

    if second_pass:
        images, audio, audio_lat = _ltx2_decode(g, av_out, video_vae, active_audio_vae)
        images, audio = _ltx2_second_pass(g, model, cond_cropped, images, audio_lat,
                                           video_vae, active_audio_vae, width, height, length, seed=seed)
    else:
        images, audio, _ = _ltx2_decode(g, av_out, video_vae, active_audio_vae)

    _ltx2_save(g, images, fps, filename_prefix, audio=audio, raw_audio=raw_audio)
    return g.to_dict()



# ---------------------------------------------------------------------------
# LTX2.3 fragments (22B GGUF, two-stage distilled, built-in latent upscale)
# ---------------------------------------------------------------------------

def _ltx23_loaders(g):
    """Load LTX2.3 22B GGUF + DualCLIP + video VAE + audio VAE + spatial upscaler.
    Returns (model, clip, video_vae, audio_vae, upscaler)."""
    unet  = g.node("UnetLoaderGGUF", unet_name="ltx-2.3-22b-dev-Q4_K_M.gguf")
    model = g.node("LTXVChunkFeedForward", model=unet[0], chunks=4, dim_threshold=4096)
    clip  = g.node("DualCLIPLoader",
                   clip_name1="gemma_3_12B_it_fp4_mixed.safetensors",
                   clip_name2="ltx-2.3_text_projection_bf16.safetensors",
                   type="ltxv", device="default")
    video_vae  = g.node("VAELoaderKJ", vae_name="ltx-2.3-22b-dev_video_vae.safetensors",
                        device="main_device", weight_dtype="bf16")
    audio_vae  = g.node("VAELoaderKJ", vae_name="ltx-2.3-22b-dev_audio_vae.safetensors",
                        device="main_device", weight_dtype="bf16")
    upscaler   = g.node("LatentUpscaleModelLoader", model_name="ltx-2.3-spatial-upscaler-x2-1.0.safetensors")
    return model, clip, video_vae, audio_vae, upscaler


def _ltx23_condition(g, clip, positive_text, fps=24):
    """Encode prompt for LTX2.3. Returns cond NodeRef (cond[0]=pos, cond[1]=neg)."""
    pos = g.node("CLIPTextEncode", text=positive_text, clip=clip)
    neg = g.node("CLIPTextEncode",
                 text="blurry, low quality, watermark, distorted, still frame, inconsistent motion",
                 clip=clip)
    return g.node("LTXVConditioning", positive=pos[0], negative=neg[0], frame_rate=float(fps))


def _ltx23_sample_stage1(g, model, cond, latent, seed=None):
    """Stage 1: distilled 9-step rollout."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**32)
    sampler = g.node("KSamplerSelect", sampler_name="euler_ancestral_cfg_pp")
    sigmas  = g.node("ManualSigmas",
                     sigmas="1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0")
    noise   = g.node("RandomNoise", noise_seed=seed)
    guider  = g.node("CFGGuider", model=model[0], positive=cond[0], negative=cond[1], cfg=1.0)
    return g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0],
                  sampler=sampler[0], sigmas=sigmas[0], latent_image=latent)


def _ltx23_sample_stage2(g, model, cond, latent, seed=None):
    """Stage 2: 4-step refinement pass."""
    if seed is None:
        seed = int(time.time() * 1000) % (2**32)
    sampler = g.node("KSamplerSelect", sampler_name="euler_cfg_pp")
    sigmas  = g.node("ManualSigmas", sigmas="0.85, 0.7250, 0.4219, 0.0")
    noise   = g.node("RandomNoise", noise_seed=seed + 1)
    guider  = g.node("CFGGuider", model=model[0], positive=cond[0], negative=cond[1], cfg=1.0)
    return g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0],
                  sampler=sampler[0], sigmas=sigmas[0], latent_image=latent)


def _ltx23_decode_and_upscale(g, av_latent_s1, model, cond, video_vae, audio_vae, upscaler,
                               prep_image, seed=None):
    """Separate AV → upscale video latent → re-inject image → stage 2 → decode.
    Returns (images, audio)."""
    sep1     = g.node("LTXVSeparateAVLatent", av_latent=av_latent_s1)
    upsamp   = g.node("LTXVLatentUpsampler", samples=sep1[0], upscale_model=upscaler[0],
                      vae=video_vae[0])
    vid_cond = g.node("LTXVImgToVideoConditionOnly", vae=video_vae[0], image=prep_image,
                      latent=upsamp[0], strength=1.0, bypass=False)
    av_s2_in = g.node("LTXVConcatAVLatent", video_latent=vid_cond[0], audio_latent=sep1[1])
    av_out2  = _ltx23_sample_stage2(g, model, cond, av_s2_in[0], seed=seed)
    sep2     = g.node("LTXVSeparateAVLatent", av_latent=av_out2)
    images   = g.node("VAEDecodeTiled", samples=sep2[0], vae=video_vae[0],
                      tile_size=512, temporal_size=64, overlap=64, temporal_overlap=8)
    audio    = g.node("LTXVAudioVAEDecode", samples=sep2[1], audio_vae=audio_vae[0])
    return images, audio


def ltx23_image_to_video(image_filename, prompt, seconds=7, fps=24,
                          filename_prefix="ltx23_i2v", seed=None, include_audio=True):
    """LTX2.3 22B GGUF image-to-video. Two-stage distilled with built-in latent upscale.
    Output: 960×544 upscaled to full resolution. ~5-15 min on RTX 4070 Ti.
    No camera LoRA support yet (use prompt description instead).
    include_audio=True (default): generates ambient audio via LTX audio VAE."""
    g = WorkflowGraph()
    length = seconds * fps + 1
    width, height = 960, 544

    model, clip, video_vae, audio_vae, upscaler = _ltx23_loaders(g)
    lora  = g.node("LoraLoaderModelOnly", model=model[0],
                   lora_name="ltx-2.3-22b-distilled-lora-384.safetensors",
                   strength_model=0.5)
    cond  = _ltx23_condition(g, clip, prompt, fps=fps)

    frame   = g.node("LoadImage", image=image_filename)
    prep    = g.node("LTXVPreprocess", image=frame[0], img_compression=18)

    video_latent = g.node("EmptyLTXVLatentVideo", width=width, height=height,
                          length=length, batch_size=1)
    vid_cond_s1  = g.node("LTXVImgToVideoConditionOnly", vae=video_vae[0], image=prep[0],
                           latent=video_latent[0], strength=0.7, bypass=False)

    if include_audio:
        audio_latent = g.node("LTXVEmptyLatentAudio",
                              frames_number=int(length - 4), frame_rate=fps,
                              audio_vae=audio_vae[0], batch_size=1)
        latent_s1 = g.node("LTXVConcatAVLatent", video_latent=vid_cond_s1[0],
                           audio_latent=audio_latent[0])
    else:
        latent_s1 = vid_cond_s1

    av_out1 = _ltx23_sample_stage1(g, lora, cond, latent_s1[0], seed=seed)
    images, audio = _ltx23_decode_and_upscale(
        g, av_out1, lora, cond, video_vae, audio_vae, upscaler, prep[0], seed=seed)

    video = g.node("CreateVideo", images=images[0], fps=float(fps),
                   **{"audio": audio[0]} if include_audio else {})
    g.node("SaveVideo", video=video[0], filename_prefix=filename_prefix,
           format="auto", codec="auto")
    return g.to_dict()


def ltx23_text_to_video(prompt, seconds=7, fps=24,
                         filename_prefix="ltx23_t2v", seed=None, include_audio=True):
    """LTX2.3 22B GGUF text-to-video. Two-stage distilled with built-in latent upscale."""
    g = WorkflowGraph()
    length = seconds * fps + 1
    width, height = 960, 544

    model, clip, video_vae, audio_vae, upscaler = _ltx23_loaders(g)
    lora  = g.node("LoraLoaderModelOnly", model=model[0],
                   lora_name="ltx-2.3-22b-distilled-lora-384.safetensors",
                   strength_model=0.5)
    cond  = _ltx23_condition(g, clip, prompt, fps=fps)

    video_latent = g.node("EmptyLTXVLatentVideo", width=width, height=height,
                          length=length, batch_size=1)

    if include_audio:
        audio_latent = g.node("LTXVEmptyLatentAudio",
                              frames_number=int(length - 4), frame_rate=fps,
                              audio_vae=audio_vae[0], batch_size=1)
        latent_s1 = g.node("LTXVConcatAVLatent", video_latent=video_latent[0],
                           audio_latent=audio_latent[0])
    else:
        latent_s1 = video_latent

    av_out1  = _ltx23_sample_stage1(g, lora, cond, latent_s1[0], seed=seed)
    sep1     = g.node("LTXVSeparateAVLatent", av_latent=av_out1)
    upsamp   = g.node("LTXVLatentUpsampler", samples=sep1[0], upscale_model=upscaler[0],
                      vae=video_vae[0])
    av_s2_in = g.node("LTXVConcatAVLatent", video_latent=upsamp[0],
                      audio_latent=sep1[1]) if include_audio else upsamp
    av_out2  = _ltx23_sample_stage2(g, lora, cond, av_s2_in[0] if include_audio else upsamp[0], seed=seed)
    sep2     = g.node("LTXVSeparateAVLatent", av_latent=av_out2)
    images   = g.node("VAEDecodeTiled", samples=sep2[0], vae=video_vae[0],
                      tile_size=512, temporal_size=64, overlap=64, temporal_overlap=8)
    audio    = g.node("LTXVAudioVAEDecode", samples=sep2[1], audio_vae=audio_vae[0]) if include_audio else None

    video_node = g.node("CreateVideo", images=images[0], fps=float(fps),
                        **{"audio": audio[0]} if audio else {})
    g.node("SaveVideo", video=video_node[0], filename_prefix=filename_prefix,
           format="auto", codec="auto")
    return g.to_dict()


def extract_last_frame(video_path, filename_prefix="last_frame"):
    """Extract the last frame from a ComfyUI output video (by server-side path).
    video_path: absolute path on the ComfyUI server (e.g. /app/ComfyUI/output/myvideo.mp4).
    Saves a PNG to ComfyUI output — download and upload to input before using in i2v.

    Typical chaining pattern:
      1. Generate video → save locally
      2. run extract_last_frame with the server path → get PNG filename
      3. upload_to_input(local_png) → use as image_filename in ltx2_image_to_video
    """
    g = WorkflowGraph()
    frames = g.node("VHS_LoadVideoPath", video=video_path, force_rate=0,
                    custom_width=0, custom_height=0, frame_load_cap=0,
                    skip_first_frames=0, select_every_nth=1)
    last = g.node("GetImageRangeFromBatch", images=frames[0], start_index=-1, num_frames=1)
    g.node("SaveImage", images=last[0], filename_prefix=filename_prefix)
    return g.to_dict()


def qwen_tts(text, voice_instruct="A clear, friendly voice.", language="Auto",
              filename_prefix="tts"):
    """Qwen3-TTS with free-text voice style description."""
    g = WorkflowGraph()
    audio = _qwen_tts_design(g, text, voice_instruct, language)
    g.node("SaveAudioMP3", audio=audio[0], filename_prefix=filename_prefix, quality="V0", audioUI="")
    return g.to_dict()


def qwen_voice_clone(text, voice_name="gio", language="Auto", filename_prefix="clone"):
    """Clone a named voice and speak text. voice_name must be in VOICE_LIBRARY."""
    g = WorkflowGraph()
    audio = _qwen_voice_clone_audio(g, text, voice_name, language)
    g.node("SaveAudioMP3", audio=audio[0], filename_prefix=filename_prefix, quality="V0", audioUI="")
    return g.to_dict()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _submit_and_wait(workflow: dict, output_dir: Path, timeout: int = 600):
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(f"{BASE}/prompt", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.load(r)
    if result.get("node_errors"):
        print(f"[WARN] Node errors: {result['node_errors']}", file=sys.stderr)
    prompt_id = result["prompt_id"]
    print(f"prompt_id: {prompt_id}", file=sys.stderr)

    deadline = time.time() + timeout
    last_st = None
    while time.time() < deadline:
        with urllib.request.urlopen(f"{BASE}/history/{prompt_id}", timeout=15) as r:
            hist = json.load(r)
        entry = hist.get(prompt_id)
        if entry:
            outputs = entry.get("outputs", {})
            st = (entry.get("status") or {}).get("status_str") or (entry.get("status") or {}).get("status")
            if st and st != last_st:
                print(f"[{st}]", file=sys.stderr)
                last_st = st
            if outputs:
                _save_assets(entry, output_dir)
                return
            if (entry.get("status") or {}).get("completed") is True or st == "error":
                print("Completed with no outputs.", file=sys.stderr)
                return
        time.sleep(2)
    raise TimeoutError(f"Timed out after {timeout}s")


NOTIFY_TARGET = os.environ.get("OPENCLAW_NOTIFY_TARGET")


def _save_assets(entry: dict, output_dir: Path):
    import subprocess
    output_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    send_queue = []
    saved_files = []
    for nout in entry.get("outputs", {}).values():
        for v in nout.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "filename" in item:
                        fname = item["filename"]
                        if fname in seen:
                            continue
                        seen.add(fname)
                        sf = item.get("subfolder", "")
                        tp = item.get("type", "output")
                        url = f"{BASE}/view?filename={urllib.parse.quote(fname)}&subfolder={sf}&type={tp}&_={int(time.time()*1000)}"
                        print(f"asset_url: {url}")
                        dest = output_dir / fname
                        with urllib.request.urlopen(url, timeout=120) as r:
                            dest.write_bytes(r.read())
                        print(f"saved: {dest}")
                        saved_files.append(dest)
                        # queue this asset for the external sender (assistant watcher)
                        send_queue.append({
                            "filename": str(dest.resolve()),
                            "prompt_id": entry.get("prompt_id"),
                            "workflow": entry.get("workflow_name", ""),
                            "timestamp": int(time.time())
                        })
    # write a small JSON queue file atomically so an external watcher can pick it up
    if send_queue:
        queue_file = output_dir / "._send_queue.json"
        try:
            existing = []
            if queue_file.exists():
                with queue_file.open("r", encoding="utf-8") as f:
                    existing = json.load(f)
            existing.extend(send_queue)
            tmp = output_dir / f"._send_queue_{int(time.time())}.tmp"
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(existing, f)
            tmp.replace(queue_file)
            print(f"queued {len(send_queue)} asset(s) for sending: {queue_file}")
        except Exception as e:
            print(f"[WARN] Failed to write send queue: {e}", file=sys.stderr)

    # If a notify target is provided (CLI option sets global before calling), copy assets
    # into OpenClaw outbound folder and use the CLI to send them.
    notify = globals().get("NOTIFY_TARGET")
    if notify:
        outbound_dir = Path.home() / ".openclaw" / "media" / "outbound"
        outbound_dir.mkdir(parents=True, exist_ok=True)
        outbound_log = outbound_dir / "send-log-cli.txt"
        for p in saved_files:
            try:
                dst = outbound_dir / p.name
                if not dst.exists():
                    dst.write_bytes(p.read_bytes())

                # wait for file stability (size unchanged for 1s)
                stable_count = 0
                last_size = -1
                for _ in range(10):
                    try:
                        cur_size = dst.stat().st_size
                    except Exception:
                        cur_size = -1
                    if cur_size == last_size and cur_size > 0:
                        stable_count += 1
                    else:
                        stable_count = 0
                    if stable_count >= 2:
                        break
                    last_size = cur_size
                    time.sleep(0.5)

                # call openclaw CLI to send the file and capture output
                caption = f"{p.name} — generated asset (prompt_id={entry.get('prompt_id')})"
                cmd = ["openclaw", "message", "send", "--channel", "telegram", "--target", str(notify), "--message", caption, "--media", str(dst.resolve())]
                print("Running:", " ".join(cmd))
                proc = subprocess.run(cmd, check=False, capture_output=True, text=True)

                # log CLI stdout/stderr and exit code to both logs
                main_logf = output_dir / "send-log.txt"
                try:
                    with main_logf.open("a", encoding="utf-8") as lf:
                        lf.write(f"[{time.ctime()}] CMD: {' '.join(cmd)}\n")
                        lf.write(f"exit={proc.returncode}\n")
                        if proc.stdout:
                            lf.write("STDOUT:\n" + proc.stdout + "\n")
                        if proc.stderr:
                            lf.write("STDERR:\n" + proc.stderr + "\n")
                except Exception as e:
                    print(f"[WARN] Failed to write main send-log: {e}", file=sys.stderr)
                try:
                    with outbound_log.open("a", encoding="utf-8") as of:
                        of.write(f"[{time.ctime()}] CMD: {' '.join(cmd)}\n")
                        of.write(f"exit={proc.returncode}\n")
                        if proc.stdout:
                            of.write("STDOUT:\n" + proc.stdout + "\n")
                        if proc.stderr:
                            of.write("STDERR:\n" + proc.stderr + "\n")
                except Exception as e:
                    print(f"[WARN] Failed to write outbound send-log: {e}", file=sys.stderr)

            except Exception as e:
                print(f"[WARN] Failed to send asset {p}: {e}", file=sys.stderr)


def upload_image(local_path: str) -> str:
    """Upload a local image file to ComfyUI's input directory.
    Returns the filename as registered on the server (use this in LoadImage nodes).
    Works with any image format; content-type is inferred from extension."""
    path = Path(local_path)
    data = path.read_bytes()
    ext = path.suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png" if ext == ".png" else "application/octet-stream"
    boundary = "----ComfyUploadBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="type"\r\n\r\ninput\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="subfolder"\r\n\r\n\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    return resp["name"]


def upload_if_local(path: str, upload_flag: bool = True) -> str:
    """If path points to local file and upload_flag True, upload to ComfyUI input dir and return server filename.
    Otherwise return the original path unchanged."""
    if not path:
        return path
    try:
        p = Path(path)
        if p.exists() and upload_flag:
            try:
                server = upload_image(str(p))
                print(f"Uploaded local image {p} -> {server}")
                return server
            except Exception as e:
                print(f"[WARN] Failed to upload image {p}: {e}", file=sys.stderr)
                return path
    except Exception:
        pass
    return path


def _parse_args(args):
    opts = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                opts[key] = args[i + 1]; i += 2
            else:
                opts[key] = True; i += 1
        else:
            i += 1
    return opts


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__); sys.exit(1)

    dump_only = args[0] == "dump"
    if dump_only:
        args = args[1:]
    if not args:
        print(__doc__); sys.exit(1)

    cmd  = args[0]
    opts = _parse_args(args[1:])

    output_dir  = Path(opts.get("output_dir", "outputs"))
    timeout     = int(opts.get("timeout", 600))
    seed_raw      = opts.get("seed")
    seed          = int(seed_raw) if seed_raw else None
    second_pass   = "second_pass" in opts
    speech_text   = opts.get("speech_text")
    speech_voice  = opts.get("speech_voice", "Clear, neutral voice")
    speech_voice_name = opts.get("speech_voice_name")
    audio_file    = opts.get("audio_file")
    include_audio = "no_audio" not in opts

    # Notify target resolution: CLI flag first, then env var
    notify_target = opts.get('notify_target') or os.environ.get('OPENCLAW_NOTIFY_TARGET')
    # Enforce presence of notify target for generation commands to ensure outbound sending works
    generation_cmds = {'t2i','i2i','i2i2','angles','t2v','i2v','mf'}
    if cmd in generation_cmds and not notify_target:
        print("ERROR: No notify target set. To receive generated assets via OpenClaw, set the environment variable OPENCLAW_NOTIFY_TARGET or pass --notify-target when calling the CLI.")
        print("Example: setx OPENCLAW_NOTIFY_TARGET telegram:123456789")
        print("Or: python comfy_graph.py angles --image input.png --prompts \"front\\nside\" --notify-target telegram:123456789")
        sys.exit(2)

    if cmd == "t2i":
        wf = flux2_text_to_image(
            prompt=opts.get("prompt", ""),
            width=int(opts.get("width", 1024)), height=int(opts.get("height", 576)),
            steps=int(opts.get("steps", 4)),
            filename_prefix=opts.get("prefix", "flux2_t2i"),
            lora=opts.get("lora"), lora_strength=float(opts.get("lora_strength", 1.0)),
            seed=seed)
    elif cmd == "i2i":
        image_arg = opts.get("image")
        # upload local image if requested
        if image_arg:
            image_arg = upload_if_local(image_arg, upload_flag=("upload_inputs" in opts or opts.get("upload_inputs") == "1" or opts.get("upload_inputs") == "true"))
        wf = flux2_single_image_edit(
            image_filename=image_arg, prompt=opts.get("prompt", ""),
            width=int(opts.get("width", 1024)), height=int(opts.get("height", 576)),
            steps=int(opts.get("steps", 4)),
            filename_prefix=opts.get("prefix", "flux2_i2i"), seed=seed)
    elif cmd == "i2i2":
        image1 = opts.get("image1")
        image2 = opts.get("image2")
        image1 = upload_if_local(image1, upload_flag=("upload_inputs" in opts or opts.get("upload_inputs") == "1" or opts.get("upload_inputs") == "true"))
        image2 = upload_if_local(image2, upload_flag=("upload_inputs" in opts or opts.get("upload_inputs") == "1" or opts.get("upload_inputs") == "true"))
        wf = flux2_double_image_edit(
            image1_filename=image1, image2_filename=image2,
            prompt=opts.get("prompt", ""),
            width=int(opts.get("width", 1024)), height=int(opts.get("height", 576)),
            steps=int(opts.get("steps", 4)),
            filename_prefix=opts.get("prefix", "flux2_i2i2"), seed=seed)
    elif cmd == "angles":
        prompts_raw = opts.get("prompts", "front view\nside view\n3/4 view")
        angle_prompts = [p.strip() for p in prompts_raw.splitlines() if p.strip()]
        image_arg = opts.get("image")
        # If a local file path was provided, upload it to ComfyUI input dir and use the server filename
        if image_arg:
            local_path = Path(image_arg)
            if local_path.exists():
                try:
                    server_name = upload_image(str(local_path))
                    image_arg = server_name
                    print(f"Uploaded local image {local_path} -> {server_name}")
                except Exception as e:
                    print(f"[WARN] Failed to upload image {local_path}: {e}", file=sys.stderr)
        wf = flux2_multiple_angles(
            image_filename=image_arg,
            angle_prompts=angle_prompts,
            filename_prefix=opts.get("prefix", "flux2_angles"))
    elif cmd == "t2v":
        model_ver = opts.get("model", "ltx23")
        if model_ver == "ltx2":
            wf = ltx2_text_to_video(
                prompt=opts.get("prompt", ""),
                seconds=int(opts.get("seconds", 3)), fps=int(opts.get("fps", 24)),
                camera_lora=opts.get("camera"),
                filename_prefix=opts.get("prefix", "ltx2_t2v"),
                second_pass=second_pass, seed=seed, audio_file=audio_file,
                speech_text=speech_text, speech_voice=speech_voice,
                speech_voice_name=speech_voice_name, include_audio=include_audio)
        else:
            wf = ltx23_text_to_video(
                prompt=opts.get("prompt", ""),
                seconds=int(opts.get("seconds", 7)), fps=int(opts.get("fps", 24)),
                filename_prefix=opts.get("prefix", "ltx23_t2v"),
                seed=seed, include_audio=include_audio)
    elif cmd == "i2v":
        model_ver = opts.get("model", "ltx23")
        image_arg = opts.get("image")
        if image_arg:
            image_arg = upload_if_local(image_arg, upload_flag=("upload_inputs" in opts or opts.get("upload_inputs") == "1" or opts.get("upload_inputs") == "true"))
        if model_ver == "ltx2":
            wf = ltx2_image_to_video(
                image_filename=image_arg, prompt=opts.get("prompt", ""),
                seconds=int(opts.get("seconds", 3)), fps=int(opts.get("fps", 24)),
                camera_lora=opts.get("camera"),
                filename_prefix=opts.get("prefix", "ltx2_i2v"),
                second_pass=second_pass, seed=seed, audio_file=audio_file,
                speech_text=speech_text, speech_voice=speech_voice,
                speech_voice_name=speech_voice_name, include_audio=include_audio)
        else:
            wf = ltx23_image_to_video(
                image_filename=image_arg, prompt=opts.get("prompt", ""),
                seconds=int(opts.get("seconds", 7)), fps=int(opts.get("fps", 24)),
                filename_prefix=opts.get("prefix", "ltx23_i2v"),
                seed=seed, include_audio=include_audio)
    elif cmd == "mf":
        # --frames accepts comma-separated or JSON list of "filename:frame_idx" entries
        frames_raw = opts.get("frames", "")
        guide_frames = []
        parts = []
        if frames_raw.startswith("["):
            # JSON list
            try:
                parts = json.loads(frames_raw)
            except Exception:
                parts = [frames_raw]
        else:
            parts = [p.strip() for p in frames_raw.split(",") if p.strip()]
        for part in parts:
            part = part.strip()
            if ":" in part:
                fname, idx = part.rsplit(":", 1)
                fname = fname.strip()
                # upload local file when requested
                fname = upload_if_local(fname, upload_flag=("upload_inputs" in opts or opts.get("upload_inputs") == "1" or opts.get("upload_inputs") == "true"))
                guide_frames.append((fname, int(idx), float(opts.get("strength", 0.6))))
        wf = ltx2_multiframe(
            guide_frames=guide_frames, prompt=opts.get("prompt", ""),
            seconds=int(opts.get("seconds", 3)), fps=int(opts.get("fps", 24)),
            filename_prefix=opts.get("prefix", "ltx2_mf"),
            second_pass=second_pass, seed=seed, audio_file=audio_file,
            speech_text=speech_text, speech_voice=speech_voice,
            speech_voice_name=speech_voice_name, include_audio=include_audio)
    elif cmd == "upload":
        # upload <local_path> — uploads image to ComfyUI input dir, prints server filename
        local = args[1] if len(args) > 1 else opts.get("file", "")
        if not local:
            print("Usage: comfy_graph.py upload <local_image_path>"); sys.exit(1)
        server_name = upload_image(local)
        print(server_name)
        return
    elif cmd == "last_frame":
        # --video <server_path_to_mp4>  e.g. /app/ComfyUI/output/myvideo.mp4
        wf = extract_last_frame(
            video_path=opts["video"],
            filename_prefix=opts.get("prefix", "last_frame"))
        timeout = int(opts.get("timeout", 60))
    elif cmd == "tts":
        wf = qwen_tts(
            text=opts.get("text", opts.get("prompt", "")),
            voice_instruct=opts.get("voice", "A clear, friendly voice."),
            language=opts.get("lang", "Auto"),
            filename_prefix=opts.get("prefix", "tts"))
        timeout = int(opts.get("timeout", 120))
    elif cmd == "clone":
        wf = qwen_voice_clone(
            text=opts.get("text", opts.get("prompt", "")),
            voice_name=opts.get("voice_name", "gio"),
            language=opts.get("lang", "Auto"),
            filename_prefix=opts.get("prefix", "clone"))
        timeout = int(opts.get("timeout", 120))
    else:
        print(f"Unknown command: {cmd}\n{__doc__}"); sys.exit(1)

    if dump_only:
        print(json.dumps(wf, indent=2))
        return

    # Set notify target from CLI flag or environment fallback
    notify = opts.get('notify_target') or os.environ.get('OPENCLAW_NOTIFY_TARGET')
    if notify:
        globals()['NOTIFY_TARGET'] = notify

    _submit_and_wait(wf, output_dir, timeout)


if __name__ == "__main__":
    main()
