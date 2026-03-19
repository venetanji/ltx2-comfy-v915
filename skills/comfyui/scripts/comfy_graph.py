#!/usr/bin/env python3
"""Thin CLI wrapper importing modular workflows from flux2, ltx23 and tts.
Keeps original argument parsing and behavior but delegates to modules.
"""
from __future__ import annotations

import sys
import os
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from core import _submit_and_wait
import flux2
import ltx23
import tts

# Backwards-compatibility exports (old comfy_graph API expected these symbols on import)
# Flux2
flux2_text_to_image = flux2.flux2_text_to_image
flux2_single_image_edit = flux2.flux2_single_image_edit
flux2_double_image_edit = flux2.flux2_double_image_edit
flux2_multiple_angles = flux2.flux2_multiple_angles
# TTS
qwen_tts = tts.qwen_tts
qwen_voice_clone = tts.qwen_voice_clone
# LTX2 (map old names to new module functions)
# The ltx23 module restores the original ltx2_* implementations, so map names accordingly.
ltx2_text_to_video = ltx23.ltx23_text_to_video
ltx2_image_to_video = getattr(ltx23, 'ltx2_image_to_video', None)
ltx2_multiframe = getattr(ltx23, 'ltx2_multiframe', None)
extract_last_frame = getattr(ltx23, 'extract_last_frame', None)

BASE = os.environ.get("COMFY_URL", "http://localhost:8188").rstrip("/")


def _parse_args(args):
    opts = {}
    i = 0
    while i < len(args):
        a = args[i]
        if a.startswith("--"):
            key = a[2:].replace("-", "_")
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                val = args[i + 1]
                if key in opts:
                    if isinstance(opts[key], list):
                        opts[key].append(val)
                    else:
                        opts[key] = [opts[key], val]
                else:
                    opts[key] = val
                i += 2
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

    notify_target = opts.get('notify_target') or __import__('os').environ.get('OPENCLAW_NOTIFY_TARGET')
    generation_cmds = {'t2i','i2i','i2i2','angles','t2v','i2v','mf', 'last_frame'}
    if cmd in generation_cmds and not notify_target:
        print("ERROR: No notify target set. To receive generated assets via OpenClaw, set the environment variable OPENCLAW_NOTIFY_TARGET or pass --notify-target when calling the CLI.")
        sys.exit(2)

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

    if cmd == "t2i":
        wf = flux2.flux2_text_to_image(
            prompt=opts.get("prompt", ""),
            width=int(opts.get("width", 1024)), height=int(opts.get("height", 576)),
            steps=int(opts.get("steps", 4)),
            filename_prefix=opts.get("prefix", "flux2_t2i"),
            lora=opts.get("lora"), lora_strength=float(opts.get("lora_strength", 1.0)),
            seed=seed)
    elif cmd == "i2i":
        image_arg = upload_if_local(opts.get("image", ""))
        wf = flux2.flux2_single_image_edit(
            image_filename=image_arg, prompt=opts.get("prompt", ""),
            width=int(opts.get("width", 1024)), height=int(opts.get("height", 576)),
            steps=int(opts.get("steps", 4)),
            filename_prefix=opts.get("prefix", "flux2_i2i"), seed=seed,
            unet_name=opts.get('unet'), vae_name=opts.get('vae'), clip_name=opts.get('clip'))
    elif cmd == "i2i2":
        img1 = upload_if_local(opts.get("image1", ""))
        img2 = upload_if_local(opts.get("image2", ""))
        wf = flux2.flux2_double_image_edit(
            image1_filename=img1, image2_filename=img2,
            prompt=opts.get("prompt", ""),
            width=int(opts.get("width", 1024)), height=int(opts.get("height", 576)),
            steps=int(opts.get("steps", 4)),
            filename_prefix=opts.get("prefix", "flux2_i2i2"), seed=seed,
            unet_name=opts.get('unet'), vae_name=opts.get('vae'), clip_name=opts.get('clip'))
    elif cmd == "angles":
        prompts_raw = opts.get("prompts", "front view\nside view\n3/4 view")
        angle_prompts = [p.strip() for p in prompts_raw.splitlines() if p.strip()]
        image_arg = upload_if_local(opts.get("image", ""))
        prepend = opts.get("prepend", "")
        append = opts.get("append", "")
        wf = flux2.flux2_multiple_angles(
            image_filename=image_arg,
            angle_prompts=angle_prompts,
            prepend=prepend, append=append,
            filename_prefix=opts.get("prefix", "flux2_angles"))
    elif cmd == "tts":
        wf = tts.qwen_tts(text=opts.get("text", opts.get("prompt", "")), filename_prefix=opts.get("prefix", "tts"))
        timeout = int(opts.get("timeout", 120))
    elif cmd == "t2v":
        wf = ltx23.ltx23_text_to_video(prompt=opts.get("prompt",""), seconds=int(opts.get("seconds",7)), fps=int(opts.get("fps",24)), filename_prefix=opts.get("prefix","ltx23_t2v"), seed=seed)
    elif cmd == "i2v":
        image_arg = upload_if_local(opts.get("image", ""))
        wf = ltx23.ltx2_image_to_video(
            image_filename=image_arg, prompt=opts.get("prompt", ""),
            seconds=int(opts.get("seconds", 3)), fps=int(opts.get("fps", 24)),
            camera_lora=opts.get("camera_lora"),
            filename_prefix=opts.get("prefix", "ltx2_i2v"),
            second_pass=second_pass, seed=seed,
            speech_text=speech_text, speech_voice=speech_voice,
            speech_voice_name=speech_voice_name, audio_file=audio_file,
            include_audio=include_audio)
    elif cmd == "mf":
        # multiframe expects a series of --frame <file>:<idx>:<strength>
        frames_raw = opts.get("frame", "")
        if isinstance(frames_raw, str):
            frames_raw = [frames_raw]
        guide_frames = []
        for f in frames_raw:
            parts = f.split(":")
            if len(parts) == 3:
                guide_frames.append((upload_if_local(parts[0]), int(parts[1]), float(parts[2])))
        wf = ltx23.ltx2_multiframe(
            guide_frames=guide_frames, prompt=opts.get("prompt", ""),
            seconds=int(opts.get("seconds", 3)), fps=int(opts.get("fps", 24)),
            filename_prefix=opts.get("prefix", "ltx2_mf"),
            second_pass=second_pass, seed=seed,
            speech_text=speech_text, speech_voice=speech_voice,
            speech_voice_name=speech_voice_name, audio_file=audio_file,
            include_audio=include_audio)
    elif cmd == "last_frame":
        wf = ltx23.extract_last_frame(
            video_path=opts.get("video_path", ""),
            filename_prefix=opts.get("prefix", "last_frame"))
    else:
        print(f"Unknown command: {cmd}\n{__doc__}"); sys.exit(1)

    if dump_only:
        print(json.dumps(wf, indent=2))
        return

    notify = opts.get('notify_target') or __import__('os').environ.get('OPENCLAW_NOTIFY_TARGET')
    if notify:
        globals()['NOTIFY_TARGET'] = notify

    # Pass caption template and original prompt (used to include prompt snippet in caption)
    caption_template = opts.get('caption_template') or None
    user_prompt = opts.get('prompt') or None
    _submit_and_wait(wf, output_dir, timeout, notify=notify, caption_template=caption_template, user_prompt=user_prompt)


if __name__ == "__main__":
    main()
