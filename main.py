import os
import json
import shutil
from input_engine import fetch_media
from ai_council import run_super_ai_council
from auto_editor import render_pro_short

def main():
    source_url = os.getenv("SOURCE_URL", "").strip()
    mode = os.getenv("INPUT_MODE", "vod").strip().lower()  # 'live', 'vod', or 'upload'
    style_override = os.getenv("EDIT_STYLE", "auto").strip().lower()  # 'auto', 'aura', 'funny', 'documentary', 'casual'

    if not source_url:
        raise ValueError("Error: SOURCE_URL is empty! Please provide a video/stream link or uploaded file URL.")

    os.makedirs("output_clips", exist_ok=True)

    # 1. Video + Live Chat Fetch
    video_path, chat_spikes = fetch_media(source_url, mode=mode)

    # 2. Multi-AI Council Deep Analysis
    clips, word_timestamps = run_super_ai_council(video_path, chat_spikes)

    if not clips:
        print("[MAG73] No viral clips detected in this segment.")
        return

    # 3. Multi-Style Pro Rendering
    final_results = []
    for idx, clip in enumerate(clips):
        if style_override != "auto":
            clip["mood"] = style_override

        try:
            rendered_file = render_pro_short(video_path, clip, word_timestamps, idx)
            dest_path = os.path.join("output_clips", rendered_file)
            shutil.move(rendered_file, dest_path)

            clip["file_name"] = rendered_file
            final_results.append(clip)
        except Exception as e:
            print(f"[MAG73] Error rendering clip {idx + 1}: {e}")

    # 4. Metadata & Titles Save Karo (App & Auto-Uploader ke liye)
    with open("output_clips/results.json", "w", encoding="utf-8") as f:
        json.dump(final_results, f, indent=2)

    print(f"[MAG73 SUCCESS] Generated {len(final_results)} ready-to-upload viral clips!")

if __name__ == "__main__":
    main()
