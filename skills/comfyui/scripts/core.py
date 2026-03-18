"""Core helpers for comfy_graph refactor: WorkflowGraph, NodeRef, upload helpers,
submit/wait and safe asset saving (copies into OpenClaw outbound and optionally calls CLI).
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
import urllib.parse
import shutil
import subprocess
import shlex
from pathlib import Path

BASE = os.environ.get("COMFY_URL", "http://localhost:8188").rstrip("/")

# Default notify target read from environment; callers may override by passing notify to functions.
NOTIFY_TARGET = os.environ.get("OPENCLAW_NOTIFY_TARGET")

VOICE_LIBRARY = {
    "gio": {"file": "voice.mp3", "reference_text": "", "x_vector_only": True},
}


class NodeRef:
    def __init__(self, node_id: str, output_idx: int = 0):
        self.node_id = node_id
        self.output_idx = output_idx

    def __getitem__(self, idx: int) -> "NodeRef":
        return NodeRef(self.node_id, idx)

    def as_link(self) -> list:
        return [self.node_id, self.output_idx]

    def __repr__(self):
        return f"NodeRef({self.node_id!r}, {self.output_idx})"


class WorkflowGraph:
    def __init__(self):
        self._nodes: dict[str, dict] = {}
        self._counter = 0

    def node(self, class_type: str, **inputs) -> NodeRef:
        node_id = str(self._counter)
        self._counter += 1
        processed = {}
        for k, v in inputs.items():
            if isinstance(v, NodeRef):
                processed[k] = v.as_link()
            else:
                processed[k] = v
        self._nodes[node_id] = {"class_type": class_type, "inputs": processed}
        return NodeRef(node_id)

    def to_dict(self) -> dict:
        return dict(self._nodes)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)


def upload_image(local_path: str) -> str:
    path = Path(local_path)
    data = path.read_bytes()
    ext = path.suffix.lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png" if ext == ".png" else "application/octet-stream"
    boundary = "----ComfyUploadBoundary"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode() + data + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="type"\r\n\r\ninput\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="subfolder"\r\n\r\n\r\n'
        f"--{boundary}--\r\n"
    ).encode()
    req = urllib.request.Request(
        f"{BASE}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    return resp["name"]


def upload_if_local(path: str, upload_flag: bool = True) -> str:
    if not path:
        return path
    try:
        p = Path(path)
        if p.exists() and upload_flag:
            try:
                server = upload_image(str(p))
                print(f"Uploaded local image {p} -> {server}")
                return server
            except Exception as e:
                print(f"[WARN] Failed to upload image {p}: {e}", file=sys.stderr)
                return path
    except Exception:
        pass
    return path


def _submit_and_wait(workflow: dict, output_dir: Path, timeout: int = 600, notify: str | None = None, caption_template: str | None = None, user_prompt: str | None = None):
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(f"{BASE}/prompt", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        result = json.load(r)
    if result.get("node_errors"):
        print(f"[WARN] Node errors: {result['node_errors']}", file=sys.stderr)
    prompt_id = result["prompt_id"]
    print(f"prompt_id: {prompt_id}", file=sys.stderr)

    deadline = time.time() + timeout
    last_st = None
    while time.time() < deadline:
        with urllib.request.urlopen(f"{BASE}/history/{prompt_id}", timeout=15) as r:
            hist = json.load(r)
        entry = hist.get(prompt_id)
        if entry:
            outputs = entry.get("outputs", {})
            st = (entry.get("status") or {}).get("status_str") or (entry.get("status") or {}).get("status")
            if st and st != last_st:
                print(f"[{st}]", file=sys.stderr)
                last_st = st
            if outputs:
                _save_assets(entry, output_dir, notify=notify)
                return
            if (entry.get("status") or {}).get("completed") is True or st == "error":
                print("Completed with no outputs.", file=sys.stderr)
                return
        time.sleep(2)
    raise TimeoutError(f"Timed out after {timeout}s")


def _save_assets(entry: dict, output_dir: Path, notify: str | None = None, caption_template: str | None = None, user_prompt: str | None = None):
    output_dir.mkdir(parents=True, exist_ok=True)
    seen = set()
    send_queue = []
    saved_files = []
    for nout in entry.get("outputs", {}).values():
        for v in nout.values():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and "filename" in item:
                        fname = item["filename"]
                        if fname in seen:
                            continue
                        seen.add(fname)
                        sf = item.get("subfolder", "") or ""
                        tp = item.get("type", "output")
                        norm_fname = fname.replace("\\", "/")
                        q_fname = urllib.parse.quote(norm_fname, safe='/')
                        q_sub = urllib.parse.quote(sf)
                        url = f"{BASE}/view?filename={q_fname}&subfolder={q_sub}&type={tp}&_={int(time.time()*1000)}"
                        print(f"asset_url: {url}")
                        dest = output_dir / Path(fname).name
                        try:
                            with urllib.request.urlopen(url, timeout=120) as r:
                                dest.write_bytes(r.read())
                        except Exception as e:
                            print(f"[WARN] Failed to download asset {fname} from {url}: {e}", file=sys.stderr)
                            continue
                        print(f"saved: {dest}")
                        saved_files.append(dest)
                        send_queue.append({
                            "filename": str(dest.resolve()),
                            "prompt_id": entry.get("prompt_id"),
                            "workflow": entry.get("workflow_name", ""),
                            "timestamp": int(time.time())
                        })
    if send_queue:
        try:
            queue_file = output_dir / "._send_queue.json"
            existing = []
            if queue_file.exists():
                try:
                    with queue_file.open("r", encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    existing = []
            existing.extend(send_queue)
            tmp = output_dir / f"._send_queue_{int(time.time())}.tmp"
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(existing, f)
            tmp.replace(queue_file)
            print(f"queued {len(send_queue)} asset(s) for sending: {queue_file}")
        except Exception as e:
            print(f"[WARN] Failed to write send queue: {e}", file=sys.stderr)

    try:
        home = Path.home()
        outbound_dir = home / ".openclaw" / "media" / "outbound"
        outbound_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        outbound_dir = Path.home() / ".openclaw" / "media" / "outbound"
        print(f"[WARN] Failed to ensure outbound dir {outbound_dir} (fallback used): {e}", file=sys.stderr)

    for p in saved_files:
        try:
            dst = outbound_dir / p.name
            try:
                need_copy = (not dst.exists()) or (dst.stat().st_size != p.stat().st_size)
            except Exception:
                need_copy = True
            if need_copy:
                try:
                    dst.write_bytes(p.read_bytes())
                except Exception as e:
                    print(f"[WARN] Failed to copy {p} -> {dst}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] Failed preparing outbound copy for {p}: {e}", file=sys.stderr)

    if notify:
        openclaw_bin = shutil.which("openclaw")
        if not openclaw_bin:
            print("[WARN] 'openclaw' not found on PATH; cannot auto-send.", file=sys.stderr)
            return
        outbound_log = outbound_dir / "send-log-cli.txt"
        main_logf = output_dir / "send-log.txt"
        for p in saved_files:
            try:
                dst = outbound_dir / p.name
                stable_count = 0
                last_size = -1
                for _ in range(10):
                    try:
                        cur_size = dst.stat().st_size
                    except Exception:
                        cur_size = -1
                    if cur_size == last_size and cur_size > 0:
                        stable_count += 1
                    else:
                        stable_count = 0
                    if stable_count >= 2:
                        break
                    last_size = cur_size
                    time.sleep(0.5)
                # Build a concise, ASCII-safe caption with useful metadata
                # Build caption based on the template; default includes prompt snippet
                workflow_name = entry.get('workflow_name') or ''
                prompt_id = entry.get('prompt_id') or ''
                timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
                prompt_snippet = (user_prompt or '')[:100].replace('\n', ' ') if user_prompt else ''

                if caption_template:
                    # supported placeholders: {filename}, {workflow}, {id}, {ts}, {prompt}
                    caption = caption_template.format(filename=p.name, workflow=workflow_name, id=prompt_id, ts=timestamp, prompt=prompt_snippet)
                else:
                    parts = [p.name]
                    if workflow_name:
                        parts.append(f"workflow={workflow_name}")
                    if prompt_id:
                        parts.append(f"id={prompt_id}")
                    if prompt_snippet:
                        parts.append(f"prompt={prompt_snippet}")
                    parts.append(timestamp)
                    caption = " | ".join(parts)

                # Sanitize to ASCII to avoid weird characters in the CLI call
                caption = caption.encode('ascii', 'replace').decode('ascii')

                cmd = [openclaw_bin, "message", "send", "--channel", "telegram", "--target", str(notify), "--message", caption, "--media", str(dst.resolve())]
                cmd_line = shlex.join(cmd)
                print("Running:", cmd_line)
                proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
                # log CLI stdout/stderr and exit code to both logs (with full cmd line)
                try:
                    with main_logf.open("a", encoding="utf-8") as lf:
                        lf.write(f"[{time.ctime()}] CMD: {cmd_line}\n")
                        lf.write(f"exit={proc.returncode}\n")
                        if proc.stdout:
                            lf.write("STDOUT:\n" + proc.stdout + "\n")
                        if proc.stderr:
                            lf.write("STDERR:\n" + proc.stderr + "\n")
                except Exception as e:
                    print(f"[WARN] Failed to write main send-log: {e}", file=sys.stderr)
                try:
                    with outbound_log.open("a", encoding="utf-8") as of:
                        of.write(f"[{time.ctime()}] CMD: {cmd_line}\n")
                        of.write(f"exit={proc.returncode}\n")
                        if proc.stdout:
                            of.write("STDOUT:\n" + proc.stdout + "\n")
                        if proc.stderr:
                            of.write("STDERR:\n" + proc.stderr + "\n")
                except Exception as e:
                    print(f"[WARN] Failed to write outbound send-log: {e}", file=sys.stderr)
                if proc.returncode != 0 and "LocalMediaAccessError" in (proc.stderr or ""):
                    time.sleep(0.5)
                    proc = subprocess.run(cmd, check=False, capture_output=True, text=True)
                    try:
                        with main_logf.open("a", encoding="utf-8") as lf:
                            lf.write(f"[RETRY] exit={proc.returncode}\n")
                            if proc.stdout:
                                lf.write("STDOUT:\n" + proc.stdout + "\n")
                            if proc.stderr:
                                lf.write("STDERR:\n" + proc.stderr + "\n")
                    except Exception:
                        pass
            except Exception as e:
                print(f"[WARN] Failed to send asset {p}: {e}", file=sys.stderr)


print("core module loaded")
