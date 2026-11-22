import os
import re
import subprocess

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def _fetch_audio(query, out_prefix):
    """Cookies ke saath YouTube se BGM/SFX download karta hai taaki fail na ho"""
    out_file = f"{out_prefix}.mp3"
    if os.path.exists(out_file) or not query:
        return out_file if os.path.exists(out_file) else None

    q = query if query.startswith("ytsearch") else f"ytsearch1:{query}"
    cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3",
        "--max-filesize", "12M",
        "--js-runtimes", "node",
        "-o", f"{out_prefix}.%(ext)s"
    ]
    if os.path.exists("cookies.txt"):
        cmd.extend(["--cookies", "cookies.txt"])
    cmd.append(q)

    subprocess.run(cmd, check=False)
    return out_file if os.path.exists(out_file) else None

def _format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _ascii_only(text):
    return re.sub(r"[^A-Za-z0-9 !?@#.,'-]", "", text).strip()

def generate_captions(words, clip_start, clip_end, time_offset, color_hex, ass_path):
    """Clean, professional Hinglish/English captions (pop animation, crisp outline)"""
    clip_words = [w for w in words if w.get("start", 0) >= clip_start and w.get("end", 0) <= clip_end]
    if not clip_words:
        return None

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,76,{color_hex},&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,1,0,1,5,2,2,60,60,340,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for i in range(0, len(clip_words), 2):
        chunk = clip_words[i:i+2]
        w_start = max(0, (chunk[0]["start"] - clip_start) + time_offset)
        w_end = max(w_start + 0.25, (chunk[-1]["end"] - clip_start) + time_offset)
        clean_txt = _ascii_only(" ".join(w.get("word", "").strip() for w in chunk))
        if not clean_txt:
            continue
        anim = r"{\fscx92\fscy92\t(0,60,\fscx104\fscy104)\t(60,120,\fscx100\fscy100)}" + clean_txt
        events.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,,0,0,0,,{anim}")

    if not events:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return ass_path

def _build_crop_filter(focus_x):
    """Subject ko frame mein rakhne ke liye smart left/center/right 9:16 crop"""
    if focus_x == "left":
        x_expr = "(iw-1080)*0.18"
    elif focus_x == "right":
        x_expr = "(iw-1080)*0.82"
    else:
        x_expr = "(iw-1080)/2"
    return f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:{x_expr}:(ih-1920)/2,setsar=1"

def render_pro_short(video_path, clip_data, word_timestamps, index):
    start = float(clip_data.get("start", 0))
    end = float(clip_data.get("end", start + 25))
    duration = max(6.0, min(55.0, end - start))

    mood = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("mood", "pro")))[:16] or "pro"
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _ascii_only(str(clip_data.get("title_text", ""))).upper()
    caption_color = str(clip_data.get("caption_color", "&H00FFFFFF"))
    hook_start = clip_data.get("visual_hook_start", None)

    output_file = f"MAG73_{mood.upper()}_Clip_{index + 1}.mp4"
    bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}")
    sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}")

    # Step 1: Optional 2-second Visual Hook prepend
    working_input = video_path
    working_start = start
    working_dur = duration
    caption_offset = 0.0

    if hook_start is not None:
        try:
            hs = float(hook_start)
            if hs >= 0 and abs(hs - start) > 2.5:
                hook_clip = f"hook_{index}.mp4"
                main_clip = f"main_{index}.mp4"
                merged_clip = f"merged_{index}.mp4"
                subprocess.run([
                    "ffmpeg", "-y", "-ss", str(hs), "-t", "2.0", "-i", video_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", hook_clip
                ], check=True)
                subprocess.run([
                    "ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path,
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", main_clip
                ], check=True)
                with open(f"concat_{index}.txt", "w") as cf:
                    cf.write(f"file '{hook_clip}'\nfile '{main_clip}'\n")
                subprocess.run([
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"concat_{index}.txt",
                    "-c", "copy", merged_clip
                ], check=True)
                working_input = merged_clip
                working_start = 0.0
                working_dur = duration + 2.0
                caption_offset = 2.0
        except Exception as e:
            print(f"[MAG73 Hook] Skipped visual hook: {e}")

    ass_file = generate_captions(word_timestamps, start, start + duration, caption_offset, caption_color, f"cap_{index}.ass")

    # Step 2: Clean Pro Visual Filter (No fazool effects/filters!)
    vf = [
        _build_crop_filter(focus_x),
        "eq=contrast=1.06:saturation=1.08"
    ]
    if title_text:
        vf.append(
            f"drawtext=fontfile={FONT_PATH}:text='{title_text}':fontcolor=white:fontsize=52:"
            f"borderw=4:bordercolor=black:x=(w-text_w)/2:y=160:enable='between(t,0,3.2)'"
        )
    if ass_file and os.path.exists(ass_file):
        vf.append(f"ass={ass_file}")

    vf_filter = ",".join(vf)
    cmd = ["ffmpeg", "-y", "-ss", str(working_start), "-t", str(working_dur), "-i", working_input]

    if bgm_file and sfx_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file, "-i", sfx_file])
        fc = (
            f"[0:v]{vf_filter}[v];"
            f"[0:a]volume=1.15[voice];[1:a]volume=0.14[bgm];[2:a]atrim=0:1.8,volume=0.45[sfx];"
            f"[voice][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=2[a]"
        )
    elif bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        fc = f"[0:v]{vf_filter}[v];[0:a]volume=1.15[voice];[1:a]volume=0.14[bgm];[voice][bgm]amix=inputs=2:duration=first[a]"
    else:
        fc = f"[0:v]{vf_filter}[v];[0:a]anull[a]"

    cmd.extend([
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        output_file
    ])

    print(f"[MAG73 Fast Pro Editor] Rendering {output_file}...")
    subprocess.run(cmd, check=True)

    # Step 3: Save Cover Thumbnail (.jpg) in output_clips/ for App My Clips Page
    os.makedirs("output_clips", exist_ok=True)
    cover_path = os.path.join("output_clips", output_file.replace(".mp4", ".jpg"))
    subprocess.run([
        "ffmpeg", "-y", "-ss", "1.5", "-i", output_file,
        "-vframes", "1", "-q:v", "4", cover_path
    ], check=False)

    return output_file
