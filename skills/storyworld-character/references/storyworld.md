# Character Agent Reference

## Storyworld Infrastructure

- **Character YAML repo:** https://github.com/venetanji/polyu-storyworld
- **Reference images dataset:** https://huggingface.co/datasets/venetanji/polyu-storyworld-characters
- **MCP server (live):** https://polyu-storyworld.tail9683c.ts.net/mcp
- **Character code format:** last 4 digits of student ID, e.g. `6166r`

## MCP Tools (via mcporter)

```bash
# List all characters
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.list_characters" --output json

# Fetch full character context (name, age, personality, appearance, backstory, profile_image)
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.get_character_context" code=<CODE> --output json

# Prepare reference image → copies to ComfyUI output dir, returns {filename, url}
# Must call get_character_context first to download assets
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.prepare_reference_image" code=<CODE> --output json
```

Returns `{"filename": "<CODE>_ref.png", "url": "https://polyu-storyworld.tail9683c.ts.net/outputs/<CODE>_ref.png"}`

## Fallback: GitHub YAML

If MCP is unavailable:
```
https://raw.githubusercontent.com/venetanji/polyu-storyworld/main/characters/<CODE>.yaml
```

## Agent Workspace Layout

```
agents/<code>-<name>/
├── SOUL.md       ← character definition, voice, role, communication instructions
├── IDENTITY.md   ← name, vibe, emoji, avatar URL
└── AGENTS.md     ← startup sequence, sessions_send usage, image generation instructions
```

Create in the workspace root (same dir as the comfyui skill).

## SOUL.md Template

```markdown
# SOUL.md — <Name> (Character <code>)

You are **<Name>**, <one-line description from backstory>.

## Who You Are
- <personality trait 1>
- <personality trait 2>
- <personality trait 3>

## How You Speak
- <voice characteristic 1>
- <voice characteristic 2>

## Your Role in the Storyworld
You are a character in the PolyU Storyworld. You can:
- Engage in narrative roleplay with the human or other characters
- Send/receive messages via `sessions_send`
- Request image/video generation via the storyworld MCP

## Communication
To reach the co-narrator: `sessions_send(label="main", message="...")`
When contacted via `sessions_send`, respond in character.

## Appearance
<from YAML appearance field>

Reference image: `<code>_ref.png`
```

## AGENTS.md Template

```markdown
# AGENTS.md — <Name> Character Session

## On Startup
1. Read `SOUL.md`
2. Read `IDENTITY.md`
3. Check `memory/` for recent context if it exists

## Communication
To reach the co-narrator:
sessions_send(label="main", message="...")

## Image Generation (via MCP)
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.flux2_single_image_edit" \
  reference_image_filename=<code>_ref.png \
  prompt="<scene description>" \
  output_filename_prefix=<name>_<scene>

## Memory
Write session notes to `memory/YYYY-MM-DD.md`.
```

## Spawning the Agent

```javascript
sessions_spawn({
  cwd: "agents/<code>-<name>",
  label: "<code>",
  mode: "run",
  task: "Read SOUL.md, IDENTITY.md, and AGENTS.md, then introduce yourself in character and send your introduction to the main session using sessions_send with label='main'."
})
```

For persistent sessions (Discord threads): add `thread: true, mode: "session"` (requires ACP runtime).

## Co-narrator Routing

When a character agent uses `sessions_send(label="main", ...)`, it arrives as an inter-session message. The co-narrator should:
1. Identify the source character
2. Relay the message to the human with character attribution
3. Route replies back to the character session using `sessions_send(sessionKey=<childSessionKey>, ...)`

## MCP Image Tools Quick Reference

| Tool | Use |
|------|-----|
| `flux2_single_image_edit` | One character + scene |
| `flux2_double_image_edit` | Two characters in same scene |
| `flux2_text_to_image` | No reference (fallback) |
| `flux2_klein_multiple_angles` | 8-angle character sheet |
| `ltx2_singlepass_i2v` | Animate a scene from image |
| `ltx2_singlepass_t2v` | Text-to-video scene |
