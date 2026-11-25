import os
import re
import json
import shutil
import subprocess
import requests

FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PRO_FONT_FILE = "Montserrat-ExtraBold.ttf"
PRO_FONT_URL = "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf"

STYLE_PALETTE = {
    "vlog":        {"hl": "&H0000D7FF&", "box": "0x1A140A@0.88", "title_col": "0xFFD700", "pbar": "0xF59E0B"},
    "informative": {"hl": "&H00FFE500&", "box": "0x0B1524@0.88", "title_col": "0x38BDF8", "pbar": "0x38BDF8"},
    "gaming":      {"hl": "&H0055FF00&", "box": "0x0B1A12@0.90", "title_col": "0x4ADE80", "pbar": "0x4ADE80"},
    "clash":       {"hl": "&H00FFFF00&", "box": "0x0F172A@0.90", "title_col": "0x22D3EE", "pbar": "0x22D3EE"},
    "funny":       {"hl": "&H0000EAFF&", "box": "0x1F1505@0.90", "title_col": "0xFACC15", "pbar": "0xFACC15"},
    "aura":        {"hl": "&H003333FF&", "box": "0x180707@0.92", "title_col": "0xF87171", "pbar": "0xEF4444"},
    "drama":       {"hl": "&H000066FF&", "box": "0x1C0D08@0.90", "title_col": "0xFB923C", "pbar": "0xF97316"},
    "clean":       {"hl": "&H0000E5FF&", "box": "0x0F1115@0.80", "title_col": "0xFFFFFF", "pbar": "0x6366F1"},
}


def _get_plugin_config():
    defaults = {
        "caption_lang": "hinglish",
        "bgm_enabled": True,
        "sfx_enabled": True,
        "banner_enabled": True,
        "custom_ffmpeg": "",
        "custom_font_url": "",
        "external_plugin_url": "",
    }
    raw = os.getenv("PLUGIN_CONFIG", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                defaults.update(parsed)
        except Exception:
            pass
    return defaults


def _ensure_pro_font(custom_font_url=""):
    target_file = PRO_FONT_FILE
    font_url = PRO_FONT_URL
    font_family = "Montserrat"

    custom_font_url = (custom_font_url or "").strip()
    if custom_font_url.startswith("http") and ".ttf" in custom_font_url.lower():
        target_file = "CustomPluginFont.ttf"
        font_url = custom_font_url

    if not os.path.exists(target_file):
        try:
            r = requests.get(font_url, timeout=15)
            if r.status_code == 200 and len(r.content) > 20000:
                with open(target_file, "wb") as f:
                    f.write(r.content)
        except Exception as e:
            print(f"[MAG73 Font] Download warning: {e}")

    if not os.path.exists(target_file) and target_file != PRO_FONT_FILE:
        target_file = PRO_FONT_FILE
        if not os.path.exists(target_file):
            try:
                r = requests.get(PRO_FONT_URL, timeout=15)
                if r.status_code == 200 and len(r.content) > 50000:
                    with open(target_file, "wb") as f:
                        f.write(r.content)
            except Exception:
                pass

    if os.path.exists(target_file):
        try:
            font_dir = os.path.expanduser("~/.local/share/fonts")
            os.makedirs(font_dir, exist_ok=True)
            shutil.copy(target_file, os.path.join(font_dir, os.path.basename(target_file)))
            subprocess.run(["fc-cache", "-f"], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            out = subprocess.check_output(
                ["fc-query", "--format=%{family[0]}", target_file],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if out:
                font_family = out
        except Exception:
            pass
        return target_file, font_family
    return FALLBACK_FONT, "DejaVu Sans"


def _probe_video_dims(video_path):
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", video_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        w, h = out.split("x")
        return int(w), int(h)
    except Exception:
        return 1280, 720


def _fetch_audio(query, out_prefix):
    """Uses full node EJS + cookies + fallback clients so BGM/SFX actually download!"""
    query = (query or "").strip()
    if not query:
        return None
    out_file = f"{out_prefix}.mp3"
    if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
        return out_file

    q = query if query.startswith("ytsearch") else f"ytsearch1:{query}"
    strategies = [
        [],
        ["--extractor-args", "youtube:player_client=web,mweb"],
        ["--extractor-args", "youtube:player_client=ios,web"],
    ]
    for extra in strategies:
        cmd = [
            "yt-dlp", "-x", "--audio-format", "mp3",
            "--max-filesize", "12M", "--no-playlist",
            "--js-runtimes", "node",
            "--remote-components", "ejs:github",
            "-o", f"{out_prefix}.%(ext)s",
        ]
        if os.path.exists("cookies.txt"):
            cmd.extend(["--cookies", "cookies.txt"])
        cmd.extend(extra)
        cmd.append(q)
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
            print(f"[MAG73 Audio] Fetched {out_file} ({os.path.getsize(out_file)} bytes)")
            return out_file
    print(f"[MAG73 Audio] Fetch skipped for query: {query}")
    return None


def _generate_whoosh_sfx(out_path):
    """Crisp opening transition whoosh generated locally via FFmpeg."""
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anoisesrc=color=pink:duration=0.45:sample_rate=44100",
                "-af", "bandpass=f=900:width_type=h:w=1200,afade=t=in:st=0:d=0.16,afade=t=out:st=0.20:d=0.25,volume=0.65",
                "-c:a", "libmp3lame", "-q:a", "4", out_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if os.path.exists(out_path) and os.path.getsize(out_path) > 1500:
            return out_path
    except Exception:
        pass
    return None


def _generate_synth_sfx(out_path, edit_type):
    """Guaranteed punchy climax bass-boom / comic pop SFX."""
    try:
        if edit_type == "funny":
            expr = "sin(2*PI*(210*exp(-7*t)+60)*t)*exp(-4.5*t)*0.85"
            dur = "0.55"
        else:
            expr = "sin(2*PI*(115*exp(-3.0*t)+36)*t)*exp(-2.4*t)*0.90"
            dur = "0.95"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"aevalsrc={expr}:d={dur}:s=44100",
                "-c:a", "libmp3lame", "-q:a", "4", out_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if os.path.exists(out_path) and os.path.getsize(out_path) > 2000:
            return out_path
    except Exception:
        pass
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
    text = re.sub(r"[^A-Za-z0-9 !?@#,.-]", "", str(text or ""))
    text = text.replace(":", "").replace("'", "")
    return re.sub(r"\s+", " ", text).strip()


def generate_pro_captions(words, clip_start, clip_end, font_name, edit_type, is_wide_blur, ass_path):
    """Big, bold CapCut/Hormozi-style pop captions placed cleanly ABOVE original bottom subtitles."""
    raw_clip_words = []
    for w in (words or []):
        ws = float(w.get("start", 0))
        we = float(w.get("end", ws + 0.25))
        txt = _clean_text(w.get("word", "")).upper()
        if not txt:
            continue
        if we >= clip_start and ws <= clip_end:
            rel_s = max(0.0, ws - clip_start)
            rel_e = min(clip_end - clip_start, we - clip_start)
            if rel_e - rel_s > 1.0:
                rel_e = rel_s + 0.85
            if rel_e - rel_s < 0.12:
                rel_e = rel_s + 0.22
            raw_clip_words.append({"word": txt, "start": rel_s, "end": rel_e})

    if not raw_clip_words:
        print(f"[MAG73 Captions] WARNING: 0 words matched clip [{clip_start:.1f}s - {clip_end:.1f}s] out of {len(words or [])} total words.")
        return None

    chunks = []
    current = []
    for w in raw_clip_words:
        if not current:
            current.append(w)
            continue
        gap = w["start"] - current[-1]["end"]
        curr_len = sum(len(x["word"]) + 1 for x in current)
        if len(current) >= 3 or (curr_len + len(w["word"]) > 15) or gap > 0.55:
            chunks.append(current)
            current = [w]
        else:
            current.append(w)
    if current:
        chunks.append(current)

    pal = STYLE_PALETTE.get(edit_type, STYLE_PALETTE["vlog"])
    hl_color = pal["hl"]
    # Placed cleanly above any burned-in bottom subtitles (MarginV=480)
    margin_v = 480 if not is_wide_blur else 440
    font_size = 86 if edit_type in ("funny", "gaming", "aura") else 80

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,{hl_color},&H00000000,&HB0000000,-1,0,0,0,100,100,1,0,1,9,4,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for chunk in chunks:
        for active_idx, active_w in enumerate(chunk):
            ev_start = active_w["start"]
            if active_idx + 1 < len(chunk):
                ev_end = min(active_w["end"] + 0.08, chunk[active_idx + 1]["start"])
                if ev_end <= ev_start:
                    ev_end = chunk[active_idx + 1]["start"]
            else:
                ev_end = active_w["end"] + 0.10

            if ev_end - ev_start < 0.08:
                ev_end = ev_start + 0.16

            styled_parts = []
            for idx, w_obj in enumerate(chunk):
                if idx == active_idx:
                    styled_parts.append(f"{{\\c{hl_color}\\fscx114\\fscy114}}{w_obj['word']}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}")
                else:
                    styled_parts.append(w_obj["word"])

            line_text = " ".join(styled_parts)
            if active_idx == 0:
                line_text = r"{\fscx84\fscy84\t(0,65,\fscx106\fscy106)\t(65,120,\fscx100\fscy100)}" + line_text

            events.append(
                f"Dialogue: 0,{_format_ass_time(ev_start)},{_format_ass_time(ev_end)},Default,,0,0,0,,{line_text}"
            )

    if not events:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(events))
    print(f"[MAG73 Captions] Generated {len(events)} animated caption events in {ass_path}.")
    return ass_path


def _build_layout_and_motion(in_w, in_h, focus_x, duration, edit_type, peak_sec):
    """
    REAL CapCut-style dynamic rhythm:
    - Opening Hook Punch-In (0.0s - 0.35s)
    - Alternating Jump-Cut Zooms every 4 seconds (1.0x <-> 1.15x) so no clip is ever static!
    - Climax Impact Hard-Zoom + Camera Shake at peak_sec!
    """
    dur_frames = max(30, int(duration * 30))
    pk = float(peak_sec) if peak_sec is not None else max(3.0, duration * 0.5)
    is_wide_blur = (edit_type in ("gaming", "clash")) and (in_w > in_h)

    if is_wide_blur:
        border_col = "0x4ADE80" if edit_type == "gaming" else "0x22D3EE"
        base_graph = (
            f"[0:v]fps=30,split=2[bg_src][fg_src];"
            f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"boxblur=20:5,eq=brightness=-0.20:saturation=1.15[bg];"
            f"[fg_src]scale=1080:-2,pad=1080:ih+8:0:4:color={border_col}[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[framed];"
        )
    else:
        crop_x = "(iw-1080)*0.18" if focus_x == "left" else ("(iw-1080)*0.82" if focus_x == "right" else "(iw-1080)/2")
        base_graph = (
            f"[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:{crop_x}:(ih-1920)/2,setsar=1[framed];"
        )

    # Active rhythmic jump-zooms + opening hook snap + climax impact shake
    if edit_type == "funny":
        z_expr = f"1.02+0.20*max(0,1-on/10)+0.14*gt(mod(on,210),105)+0.22*between(on/30,{pk:.2f},{pk+1.7:.2f})"
        x_expr = f"clip(iw/2-(iw/zoom/2)+18*sin(on*3.1)*between(on/30,{pk:.2f},{pk+0.40:.2f}),0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+18*cos(on*3.5)*between(on/30,{pk:.2f},{pk+0.40:.2f}),0,ih-ih/zoom)"
    elif edit_type == "aura":
        z_expr = f"1.04+0.18*max(0,1-on/10)+0.10*min(1,on/{dur_frames})+0.20*between(on/30,{pk:.2f},{pk+2.4:.2f})"
        x_expr = f"clip(iw/2-(iw/zoom/2)+24*sin(on*2.9)*between(on/30,{pk:.2f},{pk+0.48:.2f}),0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+24*cos(on*3.4)*between(on/30,{pk:.2f},{pk+0.48:.2f}),0,ih-ih/zoom)"
    elif edit_type in ("gaming", "clash"):
        z_expr = f"1.02+0.16*max(0,1-on/10)+0.12*gt(mod(on,240),120)+0.18*between(on/30,{pk:.2f},{pk+1.5:.2f})"
        x_expr = f"clip(iw/2-(iw/zoom/2)+18*sin(on*3.0)*between(on/30,{pk:.2f},{pk+0.42:.2f}),0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+18*cos(on*3.4)*between(on/30,{pk:.2f},{pk+0.42:.2f}),0,ih-ih/zoom)"
    elif edit_type == "drama":
        z_expr = f"1.02+0.14*max(0,1-on/10)+0.14*min(1,on/{dur_frames})+0.14*between(on/30,{pk:.2f},{pk+2.0:.2f})"
        x_expr = f"clip(iw/2-(iw/zoom/2)+12*sin(on*2.8)*between(on/30,{pk:.2f},{pk+0.35:.2f}),0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+12*cos(on*3.2)*between(on/30,{pk:.2f},{pk+0.35:.2f}),0,ih-ih/zoom)"
    elif edit_type in ("vlog", "informative"):
        z_expr = f"1.02+0.18*max(0,1-on/12)+0.12*gt(mod(on,240),120)"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        z_expr = f"1.00+0.08*min(1,on/{dur_frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    motion_graph = (
        f"[framed]zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=1080x1920:fps=30,"
        f"setpts=PTS-STARTPTS,setsar=1[base];"
    )
    return base_graph + motion_graph, is_wide_blur


def render_pro_short(video_path, clip_data, word_timestamps, index):
    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    bgm_enabled = bool(plugin_cfg.get("bgm_enabled", True))
    sfx_enabled = bool(plugin_cfg.get("sfx_enabled", True))
    banner_enabled = bool(plugin_cfg.get("banner_enabled", True))
    custom_ffmpeg = str(plugin_cfg.get("custom_ffmpeg", "")).strip()
    custom_font_url = str(plugin_cfg.get("custom_font_url", "")).strip()

    font_path, font_name = _ensure_pro_font(custom_font_url)
    in_w, in_h = _probe_video_dims(video_path)

    start = max(0.0, float(clip_data.get("start", 0)))
    end = float(clip_data.get("end", start + 18))
    duration = max(8.0, min(36.0, end - start))

    orig_start = int(float(clip_data.get("orig_start", start)))
    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "vlog"))).lower() or "vlog"
    if edit_type not in STYLE_PALETTE:
        edit_type = "vlog"

    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _clean_text(clip_data.get("title_text", "")).upper() if banner_enabled else ""

    peak_raw = clip_data.get("peak_sec", clip_data.get("bw_drop_sec", None))
    try:
        peak_sec = float(peak_raw) if peak_raw is not None else max(3.0, duration * 0.45)
        if peak_sec < 1.5 or peak_sec > duration - 1.2:
            peak_sec = max(2.0, duration * 0.45)
    except Exception:
        peak_sec = max(2.0, duration * 0.45)

    # Unique filename with timestamp so parallel clips NEVER collide on "Clip 1"
    mm, ss = divmod(max(0, orig_start), 60)
    output_file = f"MAG73_{edit_type.upper()}_{mm:02d}m{ss:02d}s_Clip_{index + 1}.mp4"

    bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}") if (bgm_enabled and edit_type != "clean") else None
    whoosh_file = _generate_whoosh_sfx(f"whoosh_{index}.mp3") if (sfx_enabled and edit_type != "clean") else None

    sfx_file = None
    if sfx_enabled and edit_type in ("aura", "funny", "gaming", "clash", "drama"):
        sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}")
        if not sfx_file:
            sfx_file = _generate_synth_sfx(f"synth_sfx_{index}.mp3", edit_type)

    layout_graph, is_wide_blur = _build_layout_and_motion(in_w, in_h, focus_x, duration, edit_type, peak_sec)

    ass_file = None
    if caption_lang != "off":
        ass_file = generate_pro_captions(
            word_timestamps, start, start + duration, font_name, edit_type, is_wide_blur, f"cap_{index}.ass"
        )

    # Distinct visual grading + opening flash + climax flash/impact per style
    if edit_type == "vlog":
        post_vf = [
            "eq=contrast=1.10:saturation=1.24:brightness=0.02",
            "colorbalance=rs=0.04:gs=0.01:bs=-0.03",
            "eq=brightness=0.22:enable='between(t,0.0,0.10)'",
        ]
    elif edit_type == "informative":
        post_vf = [
            "eq=contrast=1.08:saturation=1.12:brightness=0.01",
            "unsharp=5:5:0.45:5:5:0.0",
        ]
    elif edit_type == "funny":
        post_vf = [
            "eq=contrast=1.12:saturation=1.22:brightness=0.02",
            f"eq=brightness=0.28:enable='between(t,0.0,0.10)+between(t,{peak_sec:.2f},{peak_sec+0.10:.2f})'",
        ]
    elif edit_type in ("gaming", "clash"):
        post_vf = [
            "eq=contrast=1.16:saturation=1.20",
            f"eq=brightness=0.32:enable='between(t,0.0,0.10)+between(t,{peak_sec:.2f},{peak_sec+0.11:.2f})'",
        ]
    elif edit_type == "aura":
        post_vf = [
            "eq=contrast=1.16:saturation=0.86:brightness=-0.02",
            "vignette=PI/6",
            f"eq=brightness=0.40:enable='between(t,0.0,0.10)+between(t,{peak_sec:.2f},{peak_sec+0.12:.2f})'",
            f"hue=s=0:enable='gte(t,{peak_sec+0.12:.2f})'",
            f"eq=contrast=1.26:brightness=-0.03:enable='gte(t,{peak_sec+0.12:.2f})'",
        ]
    elif edit_type == "drama":
        post_vf = [
            "eq=contrast=1.14:saturation=0.95:brightness=-0.01",
            "vignette=PI/6",
            f"eq=brightness=0.25:enable='between(t,{peak_sec:.2f},{peak_sec+0.10:.2f})'",
        ]
    else:
        post_vf = ["eq=contrast=1.05:saturation=1.05"]

    if custom_ffmpeg and ";" not in custom_ffmpeg and "[" not in custom_ffmpeg:
        post_vf.append(custom_ffmpeg)

    pal = STYLE_PALETTE.get(edit_type, STYLE_PALETTE["vlog"])
    if title_text and edit_type != "clean":
        banner_y = 210 if is_wide_blur else 175
        post_vf.append(
            f"drawtext=fontfile={font_path}:text='{title_text}':fontcolor={pal['title_col']}:fontsize=50:"
            f"borderw=4:bordercolor=black:box=1:boxcolor={pal['box']}:boxborderw=22:"
            f"x=(w-text_w)/2:y={banner_y}:enable='between(t,0.10,3.40)'"
        )

    if ass_file and os.path.exists(ass_file):
        post_vf.append(f"ass={ass_file}:fontsdir=.")

    # Animated glowing progress bar at the bottom for instant Shorts/Reels polish
    video_chain = (
        f"{layout_graph}"
        f"[base]{','.join(post_vf)}[v_graded];"
        f"color=c={pal['pbar']}:s=1080x10:r=30[pbar];"
        f"[v_graded][pbar]overlay=x='-W+(W*min(t/{duration:.2f},1))':y=H-14:shortest=1[v];"
    )

    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    bgm_vol = "0.15" if edit_type in ("aura", "gaming", "clash") else "0.11"
    fade_out_start = max(0.5, duration - 1.2)

    audio_mix_labels = ["[voice]"]
    audio_chains = [
        "[0:a]highpass=f=80,acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.20[voice];"
    ]
    next_in = 1

    if bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        audio_chains.append(
            f"[{next_in}:a]atrim=0:{duration:.2f},afade=t=in:st=0:d=0.8,"
            f"afade=t=out:st={fade_out_start:.2f}:d=1.2,volume={bgm_vol}[bgm];"
        )
        audio_mix_labels.append("[bgm]")
        next_in += 1

    if whoosh_file:
        cmd.extend(["-i", whoosh_file])
        audio_chains.append(f"[{next_in}:a]atrim=0:0.45,volume=0.40[whoosh];")
        audio_mix_labels.append("[whoosh]")
        next_in += 1

    if sfx_file:
        cmd.extend(["-i", sfx_file])
        sfx_ms = int(peak_sec * 1000)
        audio_chains.append(
            f"[{next_in}:a]atrim=0:1.2,afade=t=out:st=0.75:d=0.45,adelay={sfx_ms}|{sfx_ms},volume=0.42[sfx];"
        )
        audio_mix_labels.append("[sfx]")
        next_in += 1

    if len(audio_mix_labels) == 1:
        audio_chains.append("[voice]anull[a]")
    else:
        audio_chains.append(
            f"{''.join(audio_mix_labels)}amix=inputs={len(audio_mix_labels)}:duration=first:dropout_transition=2:normalize=0[a]"
        )

    fc = video_chain + "".join(audio_chains)

    cmd.extend([
        "-filter_complex", fc,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "21",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_file,
    ])

    print(
        f"[MAG73 Pro Editor] Rendering {output_file} | Style: {edit_type} | "
        f"Captions: {bool(ass_file)} | BGM: {bool(bgm_file)} | Whoosh: {bool(whoosh_file)} | PeakSFX: {bool(sfx_file)}"
    )
    subprocess.run(cmd, check=True)

    os.makedirs("output_clips", exist_ok=True)
    cover_path = os.path.join("output_clips", output_file.replace(".mp4", ".jpg"))
    thumb_sec = min(2.0, duration / 2.0)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{thumb_sec:.2f}",
            "-i", output_file, "-frames:v", "1", "-update", "1", "-q:v", "3", cover_path,
        ],
        check=False,
    )

    return output_file
