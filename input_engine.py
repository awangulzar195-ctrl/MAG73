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


def _base_ytdlp_cmd(use_cookies=True):
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--socket-timeout", "15",
        "--retries", "2",
        "--fragment-retries", "2",
    ]
    if use_cookies and _has_valid_cookies():
        cmd.extend(["--cookies", "cookies.txt"])
    return cmd


def _run_ytdlp_with_fallback(base_args, url, timeout_sec=80):
    strategies = [
        (True, []),
        (True, ["--extractor-args", "youtube:player_client=web,mweb"]),
        (False, ["--extractor-args", "youtube:player_client=android_vr,web"]),
        (False, ["--extractor-args", "youtube:player_client=ios"]),
        (False, ["--extractor-args", "youtube:player_client=tv"]),
    ]
    last_stderr = ""
    for use_ck, extra in strategies:
        cmd = _base_ytdlp_cmd(use_cookies=use_ck) + extra + base_args + [url]
        tag = f"{'cookies' if use_ck else 'nocookies'} {extra or 'default'}"
        print(f"[MAG73 Input Engine] yt-dlp strategy: {tag} (timeout={timeout_sec}s)")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
            if result.returncode == 0:
                return True, result.stdout.strip()
            last_stderr = (result.stderr or result.stdout or "").strip()
            print(f"[MAG73 Input Engine] Strategy failed: {last_stderr[-180:]}")
        except subprocess.TimeoutExpired:
            last_stderr = f"yt-dlp timed out after {timeout_sec}s"
            print(f"[MAG73 Input Engine] {last_stderr}, switching strategy...")
    return False, last_stderr


def _parse_json3_subtitles(pattern="scan_meta*.json3"):
    """Parses YouTube json3 subtitles in <1s so VOD Scan doesn't need slow CPU Whisper!"""
    files = sorted(glob.glob(pattern))
    if not files:
        return []
    # Prefer English/Hinglish/Hindi track if multiple exist
    chosen = files[0]
    for f in files:
        fl = f.lower()
        if ".en." in fl or ".hi." in fl or ".en-in." in fl:
            chosen = f
            break
    words = []
    try:
        with open(chosen, "r", encoding="utf-8", errors="ignore") as fp:
            data = json.load(fp)
        for ev in (data.get("events") or []):
            t_start = float(ev.get("tStartMs", 0)) / 1000.0
            d_dur = float(ev.get("dDurationMs", 1500)) / 1000.0
            segs = ev.get("segs") or []
            if not segs:
                continue
            seg_text = "".join(str(s.get("utf8", "")) for s in segs).replace("\n", " ").strip()
            toks = [t for t in seg_text.split() if t.strip()]
            if not toks:
                continue
            step = max(0.08, min(0.8, d_dur / len(toks)))
            for i, tok in enumerate(toks):
                ws = round(t_start + i * step, 2)
                we = round(ws + step, 2)
                words.append({"word": tok, "start": ws, "end": we})
        print(f"[MAG73 Fast Scan] Parsed {len(words)} instant YouTube subtitle words from {os.path.basename(chosen)}!")
    except Exception as e:
        print(f"[MAG73 Fast Scan] Subtitle parse skipped: {e}")
    return words


def _capture_live_hls_now(source_url, out_path="source_video.mp4", duration_sec=32):
    ok, raw_urls = _run_ytdlp_with_fallback(
        ["-f", "best[height<=1080]/bestvideo[height<=1080]+bestaudio/best", "-g"],
        source_url,
        timeout_sec=45,
    )
    if not ok or not raw_urls:
        return False, raw_urls

    urls = [u.strip() for u in raw_urls.splitlines() if u.strip().startswith("http")]
    if not urls:
        return False, "No stream URL resolved"

    cmd = ["ffmpeg", "-y", "-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
    if len(urls) >= 2:
        cmd.extend(["-i", urls[0], "-i", urls[1], "-map", "0:v:0", "-map", "1:a:0"])
    else:
        cmd.extend(["-i", urls[0]])

    cmd.extend([
        "-t", str(duration_sec),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        out_path,
    ])
    print(f"[MAG73 Live Capture] Recording {duration_sec}s of live stream via FFmpeg...")
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=duration_sec + 45)
        if res.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
            return True, ""
        return False, (res.stderr or "")[-220:]
    except subprocess.TimeoutExpired:
        if os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
            return True, ""
        return False, "FFmpeg live capture timed out"


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

        heatmap = data.get("heatmap") or []
        if isinstance(heatmap, list) and heatmap:
            ranked = sorted(
                [h for h in heatmap if isinstance(h, dict) and float(h.get("value", 0)) >= 0.58],
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
        for c in comments[:50]:
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
    INSTANT SCAN ENGINE (~20-35s total):
    1. For YouTube VOD: fetches instant json3 subtitles + Most-Replayed Heatmap + Comments (no video/audio download needed!).
    2. Only downloads tiny 32k audio if subtitles are unavailable.
    Returns: (video_path_or_None, audio_path_or_None, signals, preloaded_words)
    """
    for f in glob.glob("scan_audio*") + glob.glob("scan_meta*"):
        try:
            os.remove(f)
        except Exception:
            pass

    if is_upload:
        audio_path = "scan_audio.mp3"
        vpath = _download_github_asset(source_url, "source_video.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", vpath, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k", audio_path],
            check=True,
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return vpath, audio_path, {
            "chat_spikes": [], "heatmap_spikes": [], "comment_timestamps": [],
            "top_comments": [], "video_title": "", "duration": 0.0,
        }, []

    # Step A: Ultra-fast metadata + subtitles + heatmap (ZERO media download!)
    print("[MAG73 Fast Scan] Fetching instant YouTube subtitles + Most-Replayed Heatmap...")
    meta_args = [
        "--skip-download",
        "--write-info-json",
        "--write-auto-sub",
        "--write-sub",
        "--sub-lang", "en,hi,en-IN,en-orig",
        "--sub-format", "json3",
        "--get-comments",
        "--extractor-args", "youtube:max_comments=35,all,0,0",
        "-o", "scan_meta.%(ext)s",
    ]
    ok, _ = _run_ytdlp_with_fallback(meta_args, source_url, timeout_sec=45)
    if not ok:
        meta_simple = [
            "--skip-download",
            "--write-info-json",
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang", "en,hi,en-IN,en-orig",
            "--sub-format", "json3",
            "-o", "scan_meta.%(ext)s",
        ]
        _run_ytdlp_with_fallback(meta_simple, source_url, timeout_sec=35)

    signals = _extract_signals_from_info("scan_meta*.info.json")
    sub_words = _parse_json3_subtitles("scan_meta*.json3")
    if len(sub_words) >= 35:
        print(f"[MAG73 Fast Scan] Instant subtitle scan ready ({len(sub_words)} words) — skipping audio download!")
        return None, None, signals, sub_words

    # Step B: Fallback to tiny audio download ONLY if no YouTube subtitles existed
    audio_path = "scan_audio.mp3"
    print("[MAG73 Fast Scan] No subtitles found — downloading compact audio...")
    args_audio = [
        "-f", "worstaudio[abr>=32]/bestaudio[abr<=64]/bestaudio/worst",
        "-x", "--audio-format", "mp3", "--audio-quality", "8",
        "-o", "scan_audio.%(ext)s",
    ]
    ok, err = _run_ytdlp_with_fallback(args_audio, source_url, timeout_sec=65)
    if not ok or not os.path.exists(audio_path):
        raise RuntimeError(f"Fast scan audio fetch failed: {err[-220:]}")

    print(f"[MAG73 Fast Scan] Compact audio ready ({os.path.getsize(audio_path)//1024} KB).")
    return None, audio_path, signals, []


def fetch_media(source_url, mode="vod"):
    mode = (mode or "vod").strip().lower()
    out_path = "source_video.mp4"
    if os.path.exists(out_path):
        os.remove(out_path)

    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode...")

    if mode == "upload":
        _download_github_asset(source_url, out_path)
        return out_path, {"chat_spikes": [], "heatmap_spikes": [], "comment_timestamps": [], "top_comments": [], "video_title": ""}

    if mode == "live":
        # Grab stream title quickly if possible
        live_title = ""
        ok_t, title_out = _run_ytdlp_with_fallback(["--skip-download", "--print", "title"], source_url, timeout_sec=20)
        if ok_t and title_out:
            live_title = title_out.splitlines()[0].strip()

        ok, err = _capture_live_hls_now(source_url, out_path=out_path, duration_sec=32)
        if not ok or not os.path.exists(out_path):
            args_vod = [
                "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]/best",
                "--merge-output-format", "mp4",
                "--download-sections", "*0-35",
                "-o", out_path,
            ]
            ok, err = _run_ytdlp_with_fallback(args_vod, source_url, timeout_sec=75)
        if not ok or not os.path.exists(out_path):
            raise RuntimeError(f"Live capture failed (stream may be ended/restricted): {err[-220:]}")
        return out_path, {"chat_spikes": [15], "heatmap_spikes": [], "comment_timestamps": [], "top_comments": [], "video_title": live_title}

    args_simple = [
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--write-info-json",
        "-o", out_path,
    ]
    ok, err = _run_ytdlp_with_fallback(args_simple, source_url, timeout_sec=120)
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
    args_hd = [
        "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--download-sections", section_arg,
        "--force-keyframes-at-cuts",
        "-o", seg_path,
    ]
    ok, err = _run_ytdlp_with_fallback(args_hd, source_url, timeout_sec=75)
    if ok and os.path.exists(seg_path) and os.path.getsize(seg_path) > 20000:
        print(f"[MAG73 Input Engine] 1080p HD segment ready: {section_arg}")
        return seg_path, pad_start

    args_fast = [
        "-f", "best[height<=1080]/best",
        "--merge-output-format", "mp4",
        "--download-sections", section_arg,
        "-o", seg_path,
    ]
    ok, err = _run_ytdlp_with_fallback(args_fast, source_url, timeout_sec=60)
    if ok and os.path.exists(seg_path) and os.path.getsize(seg_path) > 20000:
        print(f"[MAG73 Input Engine] Fast fallback segment ready: {section_arg}")
        return seg_path, pad_start

    print("[MAG73 Input Engine] Segment download fallback to full 1080p video...")
    full_path, _ = fetch_media(source_url, mode="vod")
    return full_path, 0.0
