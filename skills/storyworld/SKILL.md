---
name: storyworld
description: "Agent entrypoint for the PolyU Storyworld: load character profiles and reference images directly from the GitHub repo and HuggingFace dataset, store them under story/characters/, and provide a simple CLI/API for other skills to call. Replaces mcporter-first workflow with a Git-first workflow."
---

# storyworld skill

This skill is the primary entrypoint for storyworld operations. Its responsibilities:

- Clone or pull the canonical GitHub repository (https://github.com/venetanji/polyu-storyworld) into the workspace (under story/repo/).
- Load character YAML files from the repo and save them into story/characters/<code>/ (CHARACTER.yaml, refs).
- Download reference images from the HuggingFace dataset (https://huggingface.co/datasets/venetanji/polyu-storyworld-characters) into story/characters/<code>/refs/.
- Provide a small CLI script to fetch a character by code, prepare the local workspace, and print a JSON summary with paths to the saved files.
- Offer a fallback to call MCP via mcporter if a special MCP-only asset is requested (dual-mode optional).

Paths used by this skill (workspace-relative):
- story/repo/ — cloned polyu-storyworld Git repo
- story/characters/<code>/ — per-character folder
- story/characters/<code>/CHARACTER.yaml — raw character YAML
- story/characters/<code>/refs/ — downloaded reference images

CLI example:

```
python skills/storyworld/scripts/fetch_character.py --code 6166r --repo https://github.com/venetanji/polyu-storyworld --hf-dataset https://huggingface.co/datasets/venetanji/polyu-storyworld-characters
```

Return format (JSON):
```
{
  "code": "6166r",
  "yaml": "story/characters/6166r/CHARACTER.yaml",
  "refs": ["story/characters/6166r/refs/6166r_ref.png"],
  "repo_path": "story/repo"
}
```

Security & notes:
- By default this skill performs only Git clones and HTTP downloads — no remote code execution.
- If you want MCP fallback, mcporter will be invoked only if the --use-mcp flag is passed and mcporter is present on PATH.


# Implementation files
- skills/storyworld/scripts/fetch_character.py — small, robust Python script used by the skill.
