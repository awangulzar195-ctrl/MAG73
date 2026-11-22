import os
import re
import subprocess
import requests

FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PRO_FONT_FILE = "Poppins-Black.ttf"
PRO_FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/poppins/Poppins-Black.ttf"

def _ensure_pro_font():
    """Thick, viral-style Poppins-Black font download karta hai"""
    if not os.path.exists(PRO_FONT_FILE):
        try:
            r = requests.get(PRO_FONT_URL, timeout=15)
            if r.status_code == 200 and len(r.content) > 50000:
                with open(PRO_FONT_FILE, "wb") as f:
                    f.write(r.content)
                print("[MAG73 Font] Loaded Poppins-Black!")
        except Exception as e:
            print(f"[MAG73 Font] Using fallback font: {e}")

    if os.path.exists(PRO_FONT_FILE):
        return PRO_FONT_FILE, "Poppins Black"
    return FALLBACK_FONT, "DejaVu Sans"

def _fetch_audio(query, out_prefix):
    """Sirf tabhi BGM/SFX download karta hai jab AI ne non-empty query di ho"""
    query = (query or "").strip()
    if not query:
        return None

    out_file = f"{out_prefix}.mp3"
    if os.path.exists(out_file):
        return out_file

    q = query if query.startswith("ytsearch") else f"ytsearch1:{query}"
    cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3",
        "--max-filesize", "15M",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-o", f"{out_prefix}.%(ext)s"
    ]
    if os.path.exists("cookies.txt"):
        cmd.extend(["--cookies", "cookies.txt"])
    cmd.append(q)

    subprocess.run(cmd, check=False)
    if os.path.exists(out_file):
        print(f"[MAG73 Audio] Ready: {out_file}")
        return out_file
    return None

def _format_ass_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int((seconds - int(seconds)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def _ascii_only(text):
    return re.sub(r"[^A-Za-z0-9 !?@#,.-]", "", text).strip()

def generate_captions(words, clip_start, clip_end, color_hex, font_name, is_split, ass_path):
    """Bold, punchy Hinglish/English captions (Split-screen mein center border par)"""
    clip_words = [w for w in words if w.get("start", 0) >= clip_start and w.get("end", 0) <= clip_end]
    if not clip_words:
        return None

    margin_v = 910 if is_split else 340
    font_size = 78 if is_split else 88

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{color_hex},&H00FFFFFF,&H00000000,&H99000000,-1,0,0,0,100,100,0,0,1,7,4,2,55,55,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for i in range(0, len(clip_words), 2):
        chunk = clip_words[i:i+2]
        w_start = max(0, chunk[0]["start"] - clip_start)
        w_end = max(w_start + 0.25, chunk[-1]["end"] - clip_start)
        clean_txt = _ascii_only(" ".join(w.get("word", "").strip().upper() for w in chunk))
        if not clean_txt:
            continue
        anim = r"{\fscx85\fscy85\t(0,55,\fscx108\fscy108)\t(55,115,\fscx100\fscy100)}" + clean_txt
        events.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,,0,0,0,,{anim}")

    if not events:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return ass_path

def _parse_facecam_box(box):
    """Validates normalized [x, y, w, h] facecam box from Gemini Vision"""
    if not isinstance(box, list) or len(box) != 4:
        return None
    try:
        x, y, w, h = [float(v) for v in box]
        if w < 0.08 or h < 0.08 or w > 0.65 or h > 0.65:
            return None
        x = max(0.0, min(1.0 - w, x))
        y = max(0.0, min(1.0 - h, y))
        return (x, y, w, h)
    except Exception:
        return None

def _build_layout_graph(facecam_box, focus_x):
    """
    Agar valid real human facecam_box hai -> Top 1080x960 Gameplay + Bottom 1080x960 Exact Facecam
    Agar facecam_box None hai -> Clean 1080x1920 full vertical framing
    """
    if facecam_box is not None:
        fx, fy, fw, fh = facecam_box
        return (
            f"[0:v]split=2[game_src][cam_src];"
            f"[game_src]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[top];"
            f"[cam_src]crop=iw*{fw:.4f}:ih*{fh:.4f}:iw*{fx:.4f}:ih*{fy:.4f},"
            f"scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[bot];"
            f"[top][bot]vstack=inputs=2[base];"
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

    start = float(clip_data.get("start", 0))
    end = float(clip_data.get("end", start + 22))
    duration = max(6.0, min(38.0, end - start))

    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "clean"))).lower() or "clean"
    facecam_box = _parse_facecam_box(clip_data.get("facecam_box", None))
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _ascii_only(str(clip_data.get("title_text", ""))).upper()
    caption_color = str(clip_data.get("caption_color", "&H0000FFFF"))

    # B&W Beat Drop sirf aura/funny mein jab AI ne explicit bw_drop_sec diya ho
    bw_drop = clip_data.get("bw_drop_sec", None)
    try:
        bw_drop = float(bw_drop) if (bw_drop is not None and edit_type in ("aura", "funny")) else None
        if bw_drop is not None and (bw_drop < 2.0 or bw_drop > duration - 1.0):
            bw_drop = None
    except Exception:
        bw_drop = None

    is_split = (facecam_box is not None)
    output_file = f"MAG73_{edit_type.upper()}_Clip_{index + 1}.mp4"

    # Clean style mein koi forced BGM/SFX/Banner nahi
    bgm_query = "" if edit_type == "clean" else clip_data.get("bgm_query", "")
    sfx_query = "" if edit_type == "clean" else clip_data.get("sfx_query", "")

    bgm_file = _fetch_audio(bgm_query, f"bgm_{index}")
    sfx_file = _fetch_audio(sfx_query, f"sfx_{index}")
    ass_file = generate_captions(word_timestamps, start, start + duration, caption_color, font_name, is_split, f"cap_{index}.ass")

    # 1. Base Layout
    layout_graph = _build_layout_graph(facecam_box, focus_x)

    # 2. 4 Alag Edit Styles
    if edit_type == "aura":
        post_vf = ["eq=contrast=1.14:saturation=0.92:brightness=-0.03", "vignette=PI/6"]
    elif edit_type == "hype":
        post_vf = ["eq=contrast=1.10:saturation=1.18"]
    elif edit_type == "funny":
        post_vf = ["eq=contrast=1.06:saturation=1.08"]
    else:
        post_vf = ["eq=contrast=1.02:saturation=1.03"]

    if bw_drop is not None:
        post_vf.append(f"hue=s=0:enable='gte(t,{bw_drop:.2f})'")
        post_vf.append(f"eq=contrast=1.22:enable='gte(t,{bw_drop:.2f})'")

    # Title banner sirf tab jab AI ne title_text diya ho aur style 'clean' na ho
    if title_text and edit_type != "clean":
        if edit_type == "funny":
            banner_bg = "0xC81E1E@0.90"
        elif edit_type == "aura":
            banner_bg = "0x0B0D12@0.92"
        else:
            banner_bg = "0x1E293B@0.88"

        post_vf.append(
            f"drawtext=fontfile={font_path}:text='{title_text}':fontcolor=white:fontsize=46:"
            f"box=1:boxcolor={banner_bg}:boxborderw=18:x=(w-text_w)/2:y=140:enable='between(t,0,3.8)'"
        )

    if ass_file and os.path.exists(ass_file):
        post_vf.append(f"ass={ass_file}:fontsdir=.")

    video_chain = f"{layout_graph}[base]{','.join(post_vf)}[v];"
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    # 3. Clean Audio Mixing
    bgm_vol = "0.26" if edit_type in ("aura", "hype") else "0.15"

    if bgm_file and sfx_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file, "-i", sfx_file])
        sfx_delay_ms = int(bw_drop * 1000) if bw_drop is not None else 0
        sfx_filter = f"atrim=0:1.8,adelay={sfx_delay_ms}|{sfx_delay_ms},volume=0.55" if sfx_delay_ms > 0 else "atrim=0:1.8,volume=0.50"
        fc = (
            f"{video_chain}"
            f"[0:a]volume=1.15[voice];"
            f"[1:a]volume={bgm_vol}[bgm];"
            f"[2:a]{sfx_filter}[sfx];"
            f"[voice][bgm][sfx]amix=inputs=3:duration=first:dropout_transition=2:normalize=0[a]"
        )
    elif bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        fc = (
            f"{video_chain}"
            f"[0:a]volume=1.15[voice];"
            f"[1:a]volume={bgm_vol}[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:normalize=0[a]"
        )
    elif sfx_file:
        cmd.extend(["-i", sfx_file])
        sfx_delay_ms = int(bw_drop * 1000) if bw_drop is not None else 0
        sfx_filter = f"atrim=0:1.8,adelay={sfx_delay_ms}|{sfx_delay_ms},volume=0.55" if sfx_delay_ms > 0 else "atrim=0:1.8,volume=0.50"
        fc = (
            f"{video_chain}"
            f"[0:a]volume=1.15[voice];"
            f"[1:a]{sfx_filter}[sfx];"
            f"[voice][sfx]amix=inputs=2:duration=first:normalize=0[a]"
        )
    else:
        fc = f"{video_chain}[0:a]anull[a]"

    cmd.extend([
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        output_file
    ])

    print(f"[MAG73 Pro Editor] Rendering {output_file} | Style: {edit_type} | FacecamBox: {facecam_box} | B&W Drop: {bw_drop}")
    subprocess.run(cmd, check=True)

    # 4. Save Cover Thumbnail (.jpg) in output_clips/
    os.makedirs("output_clips", exist_ok=True)
    cover_path = os.path.join("output_clips", output_file.replace(".mp4", ".jpg"))
    subprocess.run([
        "ffmpeg", "-y", "-ss", "2.0", "-i", output_file,
        "-vframes", "1", "-q:v", "4", cover_path
    ], check=False)

    return output_file
