#!/usr/bin/env python3
"""fetch_character.py

Fetch a character YAML and reference images from the GitHub repo and HuggingFace dataset
and save them under story/characters/<code>/

Usage:
  python fetch_character.py --code 6166r [--repo <git_url>] [--hf-dataset <url>] [--out-dir story]

If mcporter is available and --use-mcp is passed, will call MCP as a fallback.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys
from pathlib import Path
import urllib.request
import yaml

ROOT = Path.cwd()


def run(cmd, check=True):
    print('RUN:', ' '.join(cmd))
    return subprocess.run(cmd, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def ensure_repo(repo_url: str, repo_dir: Path):
    if repo_dir.exists():
        try:
            run(['git', '-C', str(repo_dir), 'pull'])
        except Exception:
            print('Failed to pull repo, continuing with existing copy')
    else:
        run(['git', 'clone', repo_url, str(repo_dir)])


def download_hf_image(hf_base_url: str, image_name: str, dest: Path):
    # try raw link heuristics; users can override with full url
    dest.parent.mkdir(parents=True, exist_ok=True)
    urls_to_try = [f"{hf_base_url}/resolve/main/{image_name}", f"{hf_base_url}/resolve/main/{image_name}.png", image_name]
    for u in urls_to_try:
        try:
            print('Trying', u)
            urllib.request.urlretrieve(u, str(dest))
            return dest
        except Exception as e:
            # try next
            last_err = e
    raise last_err


def fetch_character(code: str, repo_url: str, hf_dataset: str, out_dir: Path, use_mcp: bool=False):
    repo_dir = out_dir / 'repo'
    chars_dir = out_dir / 'characters'
    ensure_repo(repo_url, repo_dir)

    # find YAML in repo: characters/<code>.yaml or characters/<code>/index.yaml
    candidate = None
    for p in repo_dir.rglob('*.yaml'):
        name = p.name.lower()
        if code.lower() in name:
            candidate = p
            break

    if not candidate:
        print('Character YAML not found in repo; aborting')
        if use_mcp:
            print('Attempting MCP fallback...')
        else:
            return None

    char_out = chars_dir / code
    char_out.mkdir(parents=True, exist_ok=True)
    yaml_dest = char_out / 'CHARACTER.yaml'
    with open(candidate, 'rb') as src, open(yaml_dest, 'wb') as dst:
        dst.write(src.read())

    # parse YAML to find refs (best-effort)
    refs = []
    try:
        data = yaml.safe_load(open(yaml_dest, 'r', encoding='utf-8'))
        # common keys: ref_image, image, images, avatar, ref
        for k in ('ref_image','image','avatar'):
            v = data.get(k) if isinstance(data, dict) else None
            if v:
                refs.append(v)
        # some YAML use images: [..]
        if isinstance(data, dict) and 'images' in data and isinstance(data['images'], list):
            refs.extend(data['images'])
    except Exception:
        pass

    downloaded = []
    refs_dir = char_out / 'refs'
    refs_dir.mkdir(parents=True, exist_ok=True)
    for r in refs:
        # if r looks like a URL, download directly
        if isinstance(r, str) and r.startswith('http'):
            name = os.path.basename(r.split('?')[0])
            dest = refs_dir / name
            try:
                urllib.request.urlretrieve(r, str(dest))
                downloaded.append(str(dest))
            except Exception as e:
                print('Failed to download', r, '->', e)
        else:
            # try to download from HF dataset heuristics
            try:
                imgname = str(r)
                dest = refs_dir / imgname
                download_hf_image(hf_dataset, imgname, dest)
                downloaded.append(str(dest))
            except Exception as e:
                print('HF download failed for', r, e)

    # if no refs found, attempt to find images in repo path (same folder)
    if not downloaded:
        for p in candidate.parent.glob('*'):
            if p.suffix.lower() in ('.png','.jpg','.jpeg'):
                dst = refs_dir / p.name
                if not dst.exists():
                    dst.write_bytes(p.read_bytes())
                downloaded.append(str(dst))

    result = {
        'code': code,
        'yaml': str(yaml_dest),
        'refs': downloaded,
        'repo_path': str(repo_dir)
    }

    # optional MCP fallback
    if use_mcp and (shutil.which('mcporter') or shutil.which('mcporter.ps1')):
        try:
            cmd = ['mcporter','call', f"https://polyu-storyworld.tail9683c.ts.net/mcp.get_character_context", f"code={code}", '--output','json']
            r = run(cmd)
            print('MCP output:', r.stdout)
        except Exception as e:
            print('MCP fallback failed', e)

    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--code', required=True)
    p.add_argument('--repo', default='https://github.com/venetanji/polyu-storyworld')
    p.add_argument('--hf-dataset', default='https://huggingface.co/datasets/venetanji/polyu-storyworld-characters')
    p.add_argument('--out-dir', default='story')
    p.add_argument('--use-mcp', action='store_true')
    args = p.parse_args()
    out = fetch_character(args.code, args.repo, args.hf_dataset, Path(args.out_dir), use_mcp=args.use_mcp)
    if out is None:
        print('Failed to fetch character')
        sys.exit(2)
    print(json.dumps(out, indent=2))
