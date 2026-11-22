import os
import json
import subprocess
import requests

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

def _download_file(url, out_path="source_video.mp4"):
    print(f"[MAG73] Downloading file from: {url}")
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
    print(f"[MAG73] Download complete! Size: {os.path.getsize(out_path) / (1024*1024):.2f} MB")

def fetch_media(source_url, mode="vod"):
    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode...")

    if mode == "upload":
        _download_file(source_url, "source_video.mp4")
        return "source_video.mp4", []

    cookies_env = os.getenv("YT_COOKIES", "").strip()
    base_args = [
        "--js-runtimes", "node",
        "--remote-components", "ejs:github"
    ]
    if cookies_env:
        with open("cookies.txt", "w", encoding="utf-8") as cf:
            cf.write(cookies_env)
        base_args.extend(["--cookies", "cookies.txt"])
        print("[MAG73] Using YT_COOKIES + Node JS solver!")

    # Step 1: Live Chat download (non-blocking)
    chat_cmd = [
        "yt-dlp", "--skip-download", "--write-subs", "--sub-langs", "live_chat",
        "-o", "source_video.%(ext)s"
    ] + base_args + [source_url]
    subprocess.run(chat_cmd, check=False)

    # Step 2: Video + Audio download (default web/tv clients with cookies + JS solver)
    vid_cmd = [
        "yt-dlp",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", "source_video.mp4"
    ] + base_args

    if mode == "live":
        vid_cmd.extend(["--live-from-start", "--download-sections", "*00:00:00-00:05:00"])

    vid_cmd.append(source_url)
    result = subprocess.run(vid_cmd, capture_output=True, text=True)

    if result.returncode != 0 or not os.path.exists("source_video.mp4"):
        print("[MAG73 yt-dlp ERROR]:", result.stderr[-600:])
        raise RuntimeError(f"Video download failed: {result.stderr[-250:]}")

    chat_spikes = extract_chat_hype("source_video.live_chat.json")
    return "source_video.mp4", chat_spikes

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
    sorted_spikes = sorted(buckets.items(), key=lambda x: x[1], reverse=True)
    return [t for t, score in sorted_spikes[:15]]
