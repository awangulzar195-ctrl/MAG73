import os
import re
import json
import subprocess
import requests

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

def _download_file(url, out_path="source_video.mp4"):
    print("[MAG73] Downloading uploaded file...")
    headers = dict(BROWSER_HEADERS)
    if "api.github.com" in url:
        gh_token = os.getenv("GITHUB_TOKEN", "").strip()
        headers["Authorization"] = f"Bearer {gh_token}"
        headers["Accept"] = "application/octet-stream"

    with requests.get(url, headers=headers, stream=True, allow_redirects=True, timeout=180) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)

    if not os.path.exists(out_path) or os.path.getsize(out_path) < 10000:
        raise RuntimeError("Downloaded file is empty or invalid!")

def _extract_comment_insights(info_json_path):
    if not os.path.exists(info_json_path):
        return {"timestamps": [], "top_comments": []}
    try:
        with open(info_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        comments = data.get("comments", []) or []
        timestamps = {}
        top_comments = []

        comments.sort(key=lambda c: c.get("like_count", 0) or 0, reverse=True)
        for c in comments[:80]:
            text = (c.get("text") or "").strip()
            if not text:
                continue
            if len(top_comments) < 20:
                top_comments.append(text[:140])
            for m in re.findall(r"\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b", text):
                h = int(m[0]) if m[0] else 0
                total_sec = h * 3600 + int(m[1]) * 60 + int(m[2])
                bucket = (total_sec // 5) * 5
                timestamps[bucket] = timestamps.get(bucket, 0) + 1 + (c.get("like_count", 0) or 0) // 10

        sorted_ts = [t for t, _ in sorted(timestamps.items(), key=lambda x: x[1], reverse=True)[:12]]
        return {"timestamps": sorted_ts, "top_comments": top_comments}
    except Exception:
        return {"timestamps": [], "top_comments": []}

def extract_chat_hype(chat_file):
    if not os.path.exists(chat_file):
        return []
    buckets = {}
    hype_words = ["op", "wtf", "lol", "omg", "clip", "💀", "😂", "🔥", "bhai", "arey", "gg", "clutch"]
    with open(chat_file, "r", encoding="utf-8") as f:
        for line in f:
            try:
                data = json.loads(line)
                action = data.get("replayChatItemAction", {})
                offset_ms = int(action.get("videoOffsetTimeMsec", 0))
                sec_bucket = (offset_ms // 10000) * 10
                text = json.dumps(data).lower()
                score = 1 + sum(3 for w in hype_words if w in text)
                buckets[sec_bucket] = buckets.get(sec_bucket, 0) + score
            except Exception:
                continue
    return [t for t, _ in sorted(buckets.items(), key=lambda x: x[1], reverse=True)[:15]]

def _capture_live_chunk(source_url, base_args, duration_sec=120):
    """Ongoing live stream ko bina atke exact 2-minute chunk mein capture karta hai"""
    print(f"[MAG73 Live Monitor] Capturing {duration_sec}s rolling live chunk...")
    url_cmd = ["yt-dlp", "-f", "b[height<=720]/best", "-g"] + base_args + [source_url]
    res = subprocess.run(url_cmd, capture_output=True, text=True, timeout=45)
    stream_urls = [u.strip() for u in res.stdout.splitlines() if u.strip().startswith("http")]

    if not stream_urls:
        raise RuntimeError("Could not get live stream URL.")

    # FFmpeg se exact 120s capture karo (never hangs!)
    ff_cmd = [
        "ffmpeg", "-y", "-i", stream_urls[0],
        "-t", str(duration_sec),
        "-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac",
        "source_video.mp4"
    ]
    subprocess.run(ff_cmd, timeout=duration_sec + 60, check=True)

def fetch_media(source_url, mode="vod"):
    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode...")

    if mode == "upload":
        _download_file(source_url, "source_video.mp4")
        return "source_video.mp4", {"chat_spikes": [], "comment_timestamps": [], "top_comments": []}

    cookies_env = os.getenv("YT_COOKIES", "").strip()
    base_args = [
        "--js-runtimes", "node",
        "--remote-components", "ejs:github"
    ]
    if cookies_env:
        with open("cookies.txt", "w", encoding="utf-8") as cf:
            cf.write(cookies_env)
        base_args.extend(["--cookies", "cookies.txt"])

    # LIVE MODE: Never hang on infinite live_chat — capture clean 2-min rolling chunk!
    if mode == "live":
        _capture_live_chunk(source_url, base_args, duration_sec=120)
        return "source_video.mp4", {"chat_spikes": [], "comment_timestamps": [], "top_comments": []}

    # VOD MODE: Grab top comments & chat replay (with strict 45s timeout so it never hangs)
    meta_cmd = [
        "yt-dlp", "--skip-download",
        "--write-info-json", "--get-comments",
        "--extractor-args", "youtube:max_comments=60,all,0,0",
        "-o", "source_video.%(ext)s"
    ] + base_args + [source_url]
    try:
        subprocess.run(meta_cmd, timeout=45, check=False)
    except subprocess.TimeoutExpired:
        print("[MAG73] Metadata fetch timed out, continuing to video download...")

    vid_cmd = [
        "yt-dlp",
        "-f", "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", "source_video.mp4"
    ] + base_args + [source_url]

    result = subprocess.run(vid_cmd, capture_output=True, text=True)
    if result.returncode != 0 or not os.path.exists("source_video.mp4"):
        raise RuntimeError(f"Video download failed: {result.stderr[-250:]}")

    chat_spikes = extract_chat_hype("source_video.live_chat.json")
    comment_data = _extract_comment_insights("source_video.info.json")

    return "source_video.mp4", {
        "chat_spikes": chat_spikes,
        "comment_timestamps": comment_data["timestamps"],
        "top_comments": comment_data["top_comments"]
    }
