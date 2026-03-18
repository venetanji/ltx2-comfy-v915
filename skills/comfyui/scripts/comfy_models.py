#!/usr/bin/env python3
"""
comfy_models.py - Check and download missing ComfyUI models.

Usage:
  # Check what's missing (no download)
  python skills/comfyui/scripts/comfy_models.py check --workflow path/to/workflow.json
  python skills/comfyui/scripts/comfy_models.py check --url https://pastebin.com/raw/XYZ

  # Download missing models
  python skills/comfyui/scripts/comfy_models.py download --workflow path/to/workflow.json
  python skills/comfyui/scripts/comfy_models.py download --url https://pastebin.com/raw/XYZ

  # List all models in a workflow (present + missing)
  python skills/comfyui/scripts/comfy_models.py list --workflow path/to/workflow.json

  # Download specific model by URL + directory
  python skills/comfyui/scripts/comfy_models.py get --url https://huggingface.co/.../model.safetensors --dir checkpoints

Environment:
  COMFYUI_MODELS_DIR  Override default models dir (default: ~/Documents/ComfyUI/models)
  HF_TOKEN            HuggingFace token for gated models
"""

import argparse
import json
import os
import sys
import urllib.request
import urllib.error
from pathlib import Path

# â”€â”€ Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
DEFAULT_MODELS_DIR = Path.home() / "Documents" / "ComfyUI" / "models"

def get_models_dir() -> Path:
    d = os.environ.get("COMFYUI_MODELS_DIR")
    return Path(d) if d else DEFAULT_MODELS_DIR


# â”€â”€ Workflow parsing â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def extract_models_from_workflow(data: dict) -> list[dict]:
    """
    Extract model entries from a ComfyUI workflow JSON.
    Looks in node properties.models and subgraph node properties.models.
    Each entry: {name, url, directory, node_type}
    """
    found = []
    seen = set()

    def scan_nodes(nodes):
        for node in nodes:
            props = node.get("properties", {})
            node_type = node.get("type", "unknown")
            for m in props.get("models", []):
                key = (m.get("name"), m.get("directory"))
                if key not in seen and m.get("url"):
                    seen.add(key)
                    found.append({
                        "name": m["name"],
                        "url": m["url"],
                        "directory": m["directory"],
                        "node_type": node_type,
                    })

    # Top-level nodes
    scan_nodes(data.get("nodes", []))

    # Subgraph nodes (definitions.subgraphs[].nodes)
    for sg in data.get("definitions", {}).get("subgraphs", []):
        scan_nodes(sg.get("nodes", []))

    return found


def load_workflow(workflow_path: str | None, url: str | None) -> dict:
    if url:
        print(f"Fetching workflow from {url} ...")
        req = urllib.request.Request(url, headers={"User-Agent": "comfy_models/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
        return json.loads(raw)
    elif workflow_path:
        with open(workflow_path, encoding="utf-8") as f:
            return json.load(f)
    else:
        raise ValueError("Provide --workflow or --url")


# â”€â”€ Download â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def download_file(url: str, dest: Path, hf_token: str | None = None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    headers = {"User-Agent": "comfy_models/1.0"}
    if hf_token and "huggingface.co" in url:
        headers["Authorization"] = f"Bearer {hf_token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            total = int(response.headers.get("Content-Length", 0))
            downloaded = 0
            chunk = 1024 * 1024  # 1 MB
            with open(tmp, "wb") as f:
                while True:
                    block = response.read(chunk)
                    if not block:
                        break
                    f.write(block)
                    downloaded += len(block)
                    if total:
                        pct = downloaded / total * 100
                        mb = downloaded / 1024 / 1024
                        total_mb = total / 1024 / 1024
                        print(f"\r  {mb:.1f}/{total_mb:.1f} MB ({pct:.1f}%)", end="", flush=True)
        tmp.rename(dest)
        print(f"\r  âœ“ {dest.name} ({downloaded/1024/1024:.1f} MB)")
    except Exception as e:
        if tmp.exists():
            tmp.unlink()
        raise RuntimeError(f"Download failed: {e}") from e


# â”€â”€ Commands â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def cmd_list(args):
    data = load_workflow(args.workflow, getattr(args, "url", None))
    models = extract_models_from_workflow(data)
    models_dir = get_models_dir()

    if not models:
        print("No model entries found in workflow.")
        return

    print(f"\nModels dir: {models_dir}\n")
    print(f"{'Status':<10} {'Directory':<25} {'Name'}")
    print("-" * 80)
    for m in models:
        dest = models_dir / m["directory"] / m["name"]
        status = "[OK]     " if dest.exists() else "[MISSING]"
        print(f"{status:<10} {m['directory']:<25} {m['name']}")
    print()


def cmd_check(args):
    data = load_workflow(args.workflow, getattr(args, "url", None))
    models = extract_models_from_workflow(data)
    models_dir = get_models_dir()

    missing = [m for m in models if not (models_dir / m["directory"] / m["name"]).exists()]

    if not missing:
        print("âœ“ All models present.")
        return 0

    print(f"\nâœ— {len(missing)} missing model(s):\n")
    for m in missing:
        print(f"  [{m['directory']}] {m['name']}")
        print(f"    {m['url']}")
    print(f"\nRun with 'download' to fetch them.\n")
    return 1


def cmd_download(args):
    data = load_workflow(args.workflow, getattr(args, "url", None))
    models = extract_models_from_workflow(data)
    models_dir = get_models_dir()
    hf_token = os.environ.get("HF_TOKEN")

    missing = [m for m in models if not (models_dir / m["directory"] / m["name"]).exists()]

    if not missing:
        print("âœ“ All models already present â€” nothing to download.")
        return

    print(f"\nDownloading {len(missing)} missing model(s) to {models_dir} ...\n")
    errors = []
    for m in missing:
        dest = models_dir / m["directory"] / m["name"]
        print(f"â†’ [{m['directory']}] {m['name']}")
        try:
            download_file(m["url"], dest, hf_token=hf_token)
        except Exception as e:
            print(f"  âœ— ERROR: {e}")
            errors.append((m["name"], str(e)))

    print()
    if errors:
        print(f"âœ— {len(errors)} download(s) failed:")
        for name, err in errors:
            print(f"  {name}: {err}")
        sys.exit(1)
    else:
        print(f"âœ“ All {len(missing)} model(s) downloaded.")


def cmd_get(args):
    """Download a single model by URL + directory."""
    models_dir = get_models_dir()
    name = args.name or Path(args.url.split("?")[0]).name
    dest = models_dir / args.dir / name
    hf_token = os.environ.get("HF_TOKEN")

    if dest.exists():
        print(f"âœ“ Already exists: {dest}")
        return

    print(f"â†’ Downloading {name} to {dest.parent} ...")
    download_file(args.url, dest, hf_token=hf_token)


# â”€â”€ CLI â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def main():
    parser = argparse.ArgumentParser(
        description="Check and download missing ComfyUI models from workflow JSON."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_workflow_args(p):
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--workflow", help="Path to workflow JSON file")
        g.add_argument("--url", help="URL of workflow JSON")

    p_list = sub.add_parser("list", help="List all models in workflow (present + missing)")
    add_workflow_args(p_list)
    p_list.set_defaults(func=cmd_list)

    p_check = sub.add_parser("check", help="Report missing models (no download)")
    add_workflow_args(p_check)
    p_check.set_defaults(func=cmd_check)

    p_dl = sub.add_parser("download", help="Download missing models")
    add_workflow_args(p_dl)
    p_dl.set_defaults(func=cmd_download)

    p_get = sub.add_parser("get", help="Download a single model by URL")
    p_get.add_argument("--url", required=True, help="Direct download URL")
    p_get.add_argument("--dir", required=True, help="Target subdirectory under models/")
    p_get.add_argument("--name", help="Override filename (default: derived from URL)")
    p_get.set_defaults(func=cmd_get)

    args = parser.parse_args()
    result = args.func(args)
    if isinstance(result, int):
        sys.exit(result)


if __name__ == "__main__":
    main()
