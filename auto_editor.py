import os
import re
import json
import math
import struct
import shutil
import subprocess
import requests

FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PRO_FONT_FILE = "Montserrat-ExtraBold.ttf"
PRO_FONT_URL = "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf"

# ASS uses BGR hex (&H00BBGGRR&), FFmpeg color uses 0xRRGGBB
STYLE_PALETTE = {
    "vlog":        {"hl": "&H0000D7FF&", "hook_txt": "&H0000D7FF&", "hook_bg": "&H300B1018&", "pbar": "0xF59E0B", "border": "0xF59E0B"},
    "informative": {"hl": "&H00F8BD38&", "hook_txt": "&H00F8BD38&", "hook_bg": "&H300B1524&", "pbar": "0x38BDF8", "border": "0x38BDF8"},
    "gaming":      {"hl": "&H0080DE4A&", "hook_txt": "&H0080DE4A&", "hook_bg": "&H300A1812&", "pbar": "0x4ADE80", "border": "0x4ADE80"},
    "clash":       {"hl": "&H00EED322&", "hook_txt": "&H00EED322&", "hook_bg": "&H300E1728&", "pbar": "0x22D3EE", "border": "0x22D3EE"},
    "funny":       {"hl": "&H0015CCFA&", "hook_txt": "&H0015CCFA&", "hook_bg": "&H301C1406&", "pbar": "0xFACC15", "border": "0xFACC15"},
    "aura":        {"hl": "&H005555FF&", "hook_txt": "&H007171F8&", "hook_bg": "&H3018080A&", "pbar": "0xEF4444", "border": "0xEF4444"},
    "drama":       {"hl": "&H003C92FB&", "hook_txt": "&H003C92FB&", "hook_bg": "&H301C0D08&", "pbar": "0xF97316", "border": "0xF97316"},
    "clean":       {"hl": "&H00FFE500&", "hook_txt": "&H00FFFFFF&", "hook_bg": "&H350F1115&", "pbar": "0x6366F1", "border": "0x6366F1"},
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


def _analyze_audio_profile(video_path, start, duration):
    """
    Pure-Python DSP audio analyzer:
    1. Finds the EXACT loudest reaction/action moment (real_peak_sec) for impact zoom/shake/SFX sync.
    2. Detects if the source video ALREADY has loud background music (has_existing_bgm) so 2 songs NEVER clash!
    """
    fallback_peak = max(2.5, duration * 0.45)
    try:
        raw = subprocess.check_output(
            [
                "ffmpeg", "-v", "error", "-ss", str(start), "-t", str(duration),
                "-i", video_path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-",
            ],
            stderr=subprocess.DEVNULL,
        )
        total_samples = len(raw) // 2
        if total_samples < 8000:
            return fallback_peak, False

        bucket_samples = 2000  # 0.25s buckets
        rms_list = []
        for off in range(0, total_samples - bucket_samples + 1, bucket_samples):
            chunk = struct.unpack(f"<{bucket_samples}h", raw[off * 2:(off + bucket_samples) * 2])
            sq = sum(s * s for s in chunk) / bucket_samples
            rms_list.append(math.sqrt(sq) / 32768.0)

        if len(rms_list) < 8:
            return fallback_peak, False

        # Detect existing continuous background music via 25th-percentile floor energy
        sorted_rms = sorted(rms_list)
        p25_floor = sorted_rms[len(sorted_rms) // 4]
        has_existing_bgm = p25_floor > 0.042

        # Find true climax peak between 2.5s and (duration - 2.0s)
        lo = min(len(rms_list) - 1, max(1, int(2.5 / 0.25)))
        hi = max(lo + 1, min(len(rms_list), int((duration - 2.0) / 0.25)))
        peak_idx = lo
        peak_val = -1.0
        for idx in range(lo, hi):
            if rms_list[idx] > peak_val:
                peak_val = rms_list[idx]
                peak_idx = idx

        real_peak_sec = round(peak_idx * 0.25, 2)
        print(
            f"[MAG73 DSP] Real audio peak={real_peak_sec:.2f}s (rms={peak_val:.3f}) | "
            f"Floor={p25_floor:.3f} | ExistingBGM={has_existing_bgm}"
        )
        return real_peak_sec, has_existing_bgm
    except Exception as e:
        print(f"[MAG73 DSP] Audio profile fallback: {e}")
        return fallback_peak, False


def _fetch_audio(query, out_prefix):
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
    return None


def _generate_whoosh_sfx(out_path):
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anoisesrc=color=pink:duration=0.38:sample_rate=44100",
                "-af", "bandpass=f=950:width_type=h:w=1100,afade=t=in:st=0:d=0.14,afade=t=out:st=0.18:d=0.20,volume=0.55",
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
    try:
        if edit_type == "funny":
            expr = "sin(2*PI*(200*exp(-7*t)+55)*t)*exp(-5.0*t)*0.75"
            dur = "0.45"
        else:
            expr = "sin(2*PI*(110*exp(-3.2*t)+36)*t)*exp(-2.8*t)*0.82"
            dur = "0.80"
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


def generate_pro_ass(words, clip_start, clip_end, font_name, edit_type, is_wide_blur, title_text, ass_path, captions_on=True):
    """
    Generates ONE unified Pro ASS subtitle file with:
    1. Spring-animated Viral Hook Banner (Layer 1, Top-Center) — smooth bounce & fade, never clips off-screen!
    2. ZERO-OVERLAP word-by-word CapCut/Hormozi pop captions (Layer 0) — strict chronological clamping!
    """
    pal = STYLE_PALETTE.get(edit_type, STYLE_PALETTE["vlog"])
    hl_color = pal["hl"]
    hook_txt_col = pal["hook_txt"]
    hook_bg_col = pal["hook_bg"]

    cap_margin_v = 400 if is_wide_blur else 470
    hook_margin_v = 320 if is_wide_blur else 185
    cap_font_size = 82 if edit_type in ("funny", "gaming", "aura") else 76

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{cap_font_size},&H00FFFFFF,{hl_color},&H00000000,&HB8000000,-1,0,0,0,100,100,1,0,1,9,4,2,65,65,{cap_margin_v},1
Style: Hook,{font_name},52,{hook_txt_col},&H00FFFFFF,{hook_bg_col},&H99000000,-1,0,0,0,100,100,2,0,3,18,0,8,70,70,{hook_margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []

    # 1. Spring-Animated Hook Banner (0.10s - 3.40s)
    if title_text and edit_type != "clean":
        anim_hook = (
            r"{\fad(100,260)\fscx74\fscy74\t(0,130,\fscx106\fscy106)\t(130,210,\fscx100\fscy100)}"
            + title_text
        )
        lines.append(f"Dialogue: 1,{_format_ass_time(0.10)},{_format_ass_time(3.40)},Hook,,0,0,0,,{anim_hook}")

    # 2. Word-by-word Pop Captions with STRICT zero-overlap clamping
    if captions_on and words:
        raw_clip_words = []
        for w in words:
            ws = float(w.get("start", 0))
            we = float(w.get("end", ws + 0.25))
            txt = _clean_text(w.get("word", "")).upper()
            if not txt:
                continue
            if we >= clip_start and ws <= clip_end:
                rel_s = max(0.0, ws - clip_start)
                rel_e = min(clip_end - clip_start, we - clip_start)
                if rel_e - rel_s > 0.95:
                    rel_e = rel_s + 0.80
                if rel_e - rel_s < 0.10:
                    rel_e = rel_s + 0.18
                raw_clip_words.append({"word": txt, "start": rel_s, "end": rel_e})

        raw_clip_words.sort(key=lambda x: x["start"])

        chunks = []
        current = []
        for w in raw_clip_words:
            if not current:
                current.append(w)
                continue
            gap = w["start"] - current[-1]["end"]
            curr_len = sum(len(x["word"]) + 1 for x in current)
            if len(current) >= 3 or (curr_len + len(w["word"]) > 15) or gap > 0.50:
                chunks.append(current)
                current = [w]
            else:
                current.append(w)
        if current:
            chunks.append(current)

        flat_events = []
        for chunk in chunks:
            for active_idx, active_w in enumerate(chunk):
                ev_start = active_w["start"]
                if active_idx + 1 < len(chunk):
                    ev_end = chunk[active_idx + 1]["start"]
                else:
                    ev_end = active_w["end"] + 0.08
                if ev_end <= ev_start + 0.05:
                    ev_end = ev_start + 0.14

                styled_parts = []
                for idx, w_obj in enumerate(chunk):
                    if idx == active_idx:
                        styled_parts.append(
                            f"{{\\c{hl_color}\\fscx112\\fscy112}}{w_obj['word']}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}"
                        )
                    else:
                        styled_parts.append(w_obj["word"])

                line_text = " ".join(styled_parts)
                if active_idx == 0:
                    line_text = r"{\fscx86\fscy86\t(0,60,\fscx105\fscy105)\t(60,115,\fscx100\fscy100)}" + line_text

                flat_events.append({"start": ev_start, "end": ev_end, "text": line_text})

        # STRICT ZERO-OVERLAP GUARANTEE across all chunks!
        for i in range(len(flat_events) - 1):
            if flat_events[i]["end"] >= flat_events[i + 1]["start"]:
                flat_events[i]["end"] = max(
                    flat_events[i]["start"] + 0.04,
                    flat_events[i + 1]["start"] - 0.01,
                )

        for ev in flat_events:
            if ev["end"] > ev["start"] + 0.02:
                lines.append(
                    f"Dialogue: 0,{_format_ass_time(ev['start'])},{_format_ass_time(ev['end'])},Default,,0,0,0,,{ev['text']}"
                )

        print(f"[MAG73 Captions] Generated {len(flat_events)} zero-overlap caption events.")

    if not lines:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines))
    return ass_path


def _build_layout_and_motion(in_w, in_h, focus_x, duration, edit_type, peak_sec, layout_mode):
    """
    100x Cleaner, Buttery Smooth Pro Motion (ZERO jarring step jumps or escaping borders):
    - Smooth ease-out opening hook settle (0.0s - 0.45s)
    - Gentle cinematic breathing push-in across clip
    - Smooth ease-in/ease-out climax zoom + camera shake synced to REAL audio peak
    - Gaming Wide mode enlarges gameplay 25% taller (1080x760) & zooms INSIDE the frame so borders stay rock-solid!
    """
    dur_frames = max(30, int(duration * 30))
    pk = float(peak_sec)
    is_landscape = (in_w > in_h)

    if layout_mode == "gaming_wide":
        is_wide_blur = is_landscape
    elif layout_mode == "vertical_full":
        is_wide_blur = False
    else:
        is_wide_blur = (edit_type in ("gaming", "clash")) and is_landscape

    pal = STYLE_PALETTE.get(edit_type, STYLE_PALETTE["vlog"])

    # Smooth bell-curve climax zoom around real audio peak (no abrupt teleporting!)
    peak_bell = f"max(0,1-abs(on/30-{pk:.2f})/0.85)"
    shake_win = f"between(on/30,{pk:.2f},{pk+0.38:.2f})"

    if edit_type == "funny":
        z_expr = f"1.01+0.13*max(0,1-on/13)+0.04*min(1,on/{dur_frames})+0.18*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+14*sin(on*3.2)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+14*cos(on*3.6)*{shake_win},0,ih-ih/zoom)"
    elif edit_type == "aura":
        z_expr = f"1.02+0.14*max(0,1-on/12)+0.08*min(1,on/{dur_frames})+0.18*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+20*sin(on*3.0)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+20*cos(on*3.5)*{shake_win},0,ih-ih/zoom)"
    elif edit_type in ("gaming", "clash"):
        z_expr = f"1.01+0.12*max(0,1-on/12)+0.05*min(1,on/{dur_frames})+0.15*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+15*sin(on*3.1)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+15*cos(on*3.5)*{shake_win},0,ih-ih/zoom)"
    elif edit_type == "drama":
        z_expr = f"1.01+0.10*max(0,1-on/14)+0.10*min(1,on/{dur_frames})+0.12*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+10*sin(on*2.9)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+10*cos(on*3.3)*{shake_win},0,ih-ih/zoom)"
    elif edit_type in ("vlog", "informative"):
        z_expr = f"1.01+0.12*max(0,1-on/14)+0.06*min(1,on/{dur_frames})+0.08*{peak_bell}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    else:
        z_expr = f"1.00+0.05*min(1,on/{dur_frames})"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    if is_wide_blur:
        # Bigger 1080x760 gameplay window with smooth zoom INSIDE the frame + locked sleek accent bars!
        graph = (
            f"[0:v]fps=30,split=2[bg_src][fg_src];"
            f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"boxblur=26:6,eq=brightness=-0.24:saturation=1.18,setpts=PTS-STARTPTS[bg];"
            f"[fg_src]crop=iw*0.86:ih:iw*0.07:0,scale=1080:760:force_original_aspect_ratio=increase,crop=1080:760,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=1080x760:fps=30,"
            f"setpts=PTS-STARTPTS,pad=1080:768:0:4:color={pal['border']}[fg];"
            f"[bg][fg]overlay=0:(H-h)/2:shortest=1,setsar=1[base];"
        )
    else:
        crop_x = "(iw-1080)*0.18" if focus_x == "left" else ("(iw-1080)*0.82" if focus_x == "right" else "(iw-1080)/2")
        graph = (
            f"[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920:{crop_x}:(ih-1920)/2,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=1080x1920:fps=30,"
            f"setpts=PTS-STARTPTS,setsar=1[base];"
        )

    return graph, is_wide_blur


def render_pro_short(video_path, clip_data, word_timestamps, index):
    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    bgm_enabled = bool(plugin_cfg.get("bgm_enabled", True))
    sfx_enabled = bool(plugin_cfg.get("sfx_enabled", True))
    banner_enabled = bool(plugin_cfg.get("banner_enabled", True))
    custom_ffmpeg = str(plugin_cfg.get("custom_ffmpeg", "")).strip()
    custom_font_url = str(plugin_cfg.get("custom_font_url", "")).strip()

    _, font_name = _ensure_pro_font(custom_font_url)
    in_w, in_h = _probe_video_dims(video_path)

    start = max(0.0, float(clip_data.get("start", 0)))
    end = float(clip_data.get("end", start + 18))
    duration = max(8.0, min(36.0, end - start))

    orig_start = int(float(clip_data.get("orig_start", start)))
    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "vlog"))).lower() or "vlog"
    if edit_type not in STYLE_PALETTE:
        edit_type = "vlog"

    layout_mode = str(clip_data.get("layout_mode", "auto")).strip().lower()
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _clean_text(clip_data.get("title_text", "")).upper() if banner_enabled else ""

    # DSP Audio Analysis: exact loudest climax peak + existing BGM check
    real_peak_sec, has_existing_bgm = _analyze_audio_profile(video_path, start, duration)
    peak_sec = real_peak_sec

    mm, ss = divmod(max(0, orig_start), 60)
    output_file = f"MAG73_{edit_type.upper()}_{mm:02d}m{ss:02d}s_Clip_{index + 1}.mp4"

    # NEVER clash two songs: skip external BGM if source already has background music!
    bgm_file = None
    if bgm_enabled and edit_type != "clean" and not has_existing_bgm:
        bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}")
    elif has_existing_bgm:
        print("[MAG73 Audio] Source already has BGM — skipping extra music to keep mix clean!")

    whoosh_file = _generate_whoosh_sfx(f"whoosh_{index}.mp3") if (sfx_enabled and edit_type != "clean") else None

    sfx_file = None
    if sfx_enabled and edit_type in ("aura", "funny", "gaming", "clash", "drama"):
        sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}")
        if not sfx_file:
            sfx_file = _generate_synth_sfx(f"synth_sfx_{index}.mp3", edit_type)

    layout_graph, is_wide_blur = _build_layout_and_motion(
        in_w, in_h, focus_x, duration, edit_type, peak_sec, layout_mode
    )

    ass_file = generate_pro_ass(
        word_timestamps,
        start,
        start + duration,
        font_name,
        edit_type,
        is_wide_blur,
        title_text,
        f"cap_{index}.ass",
        captions_on=(caption_lang != "off"),
    )

    # Distinct pro visual grading + smooth peak highlight flash
    if edit_type == "vlog":
        post_vf = [
            "eq=contrast=1.08:saturation=1.20:brightness=0.02",
            "colorbalance=rs=0.04:gs=0.01:bs=-0.03",
            "unsharp=5:5:0.35:5:5:0.0",
        ]
    elif edit_type == "informative":
        post_vf = [
            "eq=contrast=1.08:saturation=1.10:brightness=0.01",
            "unsharp=5:5:0.45:5:5:0.0",
        ]
    elif edit_type == "funny":
        post_vf = [
            "eq=contrast=1.10:saturation=1.18:brightness=0.02",
            f"eq=brightness=0.22:enable='between(t,{peak_sec:.2f},{peak_sec+0.09:.2f})'",
        ]
    elif edit_type in ("gaming", "clash"):
        post_vf = [
            "eq=contrast=1.13:saturation=1.18",
            "unsharp=5:5:0.45:5:5:0.0",
            f"eq=brightness=0.24:enable='between(t,{peak_sec:.2f},{peak_sec+0.10:.2f})'",
        ]
    elif edit_type == "aura":
        post_vf = [
            "eq=contrast=1.14:saturation=0.86:brightness=-0.02",
            "vignette=PI/6",
            f"eq=brightness=0.35:enable='between(t,{peak_sec:.2f},{peak_sec+0.11:.2f})'",
            f"hue=s=0:enable='gte(t,{peak_sec+0.11:.2f})'",
            f"eq=contrast=1.24:brightness=-0.03:enable='gte(t,{peak_sec+0.11:.2f})'",
        ]
    elif edit_type == "drama":
        post_vf = [
            "eq=contrast=1.12:saturation=0.95:brightness=-0.01",
            "vignette=PI/6",
            f"eq=brightness=0.20:enable='between(t,{peak_sec:.2f},{peak_sec+0.09:.2f})'",
        ]
    else:
        post_vf = ["eq=contrast=1.05:saturation=1.05"]

    if custom_ffmpeg and ";" not in custom_ffmpeg and "[" not in custom_ffmpeg:
        post_vf.append(custom_ffmpeg)

    if ass_file and os.path.exists(ass_file):
        post_vf.append(f"ass={ass_file}:fontsdir=.")

    pal = STYLE_PALETTE.get(edit_type, STYLE_PALETTE["vlog"])
    # Sleek top edge progress bar (never hidden behind Shorts/Reels bottom UI!)
    video_chain = (
        f"{layout_graph}"
        f"[base]{','.join(post_vf)}[v_graded];"
        f"color=c={pal['pbar']}:s=1080x8:r=30[pbar];"
        f"[v_graded][pbar]overlay=x='-W+(W*min(t/{duration:.2f},1))':y=0:shortest=1[v];"
    )

    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    bgm_vol = "0.18" if edit_type in ("aura", "gaming", "clash") else "0.13"
    fade_out_start = max(0.5, duration - 1.2)

    audio_mix_labels = ["[voice]"]
    if bgm_file:
        audio_chains = [
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,highpass=f=85,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.20,asplit=2[voice][v_sc];"
        ]
    else:
        audio_chains = [
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,highpass=f=85,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.20[voice];"
        ]

    next_in = 1

    if bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        # Pro sidechain ducking: BGM ducks under voice automatically!
        audio_chains.append(
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:{duration:.2f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={fade_out_start:.2f}:d=1.2,volume={bgm_vol}[bgm_pre];"
            f"[bgm_pre][v_sc]sidechaincompress=threshold=0.03:ratio=5:attack=25:release=320[bgm];"
        )
        audio_mix_labels.append("[bgm]")
        next_in += 1

    if whoosh_file:
        cmd.extend(["-i", whoosh_file])
        audio_chains.append(
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:0.38,volume=0.35[whoosh];"
        )
        audio_mix_labels.append("[whoosh]")
        next_in += 1

    if sfx_file:
        cmd.extend(["-i", sfx_file])
        sfx_ms = int(peak_sec * 1000)
        audio_chains.append(
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:1.0,afade=t=out:st=0.65:d=0.35,adelay={sfx_ms}|{sfx_ms},volume=0.38[sfx];"
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
        "-crf", "20",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_file,
    ])

    print(
        f"[MAG73 Pro Editor] Rendering {output_file} | Style={edit_type} | WideBlur={is_wide_blur} | "
        f"Peak={peak_sec:.2f}s | DuckedBGM={bool(bgm_file)} | SFX={bool(sfx_file)}"
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
