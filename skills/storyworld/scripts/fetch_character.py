#!/usr/bin/env python3
"""fetch_character.py

Fetch a character YAML and reference images from the GitHub repo and HuggingFace dataset
and save them under story/characters/<code>/

Usage:
  python fetch_character.py --code 6166r [--repo <git_url>] [--hf-dataset <url>] [--out-dir story]

If mcporter is available and --use-mcp is passed, will call MCP as a fallback.
"""
from __future__ import annotations
import argparse, json, os, subprocess, sys, shutil, re
from pathlib import Path
import urllib.request
import urllib.error
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
        try:
            run(['git', 'clone', repo_url, str(repo_dir)])
        except Exception as e:
            print('Git clone failed:', e)


def download_file(url: str, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        print('Downloading', url, '->', dest)
        urllib.request.urlretrieve(url, str(dest))
        return True
    except Exception as e:
        print('Failed to download', url, '->', e)
        return False


def list_hf_character_files(hf_base_url: str, code: str) -> list:
    """List files inside the HF dataset folder for the given character code by scraping the tree listing.
    Expects the dataset web UI at hf_base_url (e.g. https://huggingface.co/datasets/venetanji/polyu-storyworld-characters)
    and looks under /tree/main/<code>/ for file links.
    """
    try:
        tree_url = f"{hf_base_url.rstrip('/')}/tree/main/{code}"
        print('Listing HF path', tree_url)
        with urllib.request.urlopen(tree_url, timeout=15) as r:
            html = r.read().decode('utf-8', errors='ignore')
        # find hrefs that look like '/datasets/venetanji/polyu-storyworld-characters/blob/main/<code>/<filename>'
        pattern = re.compile(r'href=["\'](?P<h>/[^"\']+?/blob/main/' + re.escape(code) + r'/(?P<f>[^"\']+))["\']')
        files = []
        for m in pattern.finditer(html):
            fname = m.group('f')
            files.append(fname)
        # fallback: look for links ending with common extensions inside the code folder
        if not files:
            pattern2 = re.compile(re.escape(f'/datasets/') + r'[^"\']+' + re.escape(f'/{code}/') + r'([^"\']+)')
            for m in pattern2.finditer(html):
                files.append(m.group(1))
        # dedupe
        return sorted(set(files))
    except Exception as e:
        print('HF listing failed:', e)
        return []


def download_hf_character(hf_base_url: str, code: str, dest_dir: Path) -> list:
    files = list_hf_character_files(hf_base_url, code)
    downloaded = []
    for fname in files:
        url = f"{hf_base_url.rstrip('/')}/resolve/main/{code}/{fname}"
        dest = dest_dir / fname
        if download_file(url, dest):
            downloaded.append(str(dest))
    return downloaded


def find_and_copy_repo_refs(repo_dir: Path, code: str, dest_dir: Path) -> list:
    # look for a folder named exactly code under the repo
    candidates = list(repo_dir.rglob(code)) if repo_dir.exists() else []
    copied = []
    for c in candidates:
        if c.is_dir():
            for f in c.iterdir():
                if f.is_file():
                    dst = dest_dir / f.name
                    if not dst.exists():
                        shutil.copy2(f, dst)
                    copied.append(str(dst))
    # also try siblings like refs/, images/ in the same folder as character yaml
    # handled elsewhere by caller if needed
    return copied


def collect_image_strings_from_yaml(data) -> list:
    found = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, str) and (v.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')) or v.startswith('http')):
                found.append(v)
            else:
                found.extend(collect_image_strings_from_yaml(v))
    elif isinstance(data, list):
        for item in data:
            found.extend(collect_image_strings_from_yaml(item))
    return found


def fetch_character(code: str, repo_url: str, hf_dataset: str, out_dir: Path, use_mcp: bool=False):
    repo_dir = out_dir / 'repo'
    chars_dir = out_dir / 'characters'
    ensure_repo(repo_url, repo_dir)

    # find YAML in repo: characters/<code>.yaml or characters/<code>/index.yaml or folder named code with yaml
    candidate = None
    for p in repo_dir.rglob('*.yaml'):
        name = p.name.lower()
        if code.lower() in name:
            candidate = p
            break
    # if not found, try folder named code with yaml files
    if not candidate:
        folder = repo_dir / code
        if folder.exists() and folder.is_dir():
            for p in folder.glob('*.yaml'):
                candidate = p
                break

    if not candidate:
        print('Character YAML not found in repo; aborting fetch from repo')
        if use_mcp:
            print('Attempting MCP fallback...')
        else:
            return None

    char_out = chars_dir / code
    char_out.mkdir(parents=True, exist_ok=True)
    yaml_dest = char_out / 'CHARACTER.yaml'
    with open(candidate, 'rb') as src, open(yaml_dest, 'wb') as dst:
        dst.write(src.read())

    # parse YAML to find refs (recursive search)
    refs = []
    try:
        data = yaml.safe_load(open(yaml_dest, 'r', encoding='utf-8'))
        refs = collect_image_strings_from_yaml(data)
    except Exception as e:
        print('YAML parse failed:', e)

    downloaded = []
    refs_dir = char_out / 'refs'
    refs_dir.mkdir(parents=True, exist_ok=True)

    # if YAML referenced absolute URLs, download them
    for r in refs:
        if isinstance(r, str) and r.startswith('http'):
            name = os.path.basename(r.split('?')[0])
            dest = refs_dir / name
            if download_file(r, dest):
                downloaded.append(str(dest))

    # If no downloaded refs yet, try HF dataset character folder
    if not downloaded:
        print('No direct refs found in YAML or downloads failed; trying HF dataset folder for code', code)
        try:
            hf_downloads = download_hf_character(hf_dataset, code, refs_dir)
            downloaded.extend(hf_downloads)
        except Exception as e:
            print('HF download attempt failed:', e)

    # If still no refs, search repo for folder named code and copy files
    if not downloaded:
        print('No HF refs found; searching repo for folder named', code)
        repo_copied = find_and_copy_repo_refs(repo_dir, code, refs_dir)
        downloaded.extend(repo_copied)

    # As a last resort, look in the YAML's parent directory for images
    if not downloaded:
        for p in candidate.parent.glob('*'):
            if p.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp'):
                dst = refs_dir / p.name
                if not dst.exists():
                    shutil.copy2(p, dst)
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
