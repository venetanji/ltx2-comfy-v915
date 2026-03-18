#!/usr/bin/env python3
"""Smoke test: build workflows using inbound file and Athena refs, with upload_inputs flag.
This script runs comfy_graph.py in 'dump' mode so it doesn't contact a ComfyUI server.
It saves generated workflow JSONs and a short log to outputs/smoke_tests/.
"""
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / 'outputs' / 'smoke_tests'
OUT.mkdir(parents=True, exist_ok=True)

cases = [
    {
        'name': 'angles_athena',
        'cmd': [ 'python', str(BASE / 'skills' / 'comfyui' / 'scripts' / 'comfy_graph.py'), 'dump', 'angles', '--image', str(BASE / 'agents' / 'athena-6166r' / '6166r_ref.png'), '--prompts', 'front\nside\nrear', '--upload-inputs' ]
    },
    {
        'name': 'i2i_athena',
        'cmd': [ 'python', str(BASE / 'skills' / 'comfyui' / 'scripts' / 'comfy_graph.py'), 'dump', 'i2i', '--image', str(BASE / 'agents' / 'athena-6166r' / '6166r_ref.png'), '--prompt', 'A stylized portrait', '--upload-inputs' ]
    }
]

log = []
for c in cases:
    name = c['name']
    try:
        print('Running', name)
        p = subprocess.run(c['cmd'], capture_output=True, text=True, check=False)
        (OUT / f'{name}.json').write_text(p.stdout)
        (OUT / f'{name}.log').write_text(p.stderr)
        log.append((name, p.returncode))
    except Exception as e:
        (OUT / f'{name}.error').write_text(str(e))
        log.append((name, 'exception'))

# summary
(OUT / 'summary.txt').write_text('\n'.join([f"{n}: {r}" for n,r in log]))
print('Smoke tests completed. Outputs in', OUT)
