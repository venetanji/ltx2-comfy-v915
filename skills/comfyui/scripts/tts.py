from core import WorkflowGraph

def qwen_tts(text, voice_instruct="A clear, friendly voice.", language="Auto",
              filename_prefix="tts"):
    g = WorkflowGraph()
    audio = g.node("AILab_Qwen3TTSVoiceDesign", text=text, instruct=voice_instruct, model_size="1.7B", language=language, unload_models=True, seed=-1)
    g.node("SaveAudioMP3", audio=audio[0], filename_prefix=filename_prefix, quality="V0", audioUI="")
    return g.to_dict()

print('tts module loaded')
