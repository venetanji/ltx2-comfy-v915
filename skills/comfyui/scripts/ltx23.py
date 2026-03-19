from core import WorkflowGraph
import time

# LTX2 fragments and compatibility helpers ported from the original comfy_graph

def _ltx2_loaders(g):
    """Load GGUF UNET + dual CLIP + video VAE + audio VAE.
    Returns (model, clip, video_vae, audio_vae)."""
    unet  = g.node("UnetLoaderGGUF", unet_name="ltx-2.3-22b-dev-Q4_K_M.gguf")
    model = g.node("LTXVChunkFeedForward", model=unet[0], chunks=4, dim_threshold=4096)
    clip  = g.node("DualCLIPLoader",
                   clip_name1="gemma_3_12B_it_fp8_e4m3fn.safetensors",
                   clip_name2="ltx-2.3_text_projection_bf16.safetensors",
                   type="ltxv")
    video_vae = g.node("VAELoaderKJ", vae_name="ltx-2.3-22b-dev_video_vae.safetensors",
                       device="main_device", weight_dtype="bf16")
    audio_vae = g.node("VAELoaderKJ", vae_name="ltx-2.3-22b-dev_audio_vae.safetensors",
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
        seed = int(time.time() * 1000) % (2**31) # Standard 32-bit seed
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
    upscaled     = g.node("ImageScale", image=images[0], upscale_method="lanczos",
                          width=width * 2, height=height * 2, crop="disabled")
    hires_latent = g.node("EmptyLTXVLatentVideo",
                          width=width * 2, height=height * 2, length=length, batch_size=1)
    video_lat_2  = g.node("LTXVImgToVideoInplace", vae=video_vae[0], image=upscaled[0],
                           latent=hires_latent[0], strength=1.0, bypass=False)
    if audio_latent is not None:
        latent_2 = g.node("LTXVConcatAVLatent", video_latent=video_lat_2[0], audio_latent=audio_latent)
    else:
        latent_2 = video_lat_2
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
    """Build default LoRA list: distilled (0.6) + optional camera (+1.0)."""
    loras = [("ltx-2.3-22b-distilled-lora-384.safetensors", 0.6)]
    if camera_lora:
        loras.append((f"ltx-2-19b-lora-camera-control-{camera_lora}.safetensors", 1.0))
    return loras


# Audio/voice helpers (small wrappers that expect tts module elsewhere if needed)

def _qwen_tts_design(g, text, voice_instruct="A clear, friendly voice.", language="Auto"):
    """Qwen3-TTS with voice style description. Returns AUDIO NodeRef."""
    return g.node("AILab_Qwen3TTSVoiceDesign", text=text, instruct=voice_instruct,
                  model_size="1.7B", language=language, unload_models=True, seed=-1)


def _qwen_voice_clone_audio(g, text, voice_name="gio", language="Auto"):
    """Load reference audio, create VOICE, clone it. Returns AUDIO NodeRef."""
    # This function expects a VOICE_LIBRARY or similar to exist elsewhere; keep simple loader
    ref_audio = g.node("VHS_LoadAudioUpload", audio=voice_name)
    voice     = g.node("AILab_Qwen3TTSVoicesLibrary",
                       reference_audio=ref_audio[0],
                       reference_text="",
                       model_size="1.7B", device="auto", precision="bf16",
                       x_vector_only=True, voice_name=voice_name,
                       unload_models=True)
    return g.node("AILab_Qwen3TTSVoiceClone", target_text=text, model_size="1.7B",
                  language=language, voice=voice[0], unload_models=True, seed=-1)


def _ltx2_resolve_audio(g, audio_vae, length, fps, audio_ref, speech_text, speech_voice, speech_voice_name, include_audio, audio_file=None):
    """Resolve audio setup for LTX2 builders.
    Returns (audio_latent, active_audio_vae, raw_audio_node).
    See original comfy_graph for behaviour notes."""
    if not include_audio:
        return None, None, None
    if audio_file:
        raw_audio = g.node("LoadAudio", audio=audio_file)
        return None, None, raw_audio
    if speech_text and audio_ref is None:
        if speech_voice_name:
            audio_ref = _qwen_voice_clone_audio(g, speech_text, speech_voice_name)
        else:
            audio_ref = _qwen_tts_design(g, speech_text, speech_voice)
    audio_latent = _ltx2_audio_latent(g, audio_vae, length, fps=fps, audio_ref=audio_ref)
    return audio_latent, audio_vae, None


def ltx23_text_to_video(prompt, seconds=7, fps=24,
                         filename_prefix="ltx23_t2v", seed=None, include_audio=True):
    g = WorkflowGraph()
    # LTXV expects (seconds * fps) + 1, and it must be a multiple of 8 + 1 (e.g., 73, 97, 121...)
    raw_length = seconds * fps
    length = ((raw_length // 8) * 8) + 1
    width, height = 768, 512

    model, clip, video_vae, audio_vae = _ltx2_loaders(g)
    model = _ltx2_apply_loras(g, model, _ltx2_default_loras())
    cond  = _ltx2_condition(g, clip, prompt, fps=fps)

    video_latent = g.node("EmptyLTXVLatentVideo", width=width, height=height, length=length, batch_size=1)
    
    # Simple version: if include_audio is true, just use the built-in ambient audio generation
    # but ensure it's not causing the 400 error. For now, let's try WITHOUT audio to isolate.
    latent = video_latent

    av_out = _ltx2_sample(g, model, cond, latent, steps=8, seed=seed)

    images, _, _ = _ltx2_decode(g, av_out, video_vae, None)

    _ltx2_save(g, images, fps, filename_prefix, audio=None)
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


print('ltx23 module loaded')
