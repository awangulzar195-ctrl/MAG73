import os
import json
import shutil
import subprocess
from input_engine import fetch_media, fetch_scan_media, fetch_clip_segment
from ai_council import (
    run_fast_scan_council,
    run_super_ai_council,
    extract_accurate_transcript,
    refine_clip_metadata,
    _get_plugin_config,
)
from auto_editor import render_pro_short


def _probe_duration(path):
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return max(1.0, float(out))
    except Exception:
        return 30.0


def _exact_trim_segment(seg_path, local_start, target_dur, out_path="exact_clip.mp4"):
    """
    Trims segment to exact 0.000s start (frame-accurate) BEFORE transcription & DSP,
    permanently eliminating yt-dlp keyframe drift between captions, effects, and audio.
    """
    seg_dur = _probe_duration(seg_path)
    safe_start = max(0.0, float(local_start))
    if seg_dur - safe_start < 7.0:
        safe_start = max(0.0, seg_dur - max(10.0, target_dur))
    trim_len = min(seg_dur - safe_start, target_dur + 2.0)

    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{safe_start:.3f}", "-i", seg_path,
            "-t", f"{trim_len:.3f}",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-avoid_negative_ts", "make_zero",
            out_path,
        ],
        check=True,
        timeout=90,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"[MAG73 Trim] Frame-accurate 0.000s clip ready ({trim_len:.2f}s).")
    return out_path


def main():
    source_url = os.getenv("SOURCE_URL", "").strip()
    mode = os.getenv("INPUT_MODE", "vod").strip().lower()
    clip_spec_raw = os.getenv("CLIP_SPEC", "").strip()

    if not source_url:
        raise RuntimeError("SOURCE_URL is missing!")

    os.makedirs("output_clips", exist_ok=True)
    is_upload_asset = "api.github.com/repos/" in source_url and "/releases/assets/" in source_url

    # MODE 1: ULTRA-FAST SCAN (Audio + YouTube Heatmap + Comments)
    if mode == "scan":
        video_path, audio_path, audience_signals = fetch_scan_media(source_url, is_upload=is_upload_asset)
        clips = run_fast_scan_council(audio_path, audience_signals, video_path=video_path)

        scan_payload = {
            "source_url": source_url,
            "total_clips": len(clips),
            "clips": clips,
        }
        out_json = os.path.join("output_clips", "scan_result.json")
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(scan_payload, f, ensure_ascii=False, indent=2)
        print(f"[MAG73 Fast Scan] Saved {len(clips)} detected moment(s) to {out_json}")
        return

    # MODE 2: RENDER SINGLE SELECTED CLIP (Trim-First Zero-Drift Parallel Pipeline)
    if mode == "render_clip":
        if not clip_spec_raw:
            raise RuntimeError("CLIP_SPEC JSON is missing for render_clip mode!")

        clip_data = json.loads(clip_spec_raw)
        start_sec = float(clip_data.get("start", 0))
        end_sec = float(clip_data.get("end", start_sec + 20))
        target_dur = max(10.0, min(35.0, end_sec - start_sec))
        clip_index = int(clip_data.get("clip_index", 0))
        video_title = str(clip_data.get("video_title", "") or "")

        fetch_mode = "upload" if is_upload_asset else "vod"
        seg_path, offset_sec = fetch_clip_segment(source_url, start_sec, end_sec, mode=fetch_mode)

        local_start = max(0.0, start_sec - offset_sec)
        exact_path = _exact_trim_segment(seg_path, local_start, target_dur, "exact_clip.mp4")

        local_clip = dict(clip_data)
        local_clip["orig_start"] = int(round(start_sec))
        local_clip["start"] = 0.0
        local_clip["end"] = target_dur

        plugin_cfg = _get_plugin_config()
        caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
        seg_transcript, word_timestamps, _ = extract_accurate_transcript(
            exact_path, caption_lang=caption_lang, context_hint=video_title
        )

        # Verify exact hook title, exact 0.00s-aligned climax peak_sec, and unique stamp
        local_clip = refine_clip_metadata(local_clip, seg_transcript, word_timestamps)

        out_mp4 = render_pro_short(exact_path, local_clip, word_timestamps, clip_index)
        if out_mp4 and os.path.exists(out_mp4):
            shutil.move(out_mp4, os.path.join("output_clips", os.path.basename(out_mp4)))
            print(f"[MAG73 Render] Individual clip ready: output_clips/{os.path.basename(out_mp4)}")
        return

    # MODE 3: DIRECT LIVE / VOD / UPLOAD (Live Stream & Legacy)
    video_path, audience_signals = fetch_media(source_url, mode=mode)
    clips, word_timestamps = run_super_ai_council(video_path, audience_signals)

    if not clips:
        print("[MAG73] No viral clips detected in this segment.")
        return

    for idx, clip_data in enumerate(clips):
        try:
            clip_data["orig_start"] = int(round(float(clip_data.get("start", 0))))
            out_mp4 = render_pro_short(video_path, clip_data, word_timestamps, idx)
            if out_mp4 and os.path.exists(out_mp4):
                shutil.move(out_mp4, os.path.join("output_clips", os.path.basename(out_mp4)))
        except Exception as e:
            print(f"[MAG73] Clip {idx + 1} render error: {e}")


if __name__ == "__main__":
    main()
