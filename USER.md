# USER.md - About Your Human

- **Name:** (instructor, likely Giovanni / venetanji based on GitHub)
- **What to call them:** (TBD — ask)
- **Timezone:** Asia/Shanghai (Hong Kong / PolyU)
- **Notes:** Runs an SD5967 course at PolyU. Students create characters for a collaborative storyworld. The setup involves ComfyUI + OpenClaw on lab machines, a storyworld MCP server, and GitHub for character YAML files.

## Context

- Course project: each student creates a character (YAML + reference image), which gets added to the polyu-storyworld GitHub repo
- Character codes = last 4 digits of student ID (e.g. 6166r)
- MCP server at https://polyu-storyworld.tail9683c.ts.net/mcp provides character context and image generation
- Reference images on HuggingFace: venetanji/polyu-storyworld-characters
- My role: co-narrator alongside the instructor, spawning and orchestrating character agents
- Character agents should know how to use sessions_send to communicate with each other and the co-narrator
