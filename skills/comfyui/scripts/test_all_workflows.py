#!/usr/bin/env python3
"""
test_all_workflows.py — End-to-end test of all comfy_graph builders.

Runs each workflow, records success/failure/OOM, logs results to test_results.json.
For video, tests increasing lengths to find the OOM threshold.

Usage: python test_all_workflows.py [--output-dir ./test_outputs] [--skip-second-pass]
"""
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

# Ensure UTF-8 output on Windows consoles to avoid 'charmap' codec errors
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    # Python <3.7 or environments where reconfigure isn't available will skip
    pass

sys.path.insert(0, str(Path(__file__).parent))
import comfy_graph as cg
from core import _save_assets

BASE = os.environ.get("COMFY_URL", "http://localhost:8188").rstrip("/")
OUTPUT_DIR = Path("test_outputs")
RESULTS_FILE = Path("test_results.json")
SKIP_SECOND_PASS = "--skip-second-pass" in sys.argv
NOTIFY_TARGET = "523910944"

results = []


def log(msg):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def submit(workflow):
    payload = json.dumps({"prompt": workflow}).encode()
    req = urllib.request.Request(f"{BASE}/prompt", data=payload,
                                  headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def poll(prompt_id, timeout=900):
    """Poll until done. Returns (status_str, outputs, elapsed_s, error_msg)."""
    start = time.time()
    deadline = start + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{BASE}/history/{prompt_id}", timeout=15) as r:
                hist = json.load(r)
        except:
            time.sleep(3)
            continue
        entry = hist.get(prompt_id)
        if entry:
            outputs = entry.get("outputs", {})
            status  = entry.get("status", {})
            st      = status.get("status_str") or status.get("status", "")
            msgs    = status.get("messages", [])
            # Detect OOM in messages
            oom_msg = ""
            for m in msgs:
                if isinstance(m, list) and len(m) >= 2:
                    txt = str(m[1])
                    if "out of memory" in txt.lower() or "cuda out" in txt.lower():
                        oom_msg = txt[:200]
            if oom_msg:
                return "oom", {}, round(time.time() - start, 1), oom_msg
            if outputs:
                assets = []
                for nout in outputs.values():
                    for v in nout.values():
                        if isinstance(v, list):
                            for item in v:
                                if isinstance(item, dict) and "filename" in item:
                                    assets.append(item["filename"])
                return "success", assets, round(time.time() - start, 1), ""
            if status.get("completed") is True or st in ("error",):
                err = str(msgs[-1]) if msgs else st
                return "error", {}, round(time.time() - start, 1), err
        time.sleep(3)
    return "timeout", {}, timeout, f"Did not complete in {timeout}s"


def handle_assets(prompt_id, name, prompt):
    try:
        with urllib.request.urlopen(f"{BASE}/history/{prompt_id}", timeout=15) as r:
            hist = json.load(r)
        entry = hist.get(prompt_id, {})
        entry["workflow_name"] = name
        # Use the core helper which already handles downloading, outbound copying, and notifying
        _save_assets(entry, OUTPUT_DIR, notify=NOTIFY_TARGET, user_prompt=prompt)
        
        # Return local paths for internal tracking
        saved = []
        for nout in entry.get("outputs", {}).values():
            for v in nout.values():
                if isinstance(v, list):
                    for item in v:
                        if isinstance(item, dict) and "filename" in item:
                            saved.append(str(OUTPUT_DIR / item["filename"]))
        return saved
    except Exception as e:
        log(f"  Error handling assets: {e}")
        return [f"save_error: {e}"]


def run_test(name, workflow, prompt=None, timeout=900):
    log(f"  Submitting: {name}")
    try:
        result = submit(workflow)
        node_errors = result.get("node_errors", {})
        if node_errors:
            log(f"  Node errors: {node_errors}")
            rec = {"name": name, "status": "node_error", "errors": str(node_errors), "elapsed_s": 0, "assets": []}
            results.append(rec)
            save_results()
            return rec
        pid = result["prompt_id"]
        log(f"  prompt_id: {pid} — waiting (timeout={timeout}s)...")
        status, assets, elapsed, err = poll(pid, timeout=timeout)
        log(f"  → {status} in {elapsed}s  assets={assets}")
        saved = []
        if status == "success":
            saved = handle_assets(pid, name, prompt)
        rec = {"name": name, "status": status, "elapsed_s": elapsed,
               "assets": assets, "saved": saved, "error": err}
    except Exception as e:
        log(f"  EXCEPTION: {e}")
        rec = {"name": name, "status": "exception", "error": str(e), "elapsed_s": 0, "assets": []}
    results.append(rec)
    save_results()
    return rec


def upload_to_input(local_path):
    """Upload a local file to ComfyUI's input directory. Returns the uploaded filename."""
    import email.mime.multipart
    import io
    fname = Path(local_path).name
    data = Path(local_path).read_bytes()
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{fname}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + data + f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"type\"\r\n\r\ninput\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"subfolder\"\r\n\r\n\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{BASE}/upload/image", data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.load(r)
    return resp["name"]


def save_results():
    RESULTS_FILE.write_text(json.dumps(results, indent=2))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    seed = 42  # fixed seed for reproducibility across tests

    log("=" * 60)
    log("ComfyUI workflow test suite")
    log("=" * 60)

    # ── 1. Flux2 text-to-image ────────────────────────────────────
    log("\n[1] Flux2 t2i")
    p1 = "a red apple on a wooden table, photorealistic"
    run_test("flux2_t2i",
             cg.flux2_text_to_image(p1, width=512, height=512, seed=seed),
             prompt=p1)

    # ── 2. Flux2 text-to-image with LoRA ─────────────────────────
    log("\n[2] Flux2 t2i + pixel art LoRA")
    p2 = "a red apple"
    run_test("flux2_t2i_lora",
             cg.flux2_text_to_image(p2,
                                     width=512, height=512, seed=seed,
                                     lora="pixel_art_style_z_image_turbo.safetensors",
                                     lora_strength=1.0,
                                     filename_prefix="test_t2i_lora"),
             prompt=p2)

    # ── 3. Flux2 single-image edit ────────────────────────────────
    # Use the saved output of test 1 as reference (upload to ComfyUI input dir)
    log("\n[3] Flux2 i2i (using t2i output as ref)")
    ref_img = None
    # Find a saved PNG from the t2i test
    t2i_rec = next((r for r in results if r.get("name") == "flux2_t2i" and r.get("status") == "success"), None)
    if t2i_rec:
        saved_pngs = [s for s in t2i_rec.get("saved", []) if s.endswith(".png")]
        if saved_pngs:
            try:
                ref_img = upload_to_input(saved_pngs[0])
                log(f"  Uploaded reference image: {ref_img}")
            except Exception as e:
                log(f"  Upload failed: {e}")
    if ref_img is None:
        log("  No reference image available, skipping i2i test")

    if ref_img:
        log(f"  Using reference image: {ref_img}")
        p3 = "same scene at night"
        run_test("flux2_i2i",
                 cg.flux2_single_image_edit(ref_img, p3,
                                             width=512, height=512, seed=seed,
                                             filename_prefix="test_i2i"),
                 prompt=p3)
    else:
        log("  No reference image found in history, skipping i2i test")
        results.append({"name": "flux2_i2i", "status": "skipped", "error": "no ref image"})
        save_results()

    # ── 4. Flux2 multiple angles ──────────────────────────────────
    log("\n[4] Flux2 multiple angles (fixed SimplePromptBatcher)")
    if ref_img:
        run_test("flux2_angles",
                 cg.flux2_multiple_angles(
                     ref_img,
                     angle_prompts=["front view", "side view", "3/4 angle view"],
                     filename_prefix="test_angles"),
                 prompt="multiple angles",
                 timeout=180)
    else:
        log("  Skipping — no reference image")
        results.append({"name": "flux2_angles", "status": "skipped"})
        save_results()

    # ── 5. TTS ────────────────────────────────────────────────────
    log("\n[5] Qwen TTS")
    p5 = "This is a test of the text to speech system."
    run_test("qwen_tts",
             cg.qwen_tts(p5,
                          voice_instruct="Clear, neutral male voice",
                          filename_prefix="test_tts"),
             prompt=p5,
             timeout=120)

    # ── 6. Voice clone ────────────────────────────────────────────
    log("\n[6] Qwen voice clone (gio)")
    p6 = "This is a test using the cloned voice."
    run_test("qwen_clone",
             cg.qwen_voice_clone(p6,
                                  voice_name="gio",
                                  filename_prefix="test_clone"),
             prompt=p6,
             timeout=180)

    # ── 7. LTX2 t2v — increasing lengths ─────────────────────────
    log("\n[7] LTX2 t2v — length sweep (2s, 4s, 6s, 8s, 10s)")
    prompt_t2v = "a glowing blue jellyfish drifting through dark ocean water, cinematic"
    t2v_oom_at = None
    for secs in [2, 4, 6, 8, 10]:
        if t2v_oom_at:
            log(f"  Skipping {secs}s (OOM at {t2v_oom_at}s)")
            results.append({"name": f"ltx2_t2v_{secs}s", "status": "skipped",
                             "error": f"OOM at {t2v_oom_at}s"})
            save_results()
            continue
        log(f"\n  t2v {secs}s")
        rec = run_test(f"ltx2_t2v_{secs}s",
                       cg.ltx2_text_to_video(prompt_t2v, seconds=secs,
                                              filename_prefix=f"test_t2v_{secs}s",
                                              seed=seed),
                       prompt=prompt_t2v,
                       timeout=900)
        if rec["status"] in ("oom", "error"):
            t2v_oom_at = secs
            log(f"  !! OOM/error at {secs}s — stopping length sweep")

    # ── 8. LTX2 i2v — with camera LoRA ───────────────────────────
    log("\n[8] LTX2 i2v 3s + dolly-in camera LoRA")
    # Use the same uploaded ref_img (from t2i output, already uploaded to input dir)
    i2v_ref = ref_img  # already uploaded to ComfyUI input, or None

    if i2v_ref:
        log(f"  Using first frame: {i2v_ref}")
        p8 = "cinematic dolly in, dramatic lighting"
        run_test("ltx2_i2v_3s_dolly",
                 cg.ltx2_image_to_video(i2v_ref, p8,
                                         seconds=3, camera_lora="dolly-in",
                                         filename_prefix="test_i2v_dolly",
                                         seed=seed),
                 prompt=p8,
                 timeout=900)
    else:
        log("  No reference frame, skipping")
        results.append({"name": "ltx2_i2v_3s_dolly", "status": "skipped"})
        save_results()

    # ── 9. LTX2 i2v — length sweep ───────────────────────────────
    log("\n[9] LTX2 i2v — length sweep (3s, 5s, 8s, 12s)")
    if i2v_ref:
        i2v_oom_at = None
        for secs in [3, 5, 8, 12]:
            if i2v_oom_at:
                results.append({"name": f"ltx2_i2v_{secs}s", "status": "skipped",
                                 "error": f"OOM at {i2v_oom_at}s"})
                save_results()
                continue
            log(f"\n  i2v {secs}s")
            rec = run_test(f"ltx2_i2v_{secs}s",
                           cg.ltx2_image_to_video(i2v_ref, prompt_t2v,
                                                   seconds=secs,
                                                   filename_prefix=f"test_i2v_{secs}s",
                                                   seed=seed),
                           prompt=prompt_t2v,
                           timeout=900)
            if rec["status"] in ("oom", "error"):
                i2v_oom_at = secs
    else:
        log("  No reference frame, skipping i2v length sweep")

    # ── 10. LTX2 multiframe ───────────────────────────────────────
    log("\n[10] LTX2 multiframe (guide frames from saved outputs)")
    # Upload PNG outputs from successful tests to ComfyUI input
    mf_frames = []
    for r in results:
        if r.get("status") == "success":
            saved_pngs = [s for s in r.get("saved", []) if s.endswith(".png")]
            for sp in saved_pngs:
                try:
                    uploaded = upload_to_input(sp)
                    mf_frames.append(uploaded)
                    break
                except Exception:
                    pass
            if len(mf_frames) >= 3:
                break

    if len(mf_frames) >= 2:
        mf_prompt = "cinematic motion, dramatic lighting"

        # 10a. 1 guide frame (start only)
        log("\n[10a] LTX2 multiframe — 1 guide frame (start)")
        run_test("ltx2_mf_1frame",
                 cg.ltx2_multiframe([(mf_frames[0], 0, 0.8)], mf_prompt,
                                     seconds=3, filename_prefix="test_mf1", seed=seed),
                 prompt=mf_prompt,
                 timeout=900)

        # 10b. 2 guide frames (start + end)
        log("\n[10b] LTX2 multiframe — 2 guide frames (start + end)")
        run_test("ltx2_mf_2frames",
                 cg.ltx2_multiframe([(mf_frames[0], 0, 0.6), (mf_frames[-1], -1, 0.6)],
                                     mf_prompt, seconds=3, filename_prefix="test_mf2", seed=seed),
                 prompt=mf_prompt,
                 timeout=900)

        # 10c. 3 guide frames (start + mid + end) if enough images available
        if len(mf_frames) >= 3:
            log("\n[10c] LTX2 multiframe — 3 guide frames (start + mid + end)")
            mid_frame = mf_frames[len(mf_frames) // 2]
            mid_idx = (3 * 24) // 2  # midpoint frame index for 3s@24fps
            run_test("ltx2_mf_3frames",
                     cg.ltx2_multiframe(
                         [(mf_frames[0], 0, 0.6), (mid_frame, mid_idx, 0.5), (mf_frames[-1], -1, 0.6)],
                         mf_prompt, seconds=3, filename_prefix="test_mf3", seed=seed),
                     prompt=mf_prompt,
                     timeout=900)
        else:
            results.append({"name": "ltx2_mf_3frames", "status": "skipped",
                             "error": "not enough guide images"})
            save_results()
    else:
        log("  Not enough frames for multiframe tests, skipping")
        for name in ("ltx2_mf_1frame", "ltx2_mf_2frames", "ltx2_mf_3frames"):
            results.append({"name": name, "status": "skipped", "error": "not enough frames"})
        save_results()

    # ── 11. last_frame extraction + chain test ────────────────────
    log("\n[11] Extract last frame + chain into i2v")
    # Use a successful t2v video to extract last frame on the server
    chain_video = None
    for r in results:
        if r.get("status") == "success" and "t2v" in r.get("name", ""):
            saved_mp4s = [s for s in r.get("saved", []) if s.endswith(".mp4")]
            if saved_mp4s:
                chain_video = saved_mp4s[0]
                break

    if chain_video:
        # The server path: ComfyUI output dir is typically /app/ComfyUI/output/
        server_video_path = f"/app/ComfyUI/output/{Path(chain_video).name}"
        log(f"  Extracting last frame from: {server_video_path}")
        lf_rec = run_test("last_frame_extract",
                          cg.extract_last_frame(server_video_path, filename_prefix="test_lastframe"),
                          prompt="extract last frame",
                          timeout=60)
        # Download and upload the extracted PNG for the chain i2v
        chain_ref = None
        if lf_rec.get("status") == "success":
            lf_pngs = [s for s in lf_rec.get("saved", []) if s.endswith(".png")]
            if lf_pngs:
                try:
                    chain_ref = upload_to_input(lf_pngs[0])
                    log(f"  Chain ref uploaded: {chain_ref}")
                except Exception as e:
                    log(f"  Upload failed: {e}")
        if chain_ref:
            log("\n  Chain i2v: last frame → new segment")
            run_test("ltx2_chain_i2v",
                     cg.ltx2_image_to_video(chain_ref, prompt_t2v,
                                             seconds=3, filename_prefix="test_chain",
                                             seed=seed),
                     prompt=prompt_t2v,
                     timeout=900)
        else:
            results.append({"name": "ltx2_chain_i2v", "status": "skipped",
                             "error": "no chain ref"})
            save_results()
    else:
        log("  No t2v video found for chain test")
        for name in ("last_frame_extract", "ltx2_chain_i2v"):
            results.append({"name": name, "status": "skipped", "error": "no source video"})
        save_results()

    # ── 13. LTX2 t2v second pass ──────────────────────────────────
    if not SKIP_SECOND_PASS:
        log("\n[13] LTX2 t2v 2s + second pass")
        run_test("ltx2_t2v_2s_second_pass",
                 cg.ltx2_text_to_video(prompt_t2v, seconds=2,
                                        filename_prefix="test_t2v_2pass",
                                        second_pass=True, seed=seed),
                 prompt=prompt_t2v,
                 timeout=1200)

        log("\n[14] LTX2 i2v 2s + second pass")
        if i2v_ref:
            run_test("ltx2_i2v_2s_second_pass",
                     cg.ltx2_image_to_video(i2v_ref, prompt_t2v, seconds=2,
                                             filename_prefix="test_i2v_2pass",
                                             second_pass=True, seed=seed),
                     prompt=prompt_t2v,
                     timeout=1200)
    else:
        log("\n[13-14] Second-pass tests skipped (--skip-second-pass)")

    # ── Summary ───────────────────────────────────────────────────
    log("\n" + "=" * 60)
    log("RESULTS SUMMARY")
    log("=" * 60)
    counts = {}
    for r in results:
        st = r.get("status", "?")
        counts[st] = counts.get(st, 0) + 1
        elapsed = r.get("elapsed_s", "")
        elapsed_str = f" ({elapsed}s)" if elapsed else ""
        err = r.get("error", "")
        err_str = f" — {err[:80]}" if err else ""
        log(f"  {r['name']:40} {st}{elapsed_str}{err_str}")

    log(f"\nTotal: {len(results)}  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    log(f"Results saved to: {RESULTS_FILE.resolve()}")
    save_results()


if __name__ == "__main__":
    main()
