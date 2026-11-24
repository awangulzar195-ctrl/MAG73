import os
import json
import shutil
from input_engine import fetch_media, fetch_clip_segment
from ai_council import run_super_ai_council, extract_accurate_transcript, _get_plugin_config
from auto_editor import render_pro_short


def main():
    source_url = os.getenv("SOURCE_URL", "").strip()
    mode = os.getenv("INPUT_MODE", "vod").strip().lower()
    clip_spec_raw = os.getenv("CLIP_SPEC", "").strip()

    if not source_url:
        raise RuntimeError("SOURCE_URL is missing!")

    os.makedirs("output_clips", exist_ok=True)
    is_upload_asset = "api.github.com/repos/" in source_url and "/releases/assets/" in source_url

    # =========================================================
    # MODE 1: SCAN ONLY (Find all high-hype moments for app UI)
    # =========================================================
    if mode == "scan":
        fetch_mode = "upload" if is_upload_asset else "vod"
        video_path, audience_signals = fetch_media(source_url, mode=fetch_mode)
        clips, _ = run_super_ai_council(video_path, audience_signals)

        scan_payload = {
            "source_url": source_url,
            "total_clips": len(clips),
            "clips": clips,
        }
        out_json = os.path.join("output_clips", "scan_result.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(scan_payload, f, ensure_ascii=False, indent=2)
        print(f"[MAG73 Scan] Saved {len(clips)} detected moment(s) to {out_json}")
        return

    # =========================================================
    # MODE 2: RENDER SINGLE SELECTED CLIP (Parallel Individual)
    # =========================================================
    if mode == "render_clip":
        if not clip_spec_raw:
            raise RuntimeError("CLIP_SPEC JSON is missing for render_clip mode!")

        clip_data = json.loads(clip_spec_raw)
        start_sec = float(clip_data.get("start", 0))
        end_sec = float(clip_data.get("end", start_sec + 20))
        clip_index = int(clip_data.get("clip_index", 0))

        fetch_mode = "upload" if is_upload_asset else "vod"
        seg_path, offset_sec = fetch_clip_segment(source_url, start_sec, end_sec, mode=fetch_mode)

        # Adjust timestamps relative to downloaded segment
        local_clip = dict(clip_data)
        local_clip["start"] = max(0.0, start_sec - offset_sec)
        local_clip["end"] = max(local_clip["start"] + 8.0, end_sec - offset_sec)

        plugin_cfg = _get_plugin_config()
        caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
        _, word_timestamps, _ = extract_accurate_transcript(seg_path, caption_lang=caption_lang)

        out_mp4 = render_pro_short(seg_path, local_clip, word_timestamps, clip_index)
        if out_mp4 and os.path.exists(out_mp4):
            shutil.move(out_mp4, os.path.join("output_clips", os.path.basename(out_mp4)))
            print(f"[MAG73 Render] Individual clip ready: output_clips/{os.path.basename(out_mp4)}")
        return

    # =========================================================
    # MODE 3: DIRECT LIVE / VOD / UPLOAD (Legacy & Live Stream)
    # =========================================================
    video_path, audience_signals = fetch_media(source_url, mode=mode)
    clips, word_timestamps = run_super_ai_council(video_path, audience_signals)

    if not clips:
        print("[MAG73] No viral clips detected in this segment.")
        return

    for idx, clip_data in enumerate(clips):
        try:
            out_mp4 = render_pro_short(video_path, clip_data, word_timestamps, idx)
            if out_mp4 and os.path.exists(out_mp4):
                shutil.move(out_mp4, os.path.join("output_clips", os.path.basename(out_mp4)))
        except Exception as e:
            print(f"[MAG73] Clip {idx + 1} render error: {e}")


if __name__ == "__main__":
    main()
