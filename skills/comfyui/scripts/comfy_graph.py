#!/usr/bin/env python3
"""Thin CLI wrapper importing modular workflows from flux2, ltx23 and tts.
Keeps original argument parsing and behavior but delegates to modules.
"""
from __future__ import annotations

import sys
import os
import json
from pathlib import Path
from core import _submit_and_wait
import flux2
import ltx23
import tts


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

    notify_target = opts.get('notify_target') or __import__('os').environ.get('OPENCLAW_NOTIFY_TARGET')
    generation_cmds = {'t2i','i2i','i2i2','angles','t2v','i2v','mf'}
    if cmd in generation_cmds and not notify_target:
        print("ERROR: No notify target set. To receive generated assets via OpenClaw, set the environment variable OPENCLAW_NOTIFY_TARGET or pass --notify-target when calling the CLI.")
        sys.exit(2)

    if cmd == "t2i":
        wf = flux2.flux2_text_to_image(
            prompt=opts.get("prompt", ""),
            width=int(opts.get("width", 1024)), height=int(opts.get("height", 576)),
            steps=int(opts.get("steps", 4)),
            filename_prefix=opts.get("prefix", "flux2_t2i"),
            lora=opts.get("lora"), lora_strength=float(opts.get("lora_strength", 1.0)),
            seed=seed)
    elif cmd == "tts":
        wf = tts.qwen_tts(text=opts.get("text", opts.get("prompt", "")), filename_prefix=opts.get("prefix", "tts"))
        timeout = int(opts.get("timeout", 120))
    elif cmd == "t2v":
        wf = ltx23.ltx23_text_to_video(prompt=opts.get("prompt",""), seconds=int(opts.get("seconds",7)), fps=int(opts.get("fps",24)), filename_prefix=opts.get("prefix","ltx23_t2v"), seed=seed)
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
