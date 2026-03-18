---
name: storyworld-character
description: "Spawn and manage character agents for the PolyU Storyworld collaborative storytelling project. Use when: a student provides a character code (e.g. 6166r) and wants their character instantiated as an agent; asked to create/spawn a character session; routing messages between character agents and the co-narrator; generating images or video for a character using their reference image; setting up a new character workspace (SOUL.md, IDENTITY.md, AGENTS.md). NOT for: general image generation (use comfyui skill), GitHub/PR workflows (use github skill)."
---

# Storyworld Character Skill

Instantiate PolyU Storyworld characters as live sub-agent sessions.
Full MCP tool reference, file templates, and routing patterns: `references/storyworld.md`

## Quick Flow

### 1. Fetch Character via MCP

```bash
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.get_character_context" code=CODE --output json
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.prepare_reference_image" code=CODE --output json
```

`prepare_reference_image` requires `get_character_context` to run first (downloads assets).
Returns `{"filename": "CODE_ref.png", "url": "..."}` — use the url as the avatar.

Fallback if MCP unavailable: fetch from `https://raw.githubusercontent.com/venetanji/polyu-storyworld/main/characters/CODE.yaml`

### 2. Create Agent Workspace

Create `agents/CODE-NAME/` with three files using templates from `references/storyworld.md`:
- **SOUL.md** — character voice, backstory, how they speak, reference image filename
- **IDENTITY.md** — name, emoji, avatar URL
- **AGENTS.md** — startup sequence + `sessions_send(label="main", ...)` instructions

### 3. Spawn the Agent

```javascript
sessions_spawn({
  cwd: "agents/CODE-NAME",
  label: "CODE",
  mode: "run",
  task: "Read SOUL.md, IDENTITY.md, and AGENTS.md, then introduce yourself in character and send your introduction to the main session using sessions_send with label='main'."
})
```

### 4. Handle Incoming Messages

Inter-session messages from character agents arrive tagged with `sourceSession`. Identify the character, relay to the human with attribution, route replies back via `sessions_send(sessionKey=CHILD_KEY, ...)`.

## Image Generation for a Character

Once reference image is prepared (CODE_ref.png):

```bash
mcporter call "https://polyu-storyworld.tail9683c.ts.net/mcp.flux2_single_image_edit" \
  reference_image_filename=CODE_ref.png \
  prompt="scene description" \
  output_filename_prefix=name_scene
```

Result includes a public URL — present it directly to the user.
For two characters: `flux2_double_image_edit`. For video: `ltx2_singlepass_i2v` or `ltx2_singlepass_t2v`.

## Co-narrator Identity

The main session is the **co-narrator**: orchestrates the story, spawns character agents, routes messages, generates media. Update `IDENTITY.md` and `USER.md` in workspace root to reflect this role.
