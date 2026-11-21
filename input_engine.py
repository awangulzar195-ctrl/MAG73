import os
import json
import subprocess
import urllib.request

def fetch_media(source_url, mode="vod"):
    """
    mode = 'live'   -> Live stream chunk + live chat
    mode = 'vod'    -> YouTube video / ended stream + live chat replay
    mode = 'upload' -> Direct uploaded video file link
    """
    print(f"[MAG73 Input Engine] Starting in {mode.upper()} mode for: {source_url}")

    if mode == "upload":
        print("[MAG73] Downloading uploaded video file...")
        urllib.request.urlretrieve(source_url, "source_video.mp4")
        return "source_video.mp4", []

    # Step 1: Pehle Live Chat alag se try karo (agar chat na ho toh crash na ho!)
    chat_cmd = [
        "yt-dlp",
        "--skip-download",
        "--write-subs",
        "--sub-langs", "live_chat",
        "--extractor-args", "youtube:player_client=android,web",
        "-o", "source_video.%(ext)s",
        source_url
    ]
    subprocess.run(chat_cmd, check=False)

    # Step 2: Video + Audio download (Android/TV client bypasses GitHub datacenter bot-block)
    vid_cmd = [
        "yt-dlp",
        "--extractor-args", "youtube:player_client=android,tv_embedded",
        "-f", "bv*[height<=1080]+ba/b[height<=1080]/best",
        "--merge-output-format", "mp4",
        "-o", "source_video.mp4",
        source_url
    ]

    if mode == "live":
        vid_cmd.insert(1, "--live-from-start")
        vid_cmd.extend(["--download-sections", "*00:00:00-00:05:00"])

    result = subprocess.run(vid_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("[MAG73 yt-dlp STDERR]:", result.stderr)
        raise RuntimeError(f"Video download failed: {result.stderr[:300]}")

    chat_spikes = extract_chat_hype("source_video.live_chat.json")
    return "source_video.mp4", chat_spikes


def extract_chat_hype(chat_file):
    """Live chat ke messages analyze karke top hype timestamps (seconds) nikaalta hai"""
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
    top_times = [t for t, score in sorted_spikes[:15]]
    print(f"[MAG73] Top Chat Hype Timestamps (sec): {top_times}")
    return top_times
