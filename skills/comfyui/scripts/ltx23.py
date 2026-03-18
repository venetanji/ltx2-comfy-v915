from core import WorkflowGraph

def ltx23_text_to_video(prompt, seconds=7, fps=24,
                         filename_prefix="ltx23_t2v", seed=None, include_audio=True):
    g = WorkflowGraph()
    length = seconds * fps + 1
    width, height = 960, 544

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

    pos = g.node("CLIPTextEncode", text=prompt, clip=clip)
    neg = g.node("CLIPTextEncode", text="blurry, low quality, watermark, distorted, still frame, inconsistent motion", clip=clip)
    cond = g.node("LTXVConditioning", positive=pos[0], negative=neg[0], frame_rate=float(fps))

    video_latent = g.node("EmptyLTXVLatentVideo", width=width, height=height, length=length, batch_size=1)
    if include_audio:
        audio_latent = g.node("LTXVEmptyLatentAudio", frames_number=int(length - 4), frame_rate=fps, audio_vae=audio_vae[0], batch_size=1)
        latent_s1 = g.node("LTXVConcatAVLatent", video_latent=video_latent[0], audio_latent=audio_latent[0])
    else:
        latent_s1 = video_latent

    sampler = g.node("KSamplerSelect", sampler_name="euler_ancestral_cfg_pp")
    sigmas  = g.node("ManualSigmas", sigmas="1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0")
    noise   = g.node("RandomNoise", noise_seed=int(time.time() * 1000) % (2**32))
    guider  = g.node("CFGGuider", model=model[0], positive=cond[0], negative=cond[1], cfg=1.0)
    av_out1 = g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0], sampler=sampler[0], sigmas=sigmas[0], latent_image=latent_s1[0])

    sep1     = g.node("LTXVSeparateAVLatent", av_latent=av_out1)
    upsamp   = g.node("LTXVLatentUpsampler", samples=sep1[0], upscale_model=upscaler[0], vae=video_vae[0])
    av_s2_in = g.node("LTXVConcatAVLatent", video_latent=upsamp[0], audio_latent=sep1[1]) if include_audio else upsamp
    sampler2 = g.node("KSamplerSelect", sampler_name="euler_cfg_pp")
    sigmas2  = g.node("ManualSigmas", sigmas="0.85, 0.7250, 0.4219, 0.0")
    noise2   = g.node("RandomNoise", noise_seed=int(time.time() * 1000) % (2**32) + 1)
    guider2  = g.node("CFGGuider", model=model[0], positive=cond[0], negative=cond[1], cfg=1.0)
    av_out2  = g.node("SamplerCustomAdvanced", noise=noise2[0], guider=guider2[0], sampler=sampler2[0], sigmas=sigmas2[0], latent_image=av_s2_in[0] if include_audio else av_s2_in)

    sep2     = g.node("LTXVSeparateAVLatent", av_latent=av_out2)
    images   = g.node("VAEDecodeTiled", samples=sep2[0], vae=video_vae[0], tile_size=512, temporal_size=64, overlap=64, temporal_overlap=8)
    audio    = g.node("LTXVAudioVAEDecode", samples=sep2[1], audio_vae=audio_vae[0]) if include_audio else None

    video_node = g.node("CreateVideo", images=images[0], fps=float(fps), **{"audio": audio[0]} if audio else {})
    g.node("SaveVideo", video=video_node[0], filename_prefix=filename_prefix, format="auto", codec="auto")
    return g.to_dict()

print('ltx23 module loaded')
