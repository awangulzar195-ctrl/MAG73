import os
import re
import glob
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


def _run_ytdlp_with_fallback(base_args, url, timeout_sec=80):
    strategies = [
        [],
        ["--extractor-args", "youtube:player_client=web,mweb"],
        ["--extractor-args", "youtube:player_client=ios,web"],
    ]
    last_stderr = ""
    for extra in strategies:
        cmd = _base_ytdlp_cmd() + extra + base_args + [url]
        print(f"[MAG73 Input Engine] yt-dlp strategy: {extra or 'default'} (timeout={timeout_sec}s)")
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


def _extract_signals_from_info(pattern="*info.json"):
    """Extracts YouTube Most Replayed Heatmap spikes + Comment Timestamps + Title/Duration."""
    signals = {
        "chat_spikes": [],
        "heatmap_spikes": [],
        "comment_timestamps": [],
        "top_comments": [],
        "video_title": "",
        "duration": 0.0,
    }
    matches = glob.glob(pattern)
    if not matches:
        return signals
    try:
        with open(matches[0], "r", encoding="utf-8", errors="ignore") as f:
            data = json.load(f)

        signals["video_title"] = str(data.get("title", "") or "")
        signals["duration"] = float(data.get("duration") or 0.0)

        # YouTube Most Replayed Heatmap (goldmine for viral moments!)
        heatmap = data.get("heatmap") or []
        if isinstance(heatmap, list) and heatmap:
            ranked = sorted(
                [h for h in heatmap if isinstance(h, dict) and float(h.get("value", 0)) >= 0.55],
                key=lambda x: float(x.get("value", 0)),
                reverse=True,
            )
            spikes = []
            for h in ranked:
                st = int(round(float(h.get("start_time", 0))))
                if all(abs(st - prev) >= 18 for prev in spikes):
                    spikes.append(st)
                if len(spikes) >= 12:
                    break
            signals["heatmap_spikes"] = sorted(spikes)
            print(f"[MAG73 Signals] YouTube Most-Replayed spikes: {signals['heatmap_spikes']}")

        comments = data.get("comments") or []
        ts_set = set()
        top_texts = []
        for c in comments[:60]:
            txt = str(c.get("text", "")).strip()
            if not txt:
                continue
            if len(top_texts) < 12:
                top_texts.append(txt[:160])
            for m in re.finditer(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", txt):
                g1, g2, g3 = m.group(1), m.group(2), m.group(3)
                sec = (int(g1) * 3600 + int(g2) * 60 + int(g3)) if g3 else (int(g1) * 60 + int(g2))
                if sec > 0:
                    ts_set.add(sec)
        signals["comment_timestamps"] = sorted(list(ts_set))[:25]
        signals["top_comments"] = top_texts
    except Exception as e:
        print(f"[MAG73 Signals] Info parse warning: {e}")
    return signals


def fetch_scan_media(source_url, is_upload=False):
    """
    ULTRA-FAST SCAN FETCHER (4x faster):
    For YouTube URLs, downloads ONLY lightweight audio + Most Replayed Heatmap + Comments (seconds, not minutes!).
    Returns: (video_path_or_None, audio_path, signals)
    """
    audio_path = "scan_audio.mp3"
    for f in glob.glob("scan_audio*"):
        try:
            os.remove(f)
        except Exception:
            pass

    if is_upload:
        vpath = _download_github_asset(source_url, "source_video.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", vpath, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", audio_path],
            check=True,
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return vpath, audio_path, {
            "chat_spikes": [], "heatmap_spikes": [], "comment_timestamps": [],
            "top_comments": [], "video_title": "", "duration": 0.0,
        }

    print("[MAG73 Fast Scan] Downloading lightweight audio + YouTube heatmap...")
    args = [
        "-f", "worstaudio[abr>=48]/bestaudio[abr<=96]/bestaudio/worst",
        "-x", "--audio-format", "mp3", "--audio-quality", "7",
        "--write-info-json",
        "--get-comments",
        "--extractor-args", "youtube:max_comments=40,all,0,0",
        "-o", "scan_audio.%(ext)s",
    ]
    ok, err = _run_ytdlp_with_fallback(args, source_url, timeout_sec=75)
    if not ok or not os.path.exists(audio_path):
        args_fast = [
            "-f", "bestaudio/worst",
            "-x", "--audio-format", "mp3", "--audio-quality", "7",
            "--write-info-json",
            "-o", "scan_audio.%(ext)s",
        ]
        ok, err = _run_ytdlp_with_fallback(args_fast, source_url, timeout_sec=65)

    if not ok or not os.path.exists(audio_path):
        raise RuntimeError(f"Fast scan audio fetch failed: {err[-220:]}")

    signals = _extract_signals_from_info("scan_audio*.info.json")
    print(f"[MAG73 Fast Scan] Audio ready ({os.path.getsize(audio_path)//1024} KB).")
    return None, audio_path, signals


def fetch_media(source_url, mode="vod"):
    mode = (mode or "vod").strip().lower()
    out_path = "source_video.mp4"
    if os.path.exists(out_path):
        os.remove(out_path)

    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode...")

    if mode == "upload":
        _download_github_asset(source_url, out_path)
        return out_path, {"chat_spikes": [], "heatmap_spikes": [], "comment_timestamps": [], "top_comments": []}

    if mode == "live":
        args = [
            "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
            "--merge-output-format", "mp4",
            "--live-from-start",
            "--download-sections", "*0-45",
            "-o", out_path,
        ]
        ok, err = _run_ytdlp_with_fallback(args, source_url, timeout_sec=70)
        if not ok or not os.path.exists(out_path):
            args_fb = [
                "-f", "best[height<=720]/best",
                "--merge-output-format", "mp4",
                "--download-sections", "*0-35",
                "-o", out_path,
            ]
            ok, err = _run_ytdlp_with_fallback(args_fb, source_url, timeout_sec=70)
        if not ok or not os.path.exists(out_path):
            raise RuntimeError(f"Live capture failed: {err[-220:]}")
        return out_path, {"chat_spikes": [15], "heatmap_spikes": [], "comment_timestamps": [], "top_comments": []}

    args_simple = [
        "-f", "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]/best",
        "--merge-output-format", "mp4",
        "--write-info-json",
        "-o", out_path,
    ]
    ok, err = _run_ytdlp_with_fallback(args_simple, source_url, timeout_sec=110)
    if not ok or not os.path.exists(out_path):
        raise RuntimeError(f"Video download failed: {err[-220:]}")

    signals = _extract_signals_from_info("source_video*.info.json")
    return out_path, signals


def fetch_clip_segment(source_url, start_sec, end_sec, mode="vod"):
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
