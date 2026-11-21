import os
import subprocess

# Internet se automatically style ke hisaab se copyright-free BGM & SFX lane ke search queries
STYLE_ASSETS = {
    "aura": {
        "bgm_query": "ytsearch1:brazilian phonk no copyright aggressive bass",
        "sfx_query": "ytsearch1:bass drop impact sound effect no copyright",
        "eq": "eq=contrast=1.18:brightness=-0.03:saturation=1.25",
        "caption_color": "&H0000FF00",  # Neon Green
        "zoom_speed": "0.0015"
    },
    "funny": {
        "bgm_query": "ytsearch1:funny comedy background music no copyright",
        "sfx_query": "ytsearch1:vine boom sound effect no copyright",
        "eq": "eq=contrast=1.08:saturation=1.20",
        "caption_color": "&H0000FFFF",  # Bright Yellow
        "zoom_speed": "0.0022"
    },
    "documentary": {
        "bgm_query": "ytsearch1:cinematic dark documentary ambient music no copyright",
        "sfx_query": "ytsearch1:cinematic whoosh riser sound effect",
        "eq": "eq=contrast=1.12:brightness=-0.02:saturation=0.88",
        "caption_color": "&H00FFFFFF",  # Crisp White
        "zoom_speed": "0.0008"
    },
    "casual": {
        "bgm_query": "ytsearch1:chill lofi vlog beat no copyright",
        "sfx_query": "ytsearch1:subtle pop notification sound effect",
        "eq": "eq=contrast=1.05:saturation=1.10",
        "caption_color": "&H0080FFFF",  # Warm Cream/Yellow
        "zoom_speed": "0.0010"
    }
}

def fetch_internet_audio(style):
    """Internet se automatic BGM aur SFX download karta hai"""
    cfg = STYLE_ASSETS.get(style, STYLE_ASSETS["casual"])
    bgm_file = f"bgm_{style}.mp3"
    sfx_file = f"sfx_{style}.mp3"

    if not os.path.exists(bgm_file):
        print(f"[MAG73 Assets] Fetching {style} BGM from internet...")
        subprocess.run([
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--max-filesize", "15M", "-o", f"bgm_{style}.%(ext)s",
            cfg["bgm_query"]
        ], check=False)

    if not os.path.exists(sfx_file):
        print(f"[MAG73 Assets] Fetching {style} SFX from internet...")
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
    """Style ke hisaab se animated pop-up captions banata hai"""
    cfg = STYLE_ASSETS.get(style, STYLE_ASSETS["casual"])
    color = cfg["caption_color"]

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,88,{color},&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,1,0,1,6,3,2,45,45,380,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    clip_words = [w for w in words if w.get("start", 0) >= clip_start and w.get("end", 0) <= clip_end]

    for i in range(0, len(clip_words), 2):
        chunk = clip_words[i:i+2]
        if not chunk:
            continue
        w_start = max(0, chunk[0]["start"] - clip_start)
        w_end = max(w_start + 0.2, chunk[-1]["end"] - clip_start)
        text = " ".join(w["word"].strip().upper() for w in chunk)
        # Pop-in scale animation (\t) har caption par
        animated_text = r"{\fscx85\fscy85\t(0,80,\fscx105\fscy105)\t(80,150,\fscx100\fscy100)}" + text
        events.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,,0,0,0,,{animated_text}")

    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return ass_path

def render_pro_short(video_path, clip_data, word_timestamps, index):
    """Multi-Style Pro Render: Visual Hook + Zoom Motion + Color Filter + Overlay + BGM + SFX + Captions"""
    start = float(clip_data.get("start", 0))
    end = float(clip_data.get("end", start + 30))
    duration = max(10.0, min(58.0, end - start))
    style = clip_data.get("mood", "casual").lower()
    if style not in STYLE_ASSETS:
        style = "casual"

    cfg = STYLE_ASSETS[style]
    hook_text = clip_data.get("hook_text", "WATCH TILL END").replace("'", "").replace(":", "").upper()
    output_file = f"MAG73_{style.upper()}_Short_{index + 1}.mp4"

    bgm_file, sfx_file = fetch_internet_audio(style)
    ass_file = generate_styled_captions(word_timestamps, start, start + duration, style, f"cap_{index}.ass")

    # Visual Hook Banner (sirf pehle 3.5 seconds tak top par flash hoga) + Subtle Vignette Overlay + Color Grade
    vf_filter = (
        f"crop=ih*9/16:ih,scale=1080:1920,setsar=1,"
        f"{cfg['eq']},"
        f"vignette=PI/5,"
        f"drawtext=text='{hook_text}':fontcolor=yellow:fontsize=64:box=1:boxcolor=black@0.82:boxborderw=24:"
        f"x=(w-text_w)/2:y=190:enable='between(t,0,3.8)',"
        f"drawtext=text='@md_awan_73':fontcolor=white@0.45:fontsize=32:x=(w-text_w)/2:y=1780,"
        f"ass={ass_file}"
    )

    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    # Audio mixing: Original voice + Internet BGM + Opening Hook SFX
    if bgm_file and sfx_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file, "-i", sfx_file])
        filter_complex = (
            f"[0:v]{vf_filter}[v];"
            f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,volume=1.15[voice];"
            f"[1:a]volume=0.18[bgm];"
            f"[2:a]atrim=0:2.5,volume=0.55[sfx];"
            f"[voice][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=2[a]"
        )
    elif bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        filter_complex = (
            f"[0:v]{vf_filter}[v];"
            f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11,volume=1.15[voice];"
            f"[1:a]volume=0.18[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first[a]"
        )
    else:
        filter_complex = (
            f"[0:v]{vf_filter}[v];"
            f"[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        )

    cmd.extend([
        "-filter_complex", filter_complex,
        "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "192k",
        output_file
    ])

    print(f"[MAG73 Pro Editor] Rendering {style.upper()} edit -> {output_file}...")
    subprocess.run(cmd, check=True)
    return output_file
