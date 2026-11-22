import os
import re
import subprocess
import requests

FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PRO_FONT_FILE = "Montserrat-ExtraBold.ttf"
PRO_FONT_URL = "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf"

def _ensure_pro_font():
    """Pro Montserrat-ExtraBold font download karta hai"""
    if not os.path.exists(PRO_FONT_FILE):
        try:
            r = requests.get(PRO_FONT_URL, timeout=15)
            if r.status_code == 200 and len(r.content) > 50000:
                with open(PRO_FONT_FILE, "wb") as f:
                    f.write(r.content)
                print("[MAG73 Font] Loaded Montserrat-ExtraBold!")
        except Exception as e:
            print(f"[MAG73 Font] Using fallback font: {e}")

    if os.path.exists(PRO_FONT_FILE):
        return PRO_FONT_FILE, "Montserrat ExtraBold"
    return FALLBACK_FONT, "DejaVu Sans"

def _fetch_audio(query, out_prefix):
    """Sirf tabhi BGM/SFX download karta hai jab query non-empty ho"""
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
    """Clean, accurate Hinglish/English captions (Split-screen mein center seam par)"""
    clip_words = [w for w in words if w.get("start", 0) >= clip_start and w.get("end", 0) <= clip_end]
    if not clip_words:
        return None

    margin_v = 900 if is_split else 360
    font_size = 76 if is_split else 82

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{color_hex},&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,1,6,3,2,60,60,{margin_v},1

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
        anim = r"{\fscx88\fscy88\t(0,65,\fscx106\fscy106)\t(65,130,\fscx100\fscy100)}" + clean_txt
        events.append(f"Dialogue: 0,{_format_ass_time(w_start)},{_format_ass_time(w_end)},Default,,0,0,0,,{anim}")

    if not events:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    return ass_path

def _build_layout_graph(layout, facecam_pos, focus_x):
    """
    split_facecam: Top 1080x960 Gameplay + Bottom 1080x960 Real Human Facecam
    full_vertical: Clean 9:16 framing
    """
    if layout == "split_facecam" and facecam_pos in ("bottom_right", "bottom_left", "top_right", "top_left"):
        if facecam_pos == "bottom_right":
            cx, cy = "iw*0.72", "ih*0.66"
        elif facecam_pos == "bottom_left":
            cx, cy = "0", "ih*0.66"
        elif facecam_pos == "top_right":
            cx, cy = "iw*0.72", "0"
        else:
            cx, cy = "0", "0"

        return (
            f"[0:v]split=2[game_src][cam_src];"
            f"[game_src]scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[top];"
            f"[cam_src]crop=iw*0.28:ih*0.34:{cx}:{cy},scale=1080:960:force_original_aspect_ratio=increase,crop=1080:960,setsar=1[bot];"
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
    end = float(clip_data.get("end", start + 25))
    duration = max(8.0, min(55.0, end - start))

    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "clean"))).lower() or "clean"
    layout = str(clip_data.get("layout", "full_vertical")).lower()
    facecam_pos = str(clip_data.get("facecam_pos", "none")).lower()
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _ascii_only(str(clip_data.get("title_text", ""))).upper()
    caption_color = str(clip_data.get("caption_color", "&H0000FFFF"))

    # B&W Drop sirf aura/funny mein jab AI ne explicit bw_drop_sec diya ho
    bw_drop = clip_data.get("bw_drop_sec", None)
    try:
        bw_drop = float(bw_drop) if (bw_drop is not None and edit_type in ("aura", "funny")) else None
        if bw_drop is not None and (bw_drop < 2.0 or bw_drop > duration - 1.0):
            bw_drop = None
    except Exception:
        bw_drop = None

    is_split = (layout == "split_facecam" and facecam_pos != "none")
    output_file = f"MAG73_{edit_type.upper()}_Clip_{index + 1}.mp4"

    # NO forced default BGM — sirf wahi download karo jo AI ne decide kiya hai
    bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}")
    sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}")
    ass_file = generate_captions(word_timestamps, start, start + duration, caption_color, font_name, is_split, f"cap_{index}.ass")

    # 1. Base Layout
    layout_graph = _build_layout_graph(layout, facecam_pos, focus_x)

    # 2. Style-based Post-Processing
    if edit_type == "aura":
        post_vf = ["eq=contrast=1.10:saturation=1.12"]
    elif edit_type == "clutch":
        post_vf = ["eq=contrast=1.08:saturation=1.14"]
    else:
        post_vf = ["eq=contrast=1.03:saturation=1.05"]

    if bw_drop is not None:
        post_vf.append(f"hue=s=0:enable='gte(t,{bw_drop:.2f})'")
        post_vf.append(f"eq=contrast=1.20:enable='gte(t,{bw_drop:.2f})'")

    if title_text:
        if edit_type == "funny":
            banner_bg = "0xC81E1E@0.90"
        elif edit_type == "aura":
            banner_bg = "0x0B0D12@0.90"
        elif edit_type == "clutch":
            banner_bg = "0x1E293B@0.88"
        else:
            banner_bg = "0x111318@0.78"

        post_vf.append(
            f"drawtext=fontfile={font_path}:text='{title_text}':fontcolor=white:fontsize=46:"
            f"box=1:boxcolor={banner_bg}:boxborderw=18:x=(w-text_w)/2:y=140:enable='between(t,0,4.0)'"
        )

    if ass_file and os.path.exists(ass_file):
        post_vf.append(f"ass={ass_file}:fontsdir=.")

    video_chain = f"{layout_graph}[base]{','.join(post_vf)}[v];"
    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    # 3. Clean Audio Mixing (Voice always clear; BGM volume tuned by style)
    bgm_vol = "0.26" if edit_type in ("aura", "clutch") else "0.16"

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
            f"[voice][sfx]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[a]"
        )
    else:
        fc = f"{video_chain}[0:a]anull[a]"

    cmd.extend([
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        output_file
    ])

    print(f"[MAG73 Pro Editor] Rendering {output_file} | Style: {edit_type} | Layout: {layout} | B&W Drop: {bw_drop}")
    subprocess.run(cmd, check=True)

    # 4. Save Cover Thumbnail (.jpg) in output_clips/
    os.makedirs("output_clips", exist_ok=True)
    cover_path = os.path.join("output_clips", output_file.replace(".mp4", ".jpg"))
    subprocess.run([
        "ffmpeg", "-y", "-ss", "2.0", "-i", output_file,
        "-vframes", "1", "-q:v", "4", cover_path
    ], check=False)

    return output_file
