import time
from core import WorkflowGraph


def flux2_text_to_image(prompt, width=1024, height=576, steps=4,
                         filename_prefix="flux2_t2i", lora=None, lora_strength=1.0, seed=None):
    g = WorkflowGraph()
    unet = g.node("UNETLoader", unet_name="flux-2-klein-4b-fp8.safetensors", weight_dtype="default")
    vae  = g.node("VAELoader", vae_name="flux2-vae.safetensors")
    clip = g.node("CLIPLoader", clip_name="qwen_3_4b.safetensors", type="flux2", device="default")
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

print('flux2 module loaded')
