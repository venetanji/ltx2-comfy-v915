# ComfyUI skill (refactored)

This skill provides a thin CLI and Python helpers to programmatically create and submit ComfyUI workflows, fetch outputs, and optionally autosend generated media via OpenClaw.

Files
- scripts/core.py — Core helpers: WorkflowGraph, NodeRef, upload helpers, prompt submit/wait, and safe asset saving. Implements copying outputs into ~/.openclaw/media/outbound and calling the openclaw CLI to deliver messages.
- scripts/flux2.py — Flux2-based t2i workflows (text-to-image variants).
- scripts/ltx23.py — LTX-2.3 text-to-video workflow.
- scripts/tts.py — Simple TTS workflow helpers.
- scripts/comfy_graph.py — Lightweight CLI wrapper that delegates to module builders and submits workflows.

Autosend behavior
- Outputs are downloaded from ComfyUI into an outputs/ directory (or --output-dir).
- Files are copied into ~/.openclaw/media/outbound before calling the openclaw CLI — this avoids LocalMediaAccessError caused by OpenClaw refusing attachments outside the allowed media path.
- The script will call the openclaw CLI only if a notify target is set. You can set this via:
  - environment variable: OPENCLAW_NOTIFY_TARGET=telegram:123456789
  - CLI option: --notify-target telegram:123456789

Caption templating
- The CLI supports --caption-template to customize the message caption. Supported placeholders:
  {filename} {workflow} {id} {ts} {prompt}
- Example: --caption-template '{filename} | {prompt:.100} | {ts}'
- If no template is provided, the default caption includes filename, optional workflow/id, prompt snippet, and timestamp.

Usage examples
- t2i with autosend:
  python scripts/comfy_graph.py t2i --prompt "a cat wearing a tutu" --notify-target telegram:523910944

- Provide a custom caption template:
  python scripts/comfy_graph.py t2i --prompt "a cat" --notify-target telegram:523910944 --caption-template "{filename} | {prompt} | {ts}"

Notes & troubleshooting
- If openclaw returns LocalMediaAccessError, the file was not under ~/.openclaw/media/outbound — this skill copies outputs there automatically.
- The openclaw CLI must be available on PATH (shutil.which('openclaw') is used). If missing, autosend is skipped and a warning is logged.
- Caption text is sanitized to ASCII to avoid CLI quoting issues.

Maintenance
- The codebase is modular; add new workflows by creating a module under scripts/ and exposing a function that returns a workflow dict.
- To change defaults (caption template, notify target), set environment variables OPENCLAW_NOTIFY_TARGET and OPENCLAW_CAPTION_TEMPLATE or pass CLI flags.

Changelog (refactor)
- Split original long comfy_graph.py into core/flux2/ltx23/tts + thin CLI.
- Added robust copy-to-outbound step and retries for LocalMediaAccessError.
- Added caption template support and ASCII sanitization.
