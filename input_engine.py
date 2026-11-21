import os
import json
import subprocess
import requests

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

def _download_file(url, out_path="source_video.mp4"):
    """Browser User-Agent ke saath file download karta hai taaki 403 Forbidden na aaye"""
    print(f"[MAG73] Downloading file cleanly from: {url}")
    with requests.get(url, headers=BROWSER_HEADERS, stream=True, allow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    if not os.path.exists(out_path) or os.path.getsize(out_path) < 10000:
        raise RuntimeError("Downloaded file is empty or invalid!")
    print(f"[MAG73] Download complete! Size: {os.path.getsize(out_path) / (1024*1024):.2f} MB")

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
        "User-Agent": BROWSER_HEADERS["User-Agent"]
    }
    for api in instances:
        try:
            res = requests.post(api, json={"url": source_url, "videoQuality": "720"}, headers=headers, timeout=25)
            if res.status_code == 200:
                data = res.json()
                dl_url = data.get("url")
                if dl_url:
                    print(f"[MAG73 Fallback] Downloading from: {api}")
                    _download_file(dl_url, out_path)
                    return True
        except Exception as e:
            print(f"[MAG73 Fallback] {api} failed: {e}")
    return False

def fetch_media(source_url, mode="vod"):
    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode for: {source_url}")

    if mode == "upload":
        _download_file(source_url, "source_video.mp4")
        return "source_video.mp4", []

    cookies_env = os.getenv("YT_COOKIES", "").strip()
    cookie_args = []
    if cookies_env:
        with open("cookies.txt", "w", encoding="utf-8") as cf:
            cf.write(cookies_env)
        cookie_args = ["--cookies", "cookies.txt"]
        print("[MAG73] Using YT_COOKIES authentication!")

    chat_cmd = [
        "yt-dlp", "--skip-download", "--write-subs", "--sub-langs", "live_chat",
        "--extractor-args", "youtube:player_client=ios,mweb",
        "-o", "source_video.%(ext)s", source_url
    ] + cookie_args
    subprocess.run(chat_cmd, check=False)

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
