import os
import subprocess

FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

STYLE_ASSETS = {
    "aura": {
        "bgm_query": "ytsearch1:brazilian phonk no copyright aggressive bass",
        "sfx_query": "ytsearch1:bass drop impact sound effect no copyright",
        "eq": "eq=contrast=1.16:brightness=-0.02:saturation=1.22",
        "caption_color": "&H0000FF88"
    },
    "funny": {
        "bgm_query": "ytsearch1:funny comedy background music no copyright",
        "sfx_query": "ytsearch1:vine boom sound effect no copyright",
        "eq": "eq=contrast=1.08:saturation=1.18",
        "caption_color": "&H0000FFFF"
    },
    "documentary": {
        "bgm_query": "ytsearch1:cinematic dark documentary ambient music no copyright",
        "sfx_query": "ytsearch1:cinematic whoosh riser sound effect",
        "eq": "eq=contrast=1.12:brightness=-0.02:saturation=0.88",
        "caption_color": "&H00FFFFFF"
    },
    "casual": {
        "bgm_query": "ytsearch1:chill lofi vlog beat no copyright",
        "sfx_query": "ytsearch1:subtle pop notification sound effect",
        "eq": "eq=contrast=1.05:saturation=1.08",
        "caption_color": "&H00FFFFFF"
    }
}

def fetch_internet_audio(style):
    cfg = STYLE_ASSETS.get(style, STYLE_ASSETS["casual"])
    bgm_file = f"bgm_{style}.mp3"
    sfx_file = f"sfx_{style}.mp3"

    if not os.path.exists(bgm_file):
        subprocess.run([
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--max-filesize", "15M", "-o", f"bgm_{style}.%(ext)s",
            cfg["bgm_query"]
        ], check=False)

    if not os.path.exists(sfx_file):
        subprocess.run([
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--max-filesize", "5M", "-o", f"sfx_{style}.%(ext)s",
            cfg["sfx_query"]
        ], check=False)

    return (bgm_file if os.path.exists(bgm_file) else None), (sfx_file if os.path.exists(sfx_file) else None)

def _format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def generate_styled_captions(words, clip_start, clip_end, style, ass_path):
    clip_words = [w for w in words if w.get("start", 0) >= clip_start and w.get("end", 0) <= clip_end]
    if not clip_words:
        return None

    cfg = STYLE_ASSETS.get(style, STYLE_ASSETS["casual"])
    color = cfg["caption_color"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,82,{color},&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,5,3,2,45,45,380,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for i in range(0, len(clip_words), 2):
        chunk = clip_words[i:i+2]
        if not chunk:
            continue
        w_start = max(0, chunk[0]["start"] - clip_start)
        w_end = max(w_start + 0.2, chunk[-1]["end"] - clip_start)
        text = " ".join(w["word"].strip().upper() for w in chunk)
        animated_text = r"{\fscx88\fscy88\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}" + text
        events.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,,0,0,0,,{animated_text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return ass_path

def render_pro_short(video_path, clip_data, word_timestamps, index):
    start = float(clip_data.get("start", 0))
    end = float(clip_data.get("end", start + 25))
    duration = max(5.0, min(58.0, end - start))
    style = clip_data.get("mood", "casual").lower()
    if style not in STYLE_ASSETS:
        style = "casual"

    cfg = STYLE_ASSETS[style]
    hook_text = clip_data.get("hook_text", "WATCH TILL END").replace("'", "").replace(":", "").upper()
    output_file = f"MAG73_{style.upper()}_Short_{index + 1}.mp4"

    bgm_file, sfx_file = fetch_internet_audio(style)
    ass_file = generate_styled_captions(word_timestamps, start, start + duration, style, f"cap_{index}.ass")

    # Works cleanly for BOTH vertical (9:16) and horizontal (16:9) videos!
    vf_parts = [
        "scale=1080:1920:force_original_aspect_ratio=increase",
        "crop=1080:1920",
        "setsar=1",
        cfg["eq"],
        "vignette=PI/5",
        f"drawtext=fontfile={FONT_PATH}:text='{hook_text}':fontcolor=yellow:fontsize=58:box=1:boxcolor=black@0.8:boxborderw=20:x=(w-text_w)/2:y=190:enable='between(t,0,3.8)'"
    ]
    if ass_file and os.path.exists(ass_file):
        vf_parts.append(f"ass={ass_file}")

    vf_filter = ",".join(vf_parts)

    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    if bgm_file and sfx_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file, "-i", sfx_file])
        filter_complex = (
            f"[0:v]{vf_filter}[v];"
            f"[0:a]volume=1.15[voice];"
            f"[1:a]volume=0.16[bgm];"
            f"[2:a]atrim=0:2.5,volume=0.50[sfx];"
            f"[voice][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=2[a]"
        )
    elif bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        filter_complex = (
            f"[0:v]{vf_filter}[v];"
            f"[0:a]volume=1.15[voice];"
            f"[1:a]volume=0.16[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first[a]"
        )
    else:
        filter_complex = f"[0:v]{vf_filter}[v];[0:a]anull[a]"

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k",
        output_file
    ])

    print(f"[MAG73 Pro Editor] Rendering {output_file}...")
    subprocess.run(cmd, check=True)
    return output_file
