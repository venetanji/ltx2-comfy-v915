# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---
### Default scene workflow (storyworld → ComfyUI → autosend)

- MCP
  - Endpoint: https://polyu-storyworld.tail9683c.ts.net/mcp
  - CLI: mcporter (example: mcporter call "https://.../mcp.get_character_context" code=6166r --output json)
  - Always call get_character_context before prepare_reference_image.

- ComfyUI
  - Endpoint: http://localhost:8188 (COMFYUI_URL)
  - Main scripts:
    - skills/comfyui/scripts/comfy_graph.py — upload, i2v, last_frame, autosend helpers
    - skills/comfyui/scripts/comfy_graph.py i2v --image <NAME> --prompt "<PROMPT>" --seconds 7 --prefix "<prefix>" --output-dir outputs/
  - Recommended default: render 1 i2v shot at 7s to validate style/seed before batching more shots.

- Storyboard generator
  - skills/storyworld_storyboard/scripts/generate_storyboard.py — creates storyboard JSON/TXT (outputs/storyboard_*)

- Autosend / OpenClaw delivery
  - comfy_graph autosend copies outputs into %USERPROFILE%\.openclaw\media\outbound and (optionally) invokes openclaw to send.
  - Configure autosend target via OPENCLAW_NOTIFY_TARGET or pass --notify-target to comfy_graph.
  - Log files: outputs/send-log.txt and outbound/send-log-cli.txt (comfy_graph autosend behavior).

- Quick defaults
  - Default shot duration: 7 seconds
  - Default render: single-shot test before expanding to multi-shot sequences

---

Add whatever helps you do your job. This is your cheat sheet.
