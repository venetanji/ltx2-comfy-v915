#!/usr/bin/env python3
"""generate_storyboard.py

Create a shot-by-shot storyboard and LTX-2.3 prompts for a short video.
"""
from __future__ import annotations
import argparse, json, os, random, textwrap, time
from pathlib import Path

import urllib.request

OUT_DIR = Path("outputs")

SHOT_TEMPLATE = (
    "{index}. {duration}s — {shot_scale} — {camera}",
)

CAMERA_CHOICES = [
    'static', 'slow dolly in', 'slow dolly out', 'tracking shot (follow)', 'handheld tracking',
    'overhead crane', 'push in', 'push out', 'whip pan'
]

SHOT_SCALES = ['wide', 'medium', 'close-up', 'extreme close-up', 'establishing']

TRANSITIONS = ['cut', 'dissolve', 'match-on-action', 'whip pan', 'fade to black']


def load_hf_dataset_list(hf_dataset_url: str) -> list:
    """Try to fetch dataset metadata (simple approach: list files under the dataset url).
    Expects HF dataset raw listing URL or will try to query dataset repo HTML and find image links.
    This is a lightweight heuristic — for reliability you can pass a local manifest JSON.
    """
    try:
        if hf_dataset_url.endswith('/'):
            hf_dataset_url = hf_dataset_url[:-1]
        # try the dataset files API raw listing
        raw_url = hf_dataset_url + '/resolve/main/README.md'
        with urllib.request.urlopen(raw_url, timeout=15) as r:
            txt = r.read().decode('utf-8', errors='ignore')
        # naive extraction: find image filenames referenced in README
        imgs = []
        for line in txt.splitlines():
            if 'http' in line and ('.png' in line or '.jpg' in line or '.jpeg' in line):
                part = line.split('(')[-1].split(')')[0]
                imgs.append(part)
        return imgs
    except Exception:
        return []


def choose_characters(repo_url: str, hf_images: list, num_chars: int=3, seed: int|None=None) -> list:
    rnd = random.Random(seed)
    # heuristic: image filenames often include character ids — group by prefix
    if not hf_images:
        # fallback: fabricate character placeholders
        return [f"char_{i+1}" for i in range(num_chars)]
    groups = {}
    for url in hf_images:
        name = os.path.basename(url)
        key = name.split('_')[0]
        groups.setdefault(key, []).append(url)
    keys = list(groups.keys())
    rnd.shuffle(keys)
    chosen = keys[:num_chars]
    chars = []
    for k in chosen:
        chars.append({'id': k, 'refs': groups.get(k, [])})
    return chars


def make_shot_prompt(characters, style_ref, shot_idx, duration, scale, camera, action_notes):
    # Build a long, descriptive LTX-2.3 friendly prompt
    # characters: list of dicts {id, refs}
    primary = characters[0]
    others = characters[1:]
    char_desc = f"{primary['id']} (distinctive features from reference: see style image)"
    if others:
        others_desc = ", ".join([c['id'] for c in others])
        char_desc += f", accompanied by {others_desc}"

    scene = (
        f"{char_desc} {action_notes}. The scene is shot in a {scale} frame, "
        f"lighting: soft golden hour, warm rim light, cinematic color grading. "
        f"Camera: {camera}, lens: 35mm cinematic, shallow depth of field when close-up, "
        f"motion: {camera}. Audio: ambient ocean waves, distant seagulls, subtle surf whoosh."
    )
    # append style reference hint
    scene += f" Style reference: {style_ref} — consistent color palette and character rendering across the video."
    # make it one flowing paragraph
    return ' '.join(scene.split())


def build_storyboard(args):
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    duration = args.duration
    shots = args.shots
    seed = args.seed
    rnd = random.Random(seed)

    # load HF images (best-effort)
    hf_images = load_hf_dataset_list(args.hf_dataset) if args.hf_dataset else []

    characters = choose_characters(args.repo, hf_images, num_chars=min(3, args.max_characters), seed=seed)

    # pick style reference: choose a random ref image from chosen characters
    all_refs = [r for c in characters for r in c.get('refs', [])]
    style_ref = rnd.choice(all_refs) if all_refs else (hf_images[0] if hf_images else 'photorealistic_cinematic')

    shot_len = max(1, duration // shots)
    storyboard = {'duration': duration, 'shots': []}

    for i in range(shots):
        scale = rnd.choice(SHOT_SCALES)
        camera = rnd.choice(CAMERA_CHOICES)
        transition = rnd.choice(TRANSITIONS) if i>0 else 'cut'
        action_notes = rnd.choice([
            'rides a breaking wave, carving in a tight arc, spray flying off the rail',
            'pops up quickly and leans into the wave shoulder, smiling with joy',
            'wipes out briefly then resurfaces, shaking hair, determined',
            'performs a small aerial, landing smoothly with a spray of water',
            'circles back to the lineup, talking to another surfer and gesturing'
        ])
        prompt = make_shot_prompt(characters, style_ref, i+1, shot_len, scale, camera, action_notes)
        shot = {
            'index': i+1,
            'duration': shot_len,
            'scale': scale,
            'camera': camera,
            'transition_from_prev': transition,
            'prompt': prompt,
            'style_ref': style_ref,
            'characters': characters
        }
        storyboard['shots'].append(shot)

    # save outputs
    ts = int(time.time())
    with open(out / f'storyboard_{ts}.json', 'w', encoding='utf-8') as f:
        json.dump(storyboard, f, indent=2)
    # human readable
    with open(out / f'storyboard_{ts}.txt', 'w', encoding='utf-8') as f:
        f.write(f"Storyboard — duration: {duration}s — shots: {shots}\n\n")
        for s in storyboard['shots']:
            f.write(f"Shot {s['index']}: {s['duration']}s | {s['scale']} | {s['camera']} | transition: {s['transition_from_prev']}\n")
            f.write(textwrap.fill(s['prompt'], width=100) + '\n\n')

    print('Saved storyboard to', out)
    return storyboard


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--hf-dataset', default='https://huggingface.co/datasets/venetanji/polyu-storyworld-characters')
    p.add_argument('--repo', default='https://github.com/venetanji/polyu-storyworld')
    p.add_argument('--mcp', default='https://github.com/venetanji/storyworld-mcp')
    p.add_argument('--duration', type=int, default=60)
    p.add_argument('--shots', type=int, default=12)
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--out-dir', default='outputs/storyboard')
    p.add_argument('--max-characters', type=int, default=3)
    args = p.parse_args()
    build_storyboard(args)

if __name__ == '__main__':
    main()
