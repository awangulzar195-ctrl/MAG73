import os
import re
import json
import subprocess
import requests

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()


def _has_valid_cookies():
    if not os.path.exists("cookies.txt"):
        return False
    try:
        with open("cookies.txt", "r", encoding="utf-8", errors="ignore") as f:
            lines = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        if len(lines) > 0:
            print(f"[MAG73 Cookies] Loaded cookies.txt ({len(lines)} entries).")
            return True
    except Exception:
        pass
    return False


def _base_ytdlp_cmd():
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--socket-timeout", "15",
        "--retries", "2",
        "--fragment-retries", "2",
    ]
    if _has_valid_cookies():
        cmd.extend(["--cookies", "cookies.txt"])
    return cmd


def _run_ytdlp_with_fallback(base_args, url, timeout_sec=85):
    """Runs yt-dlp with strict timeout so a stalled connection NEVER hangs a job for 50 minutes."""
    strategies = [
        [],
        ["--extractor-args", "youtube:player_client=web,mweb"],
        ["--extractor-args", "youtube:player_client=ios,web"],
    ]
    last_stderr = ""
    for extra in strategies:
        cmd = _base_ytdlp_cmd() + extra + base_args + [url]
        print(f"[MAG73 Input Engine] Running yt-dlp strategy: {extra or 'default'} (timeout={timeout_sec}s)")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
            if result.returncode == 0:
                return True, ""
            last_stderr = (result.stderr or result.stdout or "").strip()
            print(f"[MAG73 Input Engine] Strategy failed: {last_stderr[-180:]}")
        except subprocess.TimeoutExpired:
            last_stderr = f"yt-dlp timed out after {timeout_sec}s"
            print(f"[MAG73 Input Engine] {last_stderr}, switching strategy...")
    return False, last_stderr


def _download_github_asset(asset_url, out_path="source_video.mp4"):
    headers = {"Accept": "application/octet-stream"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    print("[MAG73 Input Engine] Downloading uploaded video from GitHub Release...")
    with requests.get(asset_url, headers=headers, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 10000:
        raise RuntimeError("Uploaded video download failed or file is empty.")
    return out_path


def _extract_comment_signals(info_json_path="source_video.info.json"):
    signals = {"chat_spikes": [], "comment_timestamps": [], "top_comments": []}
    if not os.path.exists(info_json_path):
        return signals
    try:
        with open(info_json_path, "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)
        comments = data.get("comments") or []
        ts_set = set()
        top_texts = []
        for c in comments[:80]:
            txt = str(c.get("text", "")).strip()
            if not txt:
                continue
            if len(top_texts) < 15:
                top_texts.append(txt[:160])
            for m in re.finditer(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", txt):
                g1, g2, g3 = m.group(1), m.group(2), m.group(3)
                sec = (int(g1) * 3600 + int(g2) * 60 + int(g3)) if g3 else (int(g1) * 60 + int(g2))
                if sec > 0:
                    ts_set.add(sec)
        signals["comment_timestamps"] = sorted(list(ts_set))[:30]
        signals["top_comments"] = top_texts
    except Exception as e:
        print(f"[MAG73 Signals] Comment parse warning: {e}")
    return signals


def fetch_media(source_url, mode="vod"):
    mode = (mode or "vod").strip().lower()
    out_path = "source_video.mp4"
    if os.path.exists(out_path):
        os.remove(out_path)

    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode...")

    if mode == "upload":
        _download_github_asset(source_url, out_path)
        return out_path, {"chat_spikes": [], "comment_timestamps": [], "top_comments": []}

    if mode == "live":
        args = [
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
            "--merge-output-format", "mp4",
            "--live-from-start",
            "--download-sections", "*0-45",
            "-o", out_path,
        ]
        ok, err = _run_ytdlp_with_fallback(args, source_url, timeout_sec=75)
        if not ok or not os.path.exists(out_path):
            args_fb = [
                "-f", "best[height<=720]/best",
                "--merge-output-format", "mp4",
                "--download-sections", "*0-35",
                "-o", out_path,
            ]
            ok, err = _run_ytdlp_with_fallback(args_fb, source_url, timeout_sec=75)
        if not ok or not os.path.exists(out_path):
            raise RuntimeError(f"Live capture failed: {err[-220:]}")
        return out_path, {"chat_spikes": [15], "comment_timestamps": [], "top_comments": []}

    args = [
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]/best",
        "--merge-output-format", "mp4",
        "--write-info-json",
        "--get-comments",
        "--extractor-args", "youtube:max_comments=50,all,0,0",
        "-o", out_path,
    ]
    ok, err = _run_ytdlp_with_fallback(args, source_url, timeout_sec=140)
    if not ok or not os.path.exists(out_path):
        args_simple = [
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
            "--merge-output-format", "mp4",
            "-o", out_path,
        ]
        ok, err = _run_ytdlp_with_fallback(args_simple, source_url, timeout_sec=120)

    if not ok or not os.path.exists(out_path):
        raise RuntimeError(f"Video download failed: {err[-220:]}")

    signals = _extract_comment_signals("source_video.info.json")
    return out_path, signals


def fetch_clip_segment(source_url, start_sec, end_sec, mode="vod"):
    """Fast single-clip download with extra 2s tail for clean sentence-end snapping & strict 65s timeout."""
    mode = (mode or "vod").strip().lower()
    seg_path = "clip_segment.mp4"
    if os.path.exists(seg_path):
        os.remove(seg_path)

    pad_start = max(0.0, float(start_sec) - 1.5)
    pad_end = max(pad_start + 6.0, float(end_sec) + 2.5)

    if mode == "upload":
        full_path = _download_github_asset(source_url, "source_video.mp4")
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", str(pad_start), "-to", str(pad_end),
                "-i", full_path, "-c", "copy", seg_path,
            ],
            check=True,
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return seg_path, pad_start

    section_arg = f"*{pad_start:.2f}-{pad_end:.2f}"
    args = [
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
        "--merge-output-format", "mp4",
        "--download-sections", section_arg,
        "--force-keyframes-at-cuts",
        "-o", seg_path,
    ]
    ok, err = _run_ytdlp_with_fallback(args, source_url, timeout_sec=65)
    if ok and os.path.exists(seg_path) and os.path.getsize(seg_path) > 20000:
        print(f"[MAG73 Input Engine] Fast segment ready: {section_arg}")
        return seg_path, pad_start

    # Fast fallback without --force-keyframes-at-cuts (avoids ffmpeg re-encode stall)
    args_fast = [
        "-f", "best[height<=720]/best",
        "--merge-output-format", "mp4",
        "--download-sections", section_arg,
        "-o", seg_path,
    ]
    ok, err = _run_ytdlp_with_fallback(args_fast, source_url, timeout_sec=55)
    if ok and os.path.exists(seg_path) and os.path.getsize(seg_path) > 20000:
        print(f"[MAG73 Input Engine] Fast fallback segment ready: {section_arg}")
        return seg_path, pad_start

    print("[MAG73 Input Engine] Segment download fallback to full video...")
    full_path, _ = fetch_media(source_url, mode="vod")
    return full_path, 0.0
