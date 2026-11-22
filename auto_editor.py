import os
import re
import shutil
import subprocess
import requests

FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PRO_FONT_FILE = "Montserrat-ExtraBold.ttf"
PRO_FONT_URL = "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf"


def _ensure_pro_font():
    """Montserrat-ExtraBold download karke system font cache mein register karta hai"""
    if not os.path.exists(PRO_FONT_FILE):
        try:
            r = requests.get(PRO_FONT_URL, timeout=15)
            if r.status_code == 200 and len(r.content) > 50000:
                with open(PRO_FONT_FILE, "wb") as f:
                    f.write(r.content)
        except Exception as e:
            print(f"[MAG73 Font] Download warning: {e}")

    if os.path.exists(PRO_FONT_FILE):
        try:
            font_dir = os.path.expanduser("~/.local/share/fonts")
            os.makedirs(font_dir, exist_ok=True)
            shutil.copy(PRO_FONT_FILE, os.path.join(font_dir, PRO_FONT_FILE))
            subprocess.run(["fc-cache", "-f"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("[MAG73 Font] Registered Montserrat ExtraBold!")
            return PRO_FONT_FILE, "Montserrat ExtraBold"
        except Exception:
            return PRO_FONT_FILE, "Montserrat ExtraBold"
    return FALLBACK_FONT, "DejaVu Sans"


def _fetch_audio(query, out_prefix):
    """Sirf valid non-empty query hone par audio download karta hai"""
    query = (query or "").strip()
    if not query:
        return None
    out_file = f"{out_prefix}.mp3"
    if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
        return out_file

    q = query if query.startswith("ytsearch") else f"ytsearch1:{query}"
    cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3",
        "--max-filesize", "12M",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-o", f"{out_prefix}.%(ext)s"
    ]
    if os.path.exists("cookies.txt"):
        cmd.extend(["--cookies", "cookies.txt"])
    cmd.append(q)

    subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
        print(f"[MAG73 Audio] Ready: {out_file}")
        return out_file
    return None


def _format_ass_time(seconds):
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        s += 1
        cs = 0
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _clean_text(text):
    """FFmpeg drawtext aur ASS ke liye clean ASCII text"""
    text = re.sub(r"[^A-Za-z0-9 !?@#,.-]", "", str(text or ""))
    text = text.replace(":", "").replace("'", "")
    return re.sub(r"\s+", " ", text).strip()


def generate_pro_captions(words, clip_start, clip_end, font_name, is_split, ass_path):
    """
    Studio-Grade Word-by-Word Active Highlight Captions:
    - 2-3 words per clean line
    - Currently spoken word highlighted in Yellow, others Crisp White
    - Stuck-caption protection: koi bhi word 1.2s se zyada screen par nahi atkega
    """
    raw_clip_words = []
    for w in (words or []):
        ws = float(w.get("start", 0))
        we = float(w.get("end", ws + 0.3))
        txt = _clean_text(w.get("word", "")).upper()
        if not txt:
            continue
        if we >= clip_start and ws <= clip_end:
            rel_s = max(0.0, ws - clip_start)
            rel_e = min(clip_end - clip_start, we - clip_start)
            # Stuck-caption protection: cap max single-word duration to 1.15s
            if rel_e - rel_s > 1.15:
                rel_e = rel_s + 0.95
            if rel_e - rel_s < 0.12:
                rel_e = rel_s + 0.22
            raw_clip_words.append({"word": txt, "start": rel_s, "end": rel_e})

    if not raw_clip_words:
        return None

    # Group into clean 2-3 word chunks (max 15 chars per line, break on >0.6s pause)
    chunks = []
    current = []
    for w in raw_clip_words:
        if not current:
            current.append(w)
            continue
        gap = w["start"] - current[-1]["end"]
        curr_len = sum(len(x["word"]) + 1 for x in current)
        if len(current) >= 3 or (curr_len + len(w["word"]) > 15) or gap > 0.65:
            chunks.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        chunks.append(current)

    margin_v = 910 if is_split else 340
    font_size = 74 if is_split else 84

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0000E5FF,&H00000000,&H99000000,-1,0,0,0,100,100,1,0,1,7,4,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for chunk in chunks:
        for active_idx, active_w in enumerate(chunk):
            ev_start = active_w["start"]
            if active_idx + 1 < len(chunk):
                ev_end = min(active_w["end"] + 0.12, chunk[active_idx + 1]["start"])
                if ev_end <= ev_start:
                    ev_end = chunk[active_idx + 1]["start"]
            else:
                ev_end = active_w["end"] + 0.10

            if ev_end - ev_start < 0.08:
                ev_end = ev_start + 0.15

            styled_parts = []
            for idx, w_obj in enumerate(chunk):
                if idx == active_idx:
                    styled_parts.append(f"{{\\c&H0000E5FF&}}{w_obj['word']}{{\\c&H00FFFFFF&}}")
                else:
                    styled_parts.append(w_obj["word"])

            line_text = " ".join(styled_parts)
            # Subtle pop-in only on the first word of a new chunk
            if active_idx == 0:
                line_text = r"{\fscx92\fscy92\t(0,55,\fscx103\fscy103)\t(55,110,\fscx100\fscy100)}" + line_text

            events.append(
                f"Dialogue: 0,{_format_ass_time(ev_start)},{_format_ass_time(ev_end)},Default,,0,0,0,,{line_text}"
            )

    if not events:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return ass_path


def _parse_facecam_box(box):
    if not isinstance(box, list) or len(box) != 4:
        return None
    try:
        x, y, w, h = [float(v) for v in box]
        if w < 0.08 or h < 0.08 or w > 0.65 or h > 0.65:
            return None
        return (max(0.0, min(1.0 - w, x)), max(0.0, min(1.0 - h, y)), w, h)
    except Exception:
        return None


def _build_layout_graph(facecam_box, focus_x):
    """
    Split-Screen (Top Gameplay 1080x958 + 4px Dark Divider + Bottom Facecam 1080x958)
    OR Full Vertical 1080x1920
    """
    if facecam_box is not None:
        fx, fy, fw, fh = facecam_box
        return (
            f"[0:v]split=2[game_src][cam_src];"
            f"[game_src]scale=1080:958:force_original_aspect_ratio=increase,crop=1080:958,setsar=1[top];"
            f"[cam_src]crop=iw*{fw:.4f}:ih*{fh:.4f}:iw*{fx:.4f}:ih*{fy:.4f},"
            f"scale=1080:958:force_original_aspect_ratio=increase,crop=1080:958,setsar=1[bot];"
            f"color=c=0x0F1115:s=1080x4:r=30[div];"
            f"[top][div][bot]vstack=inputs=3:shortest=1[base];"
        )

    if focus_x == "left":
        x_expr = "(iw-1080)*0.18"
    elif focus_x == "right":
        x_expr = "(iw-1080)*0.82"
    else:
        x_expr = "(iw-1080)/2"
    return f"[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920:{x_expr}:(ih-1920)/2,setsar=1[base];"


def render_pro_short(video_path, clip_data, word_timestamps, index):
    font_path, font_name = _ensure_pro_font()

    start = max(0.0, float(clip_data.get("start", 0)))
    end = float(clip_data.get("end", start + 25))
    duration = max(8.0, min(42.0, end - start))

    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "hype"))).lower() or "hype"
    facecam_box = _parse_facecam_box(clip_data.get("facecam_box", None))
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _clean_text(clip_data.get("title_text", "")).upper()

    # Peak moment timestamp (relative to clip start)
    peak_raw = clip_data.get("peak_sec", clip_data.get("bw_drop_sec", None))
    try:
        peak_sec = float(peak_raw) if peak_raw is not None else None
        if peak_sec is not None and (peak_sec < 2.0 or peak_sec > duration - 1.0):
            peak_sec = None
    except Exception:
        peak_sec = None

    is_split = (facecam_box is not None)
    output_file = f"MAG73_{edit_type.upper()}_Clip_{index + 1}.mp4"

    # Tasteful Audio Policy:
    # - 'clean' -> zero BGM, zero SFX
    # - 'funny' -> zero BGM (keep comedy timing raw), optional subtle SFX only at peak
    # - 'aura'/'hype'/'expose' -> subtle BGM with smooth fade-in/out; SFX only for 'aura' at peak
    bgm_file = None
    sfx_file = None
    if edit_type in ("aura", "hype", "expose"):
        bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}")
    if edit_type in ("aura", "funny") and peak_sec is not None:
        sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}")

    ass_file = generate_pro_captions(word_timestamps, start, start + duration, font_name, is_split, f"cap_{index}.ass")

    # 1. Base Layout
    layout_graph = _build_layout_graph(facecam_box, focus_x)

    # 2. Clean, Studio Color Grading (No cheap over-the-top filters)
    if edit_type == "aura":
        post_vf = ["eq=contrast=1.10:saturation=0.95:brightness=-0.02", "vignette=PI/7"]
        if peak_sec is not None:
            post_vf.append(f"hue=s=0:enable='gte(t,{peak_sec:.2f})'")
            post_vf.append(f"eq=contrast=1.18:enable='gte(t,{peak_sec:.2f})'")
    elif edit_type == "hype":
        post_vf = ["eq=contrast=1.07:saturation=1.12"]
    elif edit_type == "expose":
        post_vf = ["eq=contrast=1.06:saturation=1.02", "vignette=PI/8"]
    else:
        post_vf = ["eq=contrast=1.04:saturation=1.05"]

    # Sleek modern dark translucent Hook Banner (3.5s, never ugly red)
    if title_text and edit_type != "clean":
        post_vf.append(
            f"drawtext=fontfile={font_path}:text='{title_text}':fontcolor=white:fontsize=46:"
            f"box=1:boxcolor=0x0F1115@0.82:boxborderw=18:x=(w-text_w)/2:y=150:enable='between(t,0.1,3.6)'"
        )

    if ass_file and os.path.exists(ass_file):
        post_vf.append(f"ass={ass_file}:fontsdir=.")

    video_chain = f"{layout_graph}[base]{','.join(post_vf)}[v];"
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    # 3. Studio Audio Mastering (Crystal Clear Voice + Subtle Smooth BGM)
    voice_chain = "[0:a]highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.15[voice];"
    bgm_vol = "0.20" if edit_type == "aura" else ("0.15" if edit_type == "hype" else "0.11")
    fade_out_start = max(0.5, duration - 1.4)

    if bgm_file and sfx_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file, "-i", sfx_file])
        sfx_ms = int(peak_sec * 1000)
        fc = (
            f"{video_chain}{voice_chain}"
            f"[1:a]atrim=0:{duration:.2f},afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_start:.2f}:d=1.4,volume={bgm_vol}[bgm];"
            f"[2:a]atrim=0:1.5,afade=t=out:st=1.0:d=0.5,adelay={sfx_ms}|{sfx_ms},volume=0.38[sfx];"
            f"[voice][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=2:normalize=0[a]"
        )
    elif bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        fc = (
            f"{video_chain}{voice_chain}"
            f"[1:a]atrim=0:{duration:.2f},afade=t=in:st=0:d=1.0,afade=t=out:st={fade_out_start:.2f}:d=1.4,volume={bgm_vol}[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
    elif sfx_file:
        cmd.extend(["-i", sfx_file])
        sfx_ms = int(peak_sec * 1000)
        fc = (
            f"{video_chain}{voice_chain}"
            f"[1:a]atrim=0:1.5,afade=t=out:st=1.0:d=0.5,adelay={sfx_ms}|{sfx_ms},volume=0.38[sfx];"
            f"[voice][sfx]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
    else:
        fc = f"{video_chain}{voice_chain}[voice]anull[a]"

    cmd.extend([
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        output_file
    ])

    print(f"[MAG73 Pro Editor] Rendering {output_file} | Style: {edit_type} | Peak: {peak_sec} | Split: {is_split}")
    subprocess.run(cmd, check=True)

    # 4. Guaranteed Cover Thumbnail (.jpg) with -update 1 fix
    os.makedirs("output_clips", exist_ok=True)
    cover_path = os.path.join("output_clips", output_file.replace(".mp4", ".jpg"))
    thumb_sec = min(2.0, duration / 2.0)
    subprocess.run([
        "ffmpeg", "-y", "-ss", f"{thumb_sec:.2f}", "-i", output_file,
        "-frames:v", "1", "-update", "1", "-q:v", "3", cover_path
    ], check=False)

    return output_file
