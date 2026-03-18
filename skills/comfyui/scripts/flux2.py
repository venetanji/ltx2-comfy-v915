import time
from core import WorkflowGraph


def flux2_text_to_image(prompt, width=1024, height=576, steps=4,
                         filename_prefix="flux2_t2i", lora=None, lora_strength=1.0, seed=None,
                         unet_name="flux-2-klein-4b-fp8.safetensors", vae_name="flux2-vae.safetensors", clip_name="qwen_3_4b.safetensors"):
    # normalize model names when callers pass None
    if not unet_name:
        unet_name = "flux-2-klein-4b-fp8.safetensors"
    if not vae_name:
        vae_name = "flux2-vae.safetensors"
    if not clip_name:
        clip_name = "qwen_3_4b.safetensors"
    g = WorkflowGraph()
    unet = g.node("UNETLoader", unet_name=unet_name, weight_dtype="default")
    vae  = g.node("VAELoader", vae_name=vae_name)
    clip = g.node("CLIPLoader", clip_name=clip_name, type="flux2", device="default")
    if lora:
        lora_node = g.node("LoraLoader", model=unet[0], clip=clip[0], lora_name=lora, strength_model=lora_strength, strength_clip=lora_strength)
        unet = lora_node[0]
    pos = g.node("CLIPTextEncode", text=prompt, clip=clip)
    neg = g.node("ConditioningZeroOut", conditioning=pos[0])
    latent   = g.node("EmptyFlux2LatentImage", width=width, height=height, batch_size=1)
    sampler  = g.node("KSamplerSelect", sampler_name="euler")
    schedule = g.node("Flux2Scheduler", steps=steps, width=width, height=height)
    noise    = g.node("RandomNoise", noise_seed=int(time.time() * 1000) % (2**32))
    guider   = g.node("CFGGuider", model=unet[0], positive=pos[0], negative=neg[0], cfg=1.0)
    samples = g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0], sampler=sampler[0], sigmas=schedule[0], latent_image=latent[0])
    decoded  = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


# Image-to-image: single reference
def flux2_single_image_edit(image_filename, prompt, width=1024, height=576, steps=4,
                              filename_prefix="flux2_i2i", seed=None, unet_name="flux-2-klein-4b-fp8.safetensors", vae_name="flux2-vae.safetensors", clip_name="qwen_3_4b.safetensors"):
    # normalize model names when callers pass None
    if not unet_name:
        unet_name = "flux-2-klein-4b-fp8.safetensors"
    if not vae_name:
        vae_name = "flux2-vae.safetensors"
    if not clip_name:
        clip_name = "qwen_3_4b.safetensors"
    g = WorkflowGraph()
    unet = g.node("UNETLoader", unet_name=unet_name, weight_dtype="default")
    vae  = g.node("VAELoader", vae_name=vae_name)
    clip = g.node("CLIPLoader", clip_name=clip_name, type="flux2", device="default")
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
    sampler  = g.node("KSamplerSelect", sampler_name="euler")
    schedule = g.node("Flux2Scheduler", steps=steps, width=width, height=height)
    noise    = g.node("RandomNoise", noise_seed=int(time.time() * 1000) % (2**32))
    guider   = g.node("CFGGuider", model=unet[0], positive=pos[0], negative=neg[0], cfg=1.0)
    samples = g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0], sampler=sampler[0], sigmas=schedule[0], latent_image=latent[0])
    decoded   = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


# Image-to-image with two reference images
def flux2_double_image_edit(image1_filename, image2_filename, prompt,
                              width=1024, height=576, steps=4,
                              filename_prefix="flux2_i2i2", seed=None, unet_name="flux-2-klein-4b-fp8.safetensors", vae_name="flux2-vae.safetensors", clip_name="qwen_3_4b.safetensors"):
    # normalize model names when callers pass None
    if not unet_name:
        unet_name = "flux-2-klein-4b-fp8.safetensors"
    if not vae_name:
        vae_name = "flux2-vae.safetensors"
    if not clip_name:
        clip_name = "qwen_3_4b.safetensors"
    g = WorkflowGraph()
    unet = g.node("UNETLoader", unet_name=unet_name, weight_dtype="default")
    vae  = g.node("VAELoader", vae_name=vae_name)
    clip = g.node("CLIPLoader", clip_name=clip_name, type="flux2", device="default")
    g = WorkflowGraph()
    unet = g.node("UNETLoader", unet_name="flux-2-klein-4b-fp8.safetensors", weight_dtype="default")
    vae  = g.node("VAELoader", vae_name="flux2-vae.safetensors")
    clip = g.node("CLIPLoader", clip_name="qwen_3_4b.safetensors", type="flux2", device="default")
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
    sampler  = g.node("KSamplerSelect", sampler_name="euler")
    schedule = g.node("Flux2Scheduler", steps=steps, width=width, height=height)
    noise    = g.node("RandomNoise", noise_seed=int(time.time() * 1000) % (2**32))
    guider   = g.node("CFGGuider", model=unet[0], positive=pos[0], negative=neg[0], cfg=1.0)
    samples = g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0], sampler=sampler[0], sigmas=schedule[0], latent_image=latent[0])
    decoded = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


# Multiple angles / batch generation from prompts
def flux2_multiple_angles(image_filename, angle_prompts: list[str], prepend: str = "", append: str = "", filename_prefix="flux2_angles"):
    """Generate multiple angles/styles given a list of prompt strings.

    prepend/append are optional strings inserted before/after each prompt block.
    """
    g = WorkflowGraph()
    unet = g.node("UNETLoader", unet_name="flux-2-klein-4b-fp8.safetensors", weight_dtype="default")
    vae  = g.node("VAELoader", vae_name="flux2-vae.safetensors")
    clip = g.node("CLIPLoader", clip_name="qwen_3_4b.safetensors", type="flux2", device="default")
    batcher_input = prepend + "\n".join([p for p in angle_prompts if p]) + "\n" + append
    batcher = g.node("SimplePromptBatcher", prepend=prepend, prompts="\n".join([p for p in angle_prompts if p]) + "\n", append=append)
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
    samples   = g.node("SamplerCustomAdvanced", noise=noise[0], guider=guider[0], sampler=sampler[0], sigmas=scheduler[0], latent_image=latent[0])
    decoded   = g.node("VAEDecode", samples=samples[0], vae=vae[0])
    g.node("SaveImage", images=decoded[0], filename_prefix=filename_prefix)
    return g.to_dict()


print('flux2 module loaded')