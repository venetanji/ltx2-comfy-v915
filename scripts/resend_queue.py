import json, subprocess, pathlib
q=pathlib.Path('outputs/._send_queue.json')
if not q.exists():
    print('no queue'); raise SystemExit
entries=json.loads(q.read_text())
files=[e['filename'] for e in entries if 'athena' in e['filename'] or 'athena_styles' in e['filename']]
# map to outbound copies (user's outbound dir)
outbound=pathlib.Path.home()/'.openclaw'/'media'/'outbound'
files_outbound=[]
for f in files:
    name=pathlib.Path(f).name
    candidate=outbound/name
    if candidate.exists():
        files_outbound.append(candidate)
    else:
        print('missing in outbound, skipping', name)
print('to send from outbound:', files_outbound)
log_out=pathlib.Path('outputs')/'send-log-cli.txt'
with log_out.open('a', encoding='utf-8') as lf:
    for p in files_outbound:
        cmd=['powershell','-NoProfile','-Command',"openclaw message send --channel telegram --target telegram:523910944 --message 'Sending %s' --media '%s'" % (p.name, p.as_posix())]
        lf.write('CMD: ' + ' '.join(cmd) + '\n')
        try:
            proc=subprocess.run(cmd, capture_output=True, text=True, check=False)
            lf.write('exit=' + str(proc.returncode) + '\n')
            lf.write('STDOUT:\n' + proc.stdout + '\n')
            lf.write('STDERR:\n' + proc.stderr + '\n')
            print('sent', p, 'exit', proc.returncode)
        except Exception as e:
            lf.write('EXC: ' + str(e) + '\n')
            print('error sending', p, e)
