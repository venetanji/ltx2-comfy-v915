# Copilot instructions for this workspace

This workspace vendors **ComfyUI Core** under `ComfyUI/` (Python). Most “real” code lives there; scripts at the repo root are wrappers.

## Big picture (how requests flow)
- `ComfyUI/main.py` is the main entrypoint: parses CLI args, applies model/input/output/user paths, loads custom nodes, then runs the server + prompt execution loop.
- `ComfyUI/server.py` (`aiohttp`) hosts the Web UI + HTTP API and a websocket at `/ws` used for push updates.
- `ComfyUI/execution.py` executes a graph prompt: resolves node inputs, runs nodes, and manages intermediate caching (`CacheType` / `CacheSet`).
- `ComfyUI/nodes.py` defines built-in node classes and the global registries (`NODE_CLASS_MAPPINGS`, `NODE_DISPLAY_NAME_MAPPINGS`).

## Common developer workflows
- Run locally (from `ComfyUI/`): `python main.py` (see args in `ComfyUI/comfy/cli_args.py`, default `--listen 127.0.0.1 --port 8188`).
- Install deps: `pip install -r ComfyUI/requirements.txt`.
- Run tests: `pytest` (configured by `ComfyUI/pytest.ini`; tests live in `ComfyUI/tests/` and `ComfyUI/tests-unit/`).
  - Inference tests: `pytest ComfyUI/tests/inference` (see `ComfyUI/tests/README.md` for extra deps).
  - Unit tests: `pip install -r ComfyUI/tests-unit/requirements.txt` then `pytest ComfyUI/tests-unit/`.

## Adding or modifying nodes (project conventions)
- Built-in nodes: implement a class in `ComfyUI/nodes.py` (often subclassing `ComfyNodeABC`) and register it in `NODE_CLASS_MAPPINGS` (and optionally `NODE_DISPLAY_NAME_MAPPINGS`).
  - Follow the existing `INPUT_TYPES` / `RETURN_TYPES` / `FUNCTION` / `CATEGORY` pattern (example: `CLIPTextEncode` near the top of `ComfyUI/nodes.py`).
- Custom nodes (external): loaded from `custom_nodes/` folders resolved via `folder_paths.get_folder_paths("custom_nodes")`.
  - V1 style: a module must export `NODE_CLASS_MAPPINGS` (and optionally `NODE_DISPLAY_NAME_MAPPINGS`).
  - V3 style: a module can export a callable `comfy_entrypoint()` returning a `ComfyExtension` that yields node classes via `get_node_list()`.
  - Optional conventions used by core:
    - `prestartup_script.py` is executed early (see `execute_prestartup_script()` in `ComfyUI/main.py`).
    - `WEB_DIRECTORY` or `pyproject.toml` metadata can auto-register extension web assets (`ComfyUI/nodes.py`).
    - `locales/<lang>/main.json` (+ `commands.json`, `settings.json`, `nodeDefs.json`) are merged for i18n (`ComfyUI/app/custom_node_manager.py`).

## Paths, storage, and safety
- Do not hardcode `models/`, `input/`, `output/`, `user/` paths; use `ComfyUI/folder_paths.py` helpers.
- Respect “system user” protection: internal-only user directories are prefixed with `__` and should not be exposed via HTTP (`get_public_user_directory()` vs `get_system_user_directory()`).

## API boundaries
- Routes under `/internal` are for ComfyUI itself and may change without notice (see `ComfyUI/api_server/routes/internal/README.md`).
- When touching server endpoints or websockets, keep behavior consistent with `PromptServer` in `ComfyUI/server.py`.

## Gotchas worth knowing
- Avoid importing `torch` before the point `ComfyUI/main.py` expects it; startup warns if torch is already imported.
- Treat prompt “extra data” secrets as sensitive: `ComfyUI/execution.py` defines `SENSITIVE_EXTRA_DATA_KEYS` (avoid logging these values).
- DB migrations (if editing app DB models): follow `ComfyUI/alembic_db/README.md` (alembic autogenerate flow).
