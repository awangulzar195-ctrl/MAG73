import os
import json
import subprocess
import urllib.request
import requests

def _download_via_cobalt_fallback(source_url, out_path="source_video.mp4"):
    """Agar YouTube GitHub IP ko bot-block kare, toh bina cookies ke Cobalt API se video nikaalta hai"""
    print("[MAG73 Fallback] Trying Cobalt public API bypass...")
    instances = [
        "https://api.cobalt.tools/",
        "https://cobalt-api.kwiatekmiki.com/",
        "https://co.wuk.sh/api/json"
    ]
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0"
    }
    for api in instances:
        try:
            res = requests.post(api, json={"url": source_url, "videoQuality": "720"}, headers=headers, timeout=25)
            if res.status_code == 200:
                data = res.json()
                dl_url = data.get("url")
                if dl_url:
                    print(f"[MAG73 Fallback] Downloading from: {api}")
                    urllib.request.urlretrieve(dl_url, out_path)
                    if os.path.exists(out_path) and os.path.getsize(out_path) > 50000:
                        return True
        except Exception as e:
            print(f"[MAG73 Fallback] {api} failed: {e}")
    return False

def fetch_media(source_url, mode="vod"):
    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode for: {source_url}")

    if mode == "upload":
        print("[MAG73] Downloading uploaded video file...")
        urllib.request.urlretrieve(source_url, "source_video.mp4")
        return "source_video.mp4", []

    # Agar YT_COOKIES secret saved hai toh cookies.txt banao
    cookies_env = os.getenv("YT_COOKIES", "").strip()
    cookie_args = []
    if cookies_env:
        with open("cookies.txt", "w", encoding="utf-8") as cf:
            cf.write(cookies_env)
        cookie_args = ["--cookies", "cookies.txt"]
        print("[MAG73] Using YT_COOKIES authentication!")

    # Step 1: Live Chat nikaalne ki koshish (non-blocking)
    chat_cmd = [
        "yt-dlp", "--skip-download", "--write-subs", "--sub-langs", "live_chat",
        "--extractor-args", "youtube:player_client=ios,mweb",
        "-o", "source_video.%(ext)s", source_url
    ] + cookie_args
    subprocess.run(chat_cmd, check=False)

    # Step 2: Video download via yt-dlp (ios,mweb client)
    vid_cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=ios,mweb",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", "source_video.mp4",
        source_url
    ] + cookie_args

    if mode == "live":
        vid_cmd.insert(1, "--live-from-start")
        vid_cmd.extend(["--download-sections", "*00:00:00-00:05:00"])

    result = subprocess.run(vid_cmd, capture_output=True, text=True)

    # Agar YouTube ne phir bhi bot-block kiya toh Cobalt fallback chalao
    if result.returncode != 0 or not os.path.exists("source_video.mp4"):
        print("[MAG73] yt-dlp blocked by YouTube, switching to fallback downloader...")
        success = _download_via_cobalt_fallback(source_url, "source_video.mp4")
        if not success:
            raise RuntimeError(
                "YouTube blocked datacenter IP. Add YT_COOKIES secret in GitHub OR use Gallery Upload mode!"
            )

    chat_spikes = extract_chat_hype("source_video.live_chat.json")
    return "source_video.mp4", chat_spikes

def extract_chat_hype(chat_file):
    if not os.path.exists(chat_file):
        print("[MAG73] No live chat found, using audio + AI vision only.")
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
