#!/usr/bin/env python3
"""pick_character.py

Pick a random character code from the cloned repo or the local story/characters/ folder.
Useful for sampling characters for scenes. Supports exclusions and seeding for reproducible picks.

Usage:
  python pick_character.py [--repo-dir story/repo] [--local-dir story/characters] [--exclude 1234r,5678x] [--seed 42] [--count 1]

Output: prints JSON list of chosen character codes.
"""
from __future__ import annotations
import argparse, json, random
from pathlib import Path


def find_codes_in_repo(repo_dir: Path) -> list:
    codes = set()
    if not repo_dir.exists():
        return []
    for p in repo_dir.rglob('*.yaml'):
        name = p.stem.lower()
        # heuristic: filename often contains code
        parts = name.split('_')
        for part in parts:
            if len(part) >= 4 and any(c.isdigit() for c in part):
                codes.add(part)
    return sorted(codes)


def find_codes_in_local(local_dir: Path) -> list:
    if not local_dir.exists():
        return []
    codes = [d.name for d in local_dir.iterdir() if d.is_dir()]
    return sorted(codes)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--repo-dir', default='story/repo')
    p.add_argument('--local-dir', default='story/characters')
    p.add_argument('--exclude', default='')
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--count', type=int, default=1)
    args = p.parse_args()

    repo_dir = Path(args.repo_dir)
    local_dir = Path(args.local_dir)

    codes = set()
    codes.update(find_codes_in_repo(repo_dir))
    codes.update(find_codes_in_local(local_dir))
    codes = sorted(codes)

    exclude = [e.strip().lower() for e in args.exclude.split(',') if e.strip()]
    if exclude:
        codes = [c for c in codes if c.lower() not in exclude]

    if not codes:
        print(json.dumps({'error':'no characters found','candidates':[]}))
        return

    rnd = random.Random(args.seed)
    picks = rnd.sample(codes, k=min(args.count, len(codes)))
    print(json.dumps({'picked':picks,'candidates_count':len(codes)}))

if __name__ == '__main__':
    main()
