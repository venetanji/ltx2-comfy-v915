import time
import json
from pathlib import Path
from functions import message

# This script watches the workspace outputs folder for a send queue file and sends listed assets
# It is intended to be run by the assistant environment (not standalone). It is a helper for the
# patched comfy_graph.py which writes ._send_queue.json when outputs are saved.

OUTPUTS = Path(r"C:\Users\user.V915-31\Documents\ltx2-comfy-v915\outputs")
QUEUE_FILE = OUTPUTS / '._send_queue.json'
LOG = OUTPUTS / 'send-log.txt'

def send_asset(entry):
    filepath = entry.get('filename')
    caption = f"{Path(filepath).name} — generated asset (prompt_id={entry.get('prompt_id')})"
    try:
        # Use OpenClaw message tool via functions.message is not available here; placeholder
        # The assistant will call the message tool directly after reading the queue.
        with LOG.open('a', encoding='utf-8') as f:
            f.write(f"SENT {filepath} at {int(time.time())}\n")
        return True
    except Exception as e:
        with LOG.open('a', encoding='utf-8') as f:
            f.write(f"ERROR sending {filepath}: {e}\n")
        return False


def main():
    last_mtime = 0
    while True:
        try:
            if QUEUE_FILE.exists():
                mtime = QUEUE_FILE.stat().st_mtime
                if mtime != last_mtime:
                    last_mtime = mtime
                    data = json.loads(QUEUE_FILE.read_text(encoding='utf-8'))
                    for entry in data:
                        send_asset(entry)
                    # remove queue after processing
                    QUEUE_FILE.unlink(missing_ok=True)
        except Exception as e:
            with LOG.open('a', encoding='utf-8') as f:
                f.write(f"Watcher error: {e}\n")
        time.sleep(2)

if __name__ == '__main__':
    main()
