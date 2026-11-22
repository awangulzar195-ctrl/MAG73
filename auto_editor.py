import os
import re
import subprocess

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def _fetch_audio(query, out_prefix):
    out_file = f"{out_prefix}.mp3"
    if not os.path.exists(out_file) and query:
        q = query if query.startswith("ytsearch") else f"ytsearch1:{query}"
        subprocess.run([
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--max-filesize", "12M", "-o", f"{out_prefix}.%(ext)s", q
        ], check=False)
    return out_file if os.path.exists(out_file) else None

def _format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _ascii_only(text):
    return re.sub(r"[^A-Za-z0-9 !?@#.,'-]", "", text).strip()

def generate_captions(words, clip_start, clip_end, color_hex, ass_path):
    clip_words = [w for w in words if w.get("start", 0) >= clip_start and w.get("end", 0) <= clip_end]
    if not clip_words:
        return None

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,86,{color_hex},&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,6,4,2,45,45,360,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for i in range(0, len(clip_words), 2):
        chunk = clip_words[i:i+2]
        w_start = max(0, chunk[0]["start"] - clip_start)
        w_end = max(w_start + 0.25, chunk[-1]["end"] - clip_start)
        clean_txt = _ascii_only(" ".join(w["word"].strip().upper() for w in chunk))
        if not clean_txt:
            continue
        anim = r"{\fscx80\fscy80\t(0,70,\fscx110\fscy110)\t(70,140,\fscx100\fscy100)}" + clean_txt
        events.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,,0,0,0,,{anim}")

    if not events:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return ass_path

def render_pro_short(video_path, clip_data, word_timestamps, index):
    start = float(clip_data.get("start", 0))
    end = float(clip_data.get("end", start + 22))
    duration = max(5.0, min(58.0, end - start))

    mood = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("mood", "pro")))[:16] or "pro"
    hook_text = _ascii_only(str(clip_data.get("hook_text", "WATCH THIS"))).upper() or "WATCH THIS"
    effects = clip_data.get("effects", ["punch_zoom", "vignette"])
    contrast = float(clip_data.get("contrast", 1.14))
    saturation = float(clip_data.get("saturation", 1.18))
    caption_color = str(clip_data.get("caption_color", "&H0000FFFF"))

    output_file = f"MAG73_{mood.upper()}_Clip_{index + 1}.mp4"
    bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}")
    sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}")
    ass_file = generate_captions(word_timestamps, start, start + duration, caption_color, f"cap_{index}.ass")

    vf = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "setsar=1"
    ]

    if "camera_shake" in effects:
        vf.append("scale=1140:2026,crop=1080:1920:x='30+18*sin(t*18)':y='53+18*cos(t*22)'")
    elif "punch_zoom" in effects:
        vf.append("scale='iw*(1+0.07*abs(sin(t*1.6)))':'ih*(1+0.07*abs(sin(t*1.6)))':eval=frame,crop=1080:1920")
    elif "slow_zoom" in effects:
        vf.append("scale='iw*(1+0.004*t)':'ih*(1+0.004*t)':eval=frame,crop=1080:1920")

    if "rgb_glitch" in effects:
        vf.append("rgbashift=rh=6:bh=-6:enable='lt(mod(t,4),0.25)'")

    vf.append(f"eq=contrast={contrast}:saturation={saturation}")
    if "flash_impact" in effects:
        vf.append("eq=brightness=0.35:enable='between(t,0,0.18)+between(t,3.8,3.95)'")
    if "vignette" in effects:
        vf.append("vignette=PI/5")

    vf.append(
        f"drawtext=fontfile={FONT_PATH}:text='{hook_text}':fontcolor=yellow:fontsize=60:"
        f"box=1:boxcolor=black@0.82:boxborderw=22:x=(w-text_w)/2:y=180:enable='between(t,0,3.5)'"
    )
    if ass_file and os.path.exists(ass_file):
        vf.append(f"ass={ass_file}")

    vf_filter = ",".join(vf)
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    if bgm_file and sfx_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file, "-i", sfx_file])
        fc = (
            f"[0:v]{vf_filter}[v];"
            f"[0:a]volume=1.15[voice];[1:a]volume=0.18[bgm];[2:a]atrim=0:2.2,volume=0.55[sfx];"
            f"[voice][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=2[a]"
        )
    elif bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        fc = f"[0:v]{vf_filter}[v];[0:a]volume=1.15[voice];[1:a]volume=0.18[bgm];[voice][bgm]amix=inputs=2:duration=first[a]"
    else:
        fc = f"[0:v]{vf_filter}[v];[0:a]anull[a]"

    cmd.extend([
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k", output_file
    ])

    print(f"[MAG73 Dynamic Editor] Rendering {output_file} with effects {effects}...")
    subprocess.run(cmd, check=True)
    return output_file
