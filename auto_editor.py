import os
import re
import json
import math
import struct
import shutil
import subprocess
import requests

try:
    import cv2
    import numpy as np
    HAS_CV2 = True
except Exception:
    HAS_CV2 = False

FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
PRO_FONT_FILE = "Montserrat-ExtraBold.ttf"
PRO_FONT_URL = "https://raw.githubusercontent.com/JulietaUla/Montserrat/master/fonts/ttf/Montserrat-ExtraBold.ttf"

# ASS BGR hex (&H00BBGGRR&), FFmpeg hex (0xRRGGBB)
STYLE_PALETTE = {
    "roast":       {"hl": "&H0015CCFA&", "pop": "&H004444FF&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H0015CCFA&", "ribbon": "0x99111B@0.76", "pbar": "0xEF4444", "border": "0xEF4444", "stamp": "ROASTED"},
    "aura":        {"hl": "&H005555FF&", "pop": "&H0015CCFA&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H0015CCFA&", "ribbon": "0x11131C@0.82", "pbar": "0xEF4444", "border": "0xEF4444", "stamp": "AURA +1000"},
    "aesthetic":   {"hl": "&H0015CCFA&", "pop": "&H00FFFFFF&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H0015CCFA&", "ribbon": "0x0B0F17@0.68", "pbar": "0xFACC15", "border": "0xFACC15", "stamp": ""},
    "vlog":        {"hl": "&H0000D7FF&", "pop": "&H0080DE4A&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H0000D7FF&", "ribbon": "0x141824@0.80", "pbar": "0xF59E0B", "border": "0xF59E0B", "stamp": ""},
    "informative": {"hl": "&H00F8BD38&", "pop": "&H0000E5FF&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H00F8BD38&", "ribbon": "0x0B1524@0.82", "pbar": "0x38BDF8", "border": "0x38BDF8", "stamp": ""},
    "gaming":      {"hl": "&H0080DE4A&", "pop": "&H0015CCFA&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H0080DE4A&", "ribbon": "0x0A1812@0.82", "pbar": "0x4ADE80", "border": "0x4ADE80", "stamp": "INSANE"},
    "clash":       {"hl": "&H00EED322&", "pop": "&H005555FF&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H00EED322&", "ribbon": "0x7F1D1D@0.76", "pbar": "0x22D3EE", "border": "0x22D3EE", "stamp": "COOKED"},
    "funny":       {"hl": "&H0015CCFA&", "pop": "&H0080DE4A&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H0015CCFA&", "ribbon": "0x1E1506@0.82", "pbar": "0xFACC15", "border": "0xFACC15", "stamp": "WAIT WHAT"},
    "drama":       {"hl": "&H003C92FB&", "pop": "&H0015CCFA&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H003C92FB&", "ribbon": "0x7C1D12@0.78", "pbar": "0xF97316", "border": "0xF97316", "stamp": ""},
    "clean":       {"hl": "&H00FFE500&", "pop": "&H0000D7FF&", "hook_txt": "&H00FFFFFF&", "hook_acc": "&H00FFFFFF&", "ribbon": "0x0F1115@0.75", "pbar": "0x6366F1", "border": "0x6366F1", "stamp": ""},
}

HYPE_WORDS = {
    "SIX", "FOUR", "OUT", "OMG", "WTF", "BRO", "BHAI", "ROAST", "CLUTCH",
    "INSANE", "CRAZY", "BOOM", "DEAD", "WIN", "AURA", "LEGEND", "COLD", "100", "200",
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


def _probe_video_info(video_path):
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height:format=duration",
                "-of", "json", video_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        data = json.loads(out)
        streams = data.get("streams") or [{}]
        w = int(streams[0].get("width", 1280))
        h = int(streams[0].get("height", 720))
        dur = float((data.get("format") or {}).get("duration", 60.0))
        return w, h, dur
    except Exception:
        return 1280, 720, 60.0


def _build_smart_face_crop_expr(video_path, start, duration, focus_x):
    """OpenCV shot-by-shot speaker face auto-reframer."""
    fallback_x = "0.18*(iw-ow)" if focus_x == "left" else ("0.82*(iw-ow)" if focus_x == "right" else "(iw-ow)/2")
    if not HAS_CV2:
        return fallback_x

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return fallback_x

        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            cap.release()
            return fallback_x

        samples = []
        step = 0.40
        t_rel = 0.0
        prev_thumb = None

        while t_rel <= duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + t_rel) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            fh, fw = frame.shape[:2]
            scale = 480.0 / max(1, fw)
            small = cv2.resize(frame, (480, max(1, int(fh * scale))))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            thumb = cv2.resize(gray, (64, 36))
            is_cut = False
            if prev_thumb is not None:
                diff = float(np.mean(np.abs(thumb.astype(np.float32) - prev_thumb.astype(np.float32))))
                if diff > 27.0:
                    is_cut = True
            prev_thumb = thumb

            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.18, minNeighbors=5, minSize=(36, 36))
            face_x = None
            if len(faces) > 0:
                best = max(faces, key=lambda b: b[2] * b[3])
                face_x = (best[0] + best[2] * 0.5) / 480.0

            samples.append({"t": round(t_rel, 2), "cut": is_cut, "fx": face_x})
            t_rel += step

        cap.release()

        if len(samples) < 3:
            return fallback_x

        shots = []
        curr = [samples[0]]
        for s in samples[1:]:
            if s["cut"] and (s["t"] - curr[0]["t"] >= 0.8):
                shots.append(curr)
                curr = [s]
            else:
                curr.append(s)
        if curr:
            shots.append(curr)

        shot_targets = []
        for sh in shots[:14]:
            fxs = sorted([x["fx"] for x in sh if x["fx"] is not None])
            cx = fxs[len(fxs) // 2] if fxs else 0.50
            cx = max(0.14, min(0.86, cx))
            shot_targets.append((sh[0]["t"], sh[-1]["t"] + step, cx))

        if not shot_targets:
            return fallback_x

        merged = [shot_targets[0]]
        for st, en, cx in shot_targets[1:]:
            pst, pen, pcx = merged[-1]
            if abs(cx - pcx) < 0.06:
                merged[-1] = (pst, en, (pcx + cx) / 2.0)
            else:
                merged.append((st, en, cx))

        expr = f"clip({merged[-1][2]:.3f}*iw-ow/2,0,iw-ow)"
        for st, en, cx in reversed(merged[:-1]):
            expr = f"if(lt(t,{en:.2f}),clip({cx:.3f}*iw-ow/2,0,iw-ow),{expr})"

        print(f"[MAG73 FaceTrack] Auto-reframed {len(merged)} camera shot(s) cleanly!")
        return expr
    except Exception as e:
        print(f"[MAG73 FaceTrack] Fallback to center crop: {e}")
        return fallback_x


def _snap_clean_duration(start, duration, max_file_dur, words):
    avail_max = max(8.0, min(38.0, max_file_dur - start - 0.1))
    target_end = start + duration
    if not words:
        return min(duration, avail_max)

    best_end = None
    for i, w in enumerate(words):
        we = float(w.get("end", 0))
        if target_end - 1.5 <= we <= min(start + avail_max, target_end + 1.8):
            txt = str(w.get("word", "")).strip()
            nxt_gap = (float(words[i + 1].get("start", we)) - we) if i + 1 < len(words) else 1.0
            if txt.endswith((".", "!", "?")) or nxt_gap >= 0.35:
                best_end = min(start + avail_max, we + 0.32)
                if we >= target_end - 0.4:
                    break

    if best_end and (best_end - start) >= 9.0:
        snapped = round(best_end - start, 2)
        print(f"[MAG73 Pacing] Snapped clip end cleanly: {duration:.1f}s -> {snapped:.1f}s")
        return snapped
    return min(duration, avail_max)


def _analyze_audio_profile(video_path, start, duration):
    fallback_peak = max(3.0, duration * 0.52)
    try:
        raw = subprocess.check_output(
            [
                "ffmpeg", "-v", "error", "-ss", str(start), "-t", str(duration),
                "-i", video_path, "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-",
            ],
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        total_samples = len(raw) // 2
        if total_samples < 8000:
            return fallback_peak, False

        bucket_samples = 2000
        rms_list = []
        for off in range(0, total_samples - bucket_samples + 1, bucket_samples):
            chunk = struct.unpack(f"<{bucket_samples}h", raw[off * 2:(off + bucket_samples) * 2])
            sq = sum(s * s for s in chunk) / bucket_samples
            rms_list.append(math.sqrt(sq) / 32768.0)

        if len(rms_list) < 8:
            return fallback_peak, False

        sorted_rms = sorted(rms_list)
        p25_floor = sorted_rms[len(sorted_rms) // 4]
        has_existing_bgm = p25_floor > 0.042

        # Peak climax between 35% and 82% of clip so setup builds properly before the drop!
        lo = min(len(rms_list) - 1, max(2, int((duration * 0.35) / 0.25)))
        hi = max(lo + 1, min(len(rms_list), int((duration * 0.82) / 0.25)))
        peak_idx = lo
        peak_val = -1.0
        for idx in range(lo, hi):
            if rms_list[idx] > peak_val:
                peak_val = rms_list[idx]
                peak_idx = idx

        real_peak_sec = round(peak_idx * 0.25, 2)
        print(f"[MAG73 DSP] Climax peak={real_peak_sec:.2f}s | ExistingBGM={has_existing_bgm}")
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
    cmd = [
        "yt-dlp", "-x", "--audio-format", "mp3",
        "--max-filesize", "10M", "--no-playlist",
        "--socket-timeout", "12",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "-o", f"{out_prefix}.%(ext)s",
    ]
    if os.path.exists("cookies.txt"):
        cmd.extend(["--cookies", "cookies.txt"])
    cmd.append(q)
    try:
        subprocess.run(cmd, check=False, timeout=35, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None
    if os.path.exists(out_file) and os.path.getsize(out_file) > 10000:
        return out_file
    return None


def _generate_whoosh_sfx(out_path):
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anoisesrc=color=pink:duration=0.36:sample_rate=44100",
                "-af", "bandpass=f=950:width_type=h:w=1100,afade=t=in:st=0:d=0.13,afade=t=out:st=0.16:d=0.20,volume=0.52",
                "-c:a", "libmp3lame", "-q:a", "4", out_path,
            ],
            check=True,
            timeout=15,
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
        if edit_type in ("funny", "roast"):
            expr = "sin(2*PI*(195*exp(-6.5*t)+46)*t)*exp(-4.2*t)*0.85"
            dur = "0.55"
        else:
            expr = "sin(2*PI*(110*exp(-3.0*t)+34)*t)*exp(-2.4*t)*0.90"
            dur = "0.85"
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"aevalsrc={expr}:d={dur}:s=44100",
                "-c:a", "libmp3lame", "-q:a", "4", out_path,
            ],
            check=True,
            timeout=15,
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


def _format_two_line_hook(title_text, acc_col):
    """Formats viral 2-line hook (Line 1 White/Yellow, Line 2 Glowing Accent) just like top Reels."""
    words = title_text.split()
    if len(words) <= 2:
        return f"{{\\c{acc_col}}}{title_text}"
    mid = max(1, len(words) // 2)
    l1 = " ".join(words[:mid])
    l2 = " ".join(words[mid:])
    return f"{l1}\\N{{\\c{acc_col}}}{l2}"


def generate_pro_ass(words, clip_start, clip_end, font_name, edit_type, is_wide_blur, title_text, peak_sec, ass_path, captions_on=True):
    """
    Viral Reels ASS Engine:
    - Roast/Aura/Aesthetic: Full-width Translucent Ribbon + Bold 2-line Hook + Climax Impact Stamp ("ROASTED" / "AURA +1000")!
    - All styles: Zero-overlap Hormozi/CapCut word-by-word pop captions!
    """
    pal = STYLE_PALETTE.get(edit_type, STYLE_PALETTE["vlog"])
    hl_color = pal["hl"]
    pop_color = pal["pop"]
    hook_txt_col = pal["hook_txt"]
    hook_acc_col = pal["hook_acc"]

    is_ribbon_style = edit_type in ("roast", "aura", "aesthetic", "clash")
    cap_margin_v = 330 if is_wide_blur else (320 if is_ribbon_style else 400)
    hook_margin_v = 250 if is_wide_blur else (210 if not is_ribbon_style else 540)
    hook_align = 2 if (is_ribbon_style and not is_wide_blur) else 8
    cap_font_size = 84 if edit_type in ("funny", "gaming", "aura", "roast") else 78

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{cap_font_size},&H00FFFFFF,{hl_color},&H00000000,&HC0000000,-1,0,0,0,100,100,1,0,1,10,5,2,60,60,{cap_margin_v},1
Style: Hook,{font_name},62,{hook_txt_col},&H00FFFFFF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,1,6,4,{hook_align},65,65,{hook_margin_v},1
Style: Stamp,{font_name},94,{hook_acc_col},&H00FFFFFF,&H00000000,&HCC000000,-1,0,0,0,100,100,3,0,1,12,6,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hook_end = min(clip_end - clip_start, max(3.6, peak_sec - 0.15)) if is_ribbon_style else 3.40

    # 1. Viral 2-Line Spring-Bounce Hook Text
    if title_text and edit_type != "clean":
        styled_hook = _format_two_line_hook(title_text, hook_acc_col)
        anim_hook = (
            r"{\fad(100,260)\fscx74\fscy74\t(0,130,\fscx107\fscy107)\t(130,220,\fscx100\fscy100)}"
            + styled_hook
        )
        lines.append(f"Dialogue: 2,{_format_ass_time(0.08)},{_format_ass_time(hook_end)},Hook,,0,0,0,,{anim_hook}")

    # 2. Climax Impact Stamp right at peak_sec for Roast / Aura / Gaming / Clash
    stamp_txt = pal.get("stamp", "")
    if stamp_txt and edit_type in ("roast", "aura", "clash", "gaming"):
        st_s = peak_sec + 0.05
        st_e = min(clip_end - clip_start - 0.2, st_s + 1.35)
        if st_e > st_s + 0.4:
            anim_stamp = (
                r"{\fad(40,260)\fscx160\fscy160\t(0,110,\fscx100\fscy100)}"
                + stamp_txt
            )
            lines.append(f"Dialogue: 3,{_format_ass_time(st_s)},{_format_ass_time(st_e)},Stamp,,0,0,0,,{anim_stamp}")

    # 3. Zero-Overlap CapCut/Hormozi Word-by-Word Pop Captions
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
            if len(current) >= 3 or (curr_len + len(w["word"]) > 14) or gap > 0.48:
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
                    word_clean = re.sub(r"[^A-Z0-9]", "", w_obj["word"])
                    is_hype = word_clean in HYPE_WORDS or word_clean.isdigit()
                    if idx == active_idx:
                        col = pop_color if is_hype else hl_color
                        scale = 118 if is_hype else 112
                        styled_parts.append(
                            f"{{\\c{col}\\fscx{scale}\\fscy{scale}}}{w_obj['word']}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}"
                        )
                    else:
                        styled_parts.append(w_obj["word"])

                line_text = " ".join(styled_parts)
                if active_idx == 0:
                    line_text = r"{\fscx84\fscy84\t(0,60,\fscx106\fscy106)\t(60,115,\fscx100\fscy100)}" + line_text

                flat_events.append({"start": ev_start, "end": ev_end, "text": line_text})

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

        print(f"[MAG73 Captions] Generated {len(flat_events)} zero-overlap animated events.")

    if not lines:
        return None, hook_end
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines))
    return ass_path, hook_end


def _build_layout_and_motion(video_path, start, in_w, in_h, focus_x, duration, edit_type, peak_sec, layout_mode):
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

    peak_bell = f"max(0,1-abs(on/30-{pk:.2f})/0.85)"
    shake_win = f"between(on/30,{pk:.2f},{pk+0.42:.2f})"

    if edit_type in ("roast", "aura"):
        z_expr = f"1.02+0.15*max(0,1-on/12)+0.08*min(1,on/{dur_frames})+0.22*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+18*sin(on*3.1)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+18*cos(on*3.6)*{shake_win},0,ih-ih/zoom)"
    elif edit_type == "aesthetic":
        z_expr = f"1.02+0.10*max(0,1-on/16)+0.10*min(1,on/{dur_frames})+0.10*{peak_bell}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif edit_type == "funny":
        z_expr = f"1.01+0.13*max(0,1-on/12)+0.04*min(1,on/{dur_frames})+0.18*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+12*sin(on*3.2)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+12*cos(on*3.6)*{shake_win},0,ih-ih/zoom)"
    elif edit_type in ("gaming", "clash"):
        z_expr = f"1.01+0.12*max(0,1-on/12)+0.05*min(1,on/{dur_frames})+0.16*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+13*sin(on*3.1)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+13*cos(on*3.5)*{shake_win},0,ih-ih/zoom)"
    elif edit_type == "drama":
        z_expr = f"1.01+0.10*max(0,1-on/14)+0.10*min(1,on/{dur_frames})+0.12*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+9*sin(on*2.9)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+9*cos(on*3.3)*{shake_win},0,ih-ih/zoom)"
    else:
        z_expr = f"1.01+0.11*max(0,1-on/14)+0.06*min(1,on/{dur_frames})+0.08*{peak_bell}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    if is_wide_blur:
        graph = (
            f"[0:v]fps=30,split=2[bg_src][fg_src];"
            f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
            f"boxblur=24:6,eq=brightness=-0.06:saturation=1.28,setpts=PTS-STARTPTS[bg];"
            f"[fg_src]crop=iw*0.92:ih:iw*0.04:0,scale=720:520:force_original_aspect_ratio=increase,crop=720:520,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=720x520:fps=30,"
            f"scale=1080:780:flags=lanczos,setpts=PTS-STARTPTS,pad=1080:788:0:4:color={pal['border']}[fg];"
            f"[bg][fg]overlay=0:(H-h)/2:shortest=1,setsar=1[base];"
        )
    else:
        face_crop_x = _build_smart_face_crop_expr(video_path, start, duration, focus_x)
        graph = (
            f"[0:v]fps=30,scale=720:1280:force_original_aspect_ratio=increase,"
            f"crop=720:1280:x='{face_crop_x}':y='(ih-1280)/2',"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=720x1280:fps=30,"
            f"scale=1080:1920:flags=lanczos,setpts=PTS-STARTPTS,setsar=1[base];"
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
    in_w, in_h, max_file_dur = _probe_video_info(video_path)

    start = max(0.0, float(clip_data.get("start", 0)))
    end = float(clip_data.get("end", start + 18))
    raw_duration = max(8.0, min(36.0, end - start))
    duration = _snap_clean_duration(start, raw_duration, max_file_dur, word_timestamps)

    orig_start = int(float(clip_data.get("orig_start", start)))
    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "vlog"))).lower() or "vlog"
    if edit_type not in STYLE_PALETTE:
        edit_type = "vlog"

    layout_mode = str(clip_data.get("layout_mode", "auto")).strip().lower()
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _clean_text(clip_data.get("title_text", "")).upper() if banner_enabled else ""

    real_peak_sec, has_existing_bgm = _analyze_audio_profile(video_path, start, duration)
    peak_sec = real_peak_sec

    mm, ss = divmod(max(0, orig_start), 60)
    output_file = f"MAG73_{edit_type.upper()}_{mm:02d}m{ss:02d}s_Clip_{index + 1}.mp4"

    bgm_file = None
    if bgm_enabled and edit_type != "clean" and not has_existing_bgm:
        bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}")

    whoosh_file = _generate_whoosh_sfx(f"whoosh_{index}.mp3") if (sfx_enabled and edit_type != "clean") else None

    sfx_file = None
    if sfx_enabled and edit_type in ("roast", "aura", "aesthetic", "funny", "gaming", "clash", "drama"):
        sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}")
        if not sfx_file:
            sfx_file = _generate_synth_sfx(f"synth_sfx_{index}.mp3", edit_type)

    layout_graph, is_wide_blur = _build_layout_and_motion(
        video_path, start, in_w, in_h, focus_x, duration, edit_type, peak_sec, layout_mode
    )

    ass_file, hook_end = generate_pro_ass(
        word_timestamps,
        start,
        start + duration,
        font_name,
        edit_type,
        is_wide_blur,
        title_text,
        peak_sec,
        f"cap_{index}.ass",
        captions_on=(caption_lang != "off"),
    )

    pal = STYLE_PALETTE.get(edit_type, STYLE_PALETTE["vlog"])

    # Viral HDR CC + Climax Drop Effects (matching your reference Reels!)
    if edit_type == "roast":
        post_vf = [
            "eq=contrast=1.18:saturation=1.16:brightness=-0.01",
            "unsharp=5:5:0.75:5:5:0.0",
            "vignette=PI/6",
            f"eq=brightness=0.40:enable='between(t,{peak_sec:.2f},{peak_sec+0.11:.2f})'",
            f"eq=contrast=1.28:saturation=0.55:brightness=-0.03:enable='gte(t,{peak_sec+0.11:.2f})'",
        ]
    elif edit_type == "aura":
        post_vf = [
            "eq=contrast=1.18:saturation=0.88:brightness=-0.02",
            "unsharp=5:5:0.75:5:5:0.0",
            "vignette=PI/5",
            f"eq=brightness=0.44:enable='between(t,{peak_sec:.2f},{peak_sec+0.12:.2f})'",
            f"hue=s=0:enable='gte(t,{peak_sec+0.12:.2f})'",
            f"eq=contrast=1.30:brightness=-0.04:enable='gte(t,{peak_sec+0.12:.2f})'",
        ]
    elif edit_type == "aesthetic":
        post_vf = [
            "eq=contrast=1.16:saturation=0.92:brightness=-0.02",
            "colorbalance=rs=0.03:gs=0.00:bs=0.05",
            "unsharp=5:5:0.65:5:5:0.0",
            "vignette=PI/5",
            f"eq=brightness=0.22:enable='between(t,{peak_sec:.2f},{peak_sec+0.10:.2f})'",
        ]
    elif edit_type == "vlog":
        post_vf = [
            "eq=contrast=1.10:saturation=1.22:brightness=0.02",
            "colorbalance=rs=0.04:gs=0.01:bs=-0.03",
            "unsharp=5:5:0.50:5:5:0.0",
        ]
    elif edit_type == "funny":
        post_vf = [
            "eq=contrast=1.12:saturation=1.22:brightness=0.02",
            "unsharp=5:5:0.55:5:5:0.0",
            f"eq=brightness=0.24:enable='between(t,{peak_sec:.2f},{peak_sec+0.09:.2f})'",
        ]
    elif edit_type in ("gaming", "clash"):
        post_vf = [
            "eq=contrast=1.16:saturation=1.22",
            "unsharp=5:5:0.65:5:5:0.0",
            f"eq=brightness=0.28:enable='between(t,{peak_sec:.2f},{peak_sec+0.10:.2f})'",
        ]
    elif edit_type == "drama":
        post_vf = [
            "eq=contrast=1.14:saturation=0.95:brightness=-0.01",
            "vignette=PI/6",
            "unsharp=5:5:0.55:5:5:0.0",
            f"eq=brightness=0.22:enable='between(t,{peak_sec:.2f},{peak_sec+0.09:.2f})'",
        ]
    else:
        post_vf = ["eq=contrast=1.06:saturation=1.08", "unsharp=5:5:0.40:5:5:0.0"]

    # Viral Full-Width Translucent Ribbon behind Hook Text (exact reference style!)
    if title_text and edit_type != "clean":
        is_ribbon_style = edit_type in ("roast", "aura", "aesthetic", "clash")
        if is_ribbon_style and not is_wide_blur:
            post_vf.append(
                f"drawbox=x=0:y=1210:w=iw:h=190:color={pal['ribbon']}:t=fill:enable='between(t,0.08,{hook_end:.2f})'"
            )
        elif not is_wide_blur:
            post_vf.append(
                f"drawbox=x=0:y=155:w=iw:h=175:color={pal['ribbon']}:t=fill:enable='between(t,0.08,{hook_end:.2f})'"
            )

    if custom_ffmpeg and ";" not in custom_ffmpeg and "[" not in custom_ffmpeg:
        post_vf.append(custom_ffmpeg)

    if ass_file and os.path.exists(ass_file):
        post_vf.append(f"ass={ass_file}:fontsdir=.")

    video_chain = (
        f"{layout_graph}"
        f"[base]{','.join(post_vf)}[v_graded];"
        f"color=c={pal['pbar']}:s=1080x8:r=30[pbar];"
        f"[v_graded][pbar]overlay=x='-W+(W*min(t/{duration:.2f},1))':y=0:shortest=1[v];"
    )

    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    bgm_vol = "0.20" if edit_type in ("roast", "aura", "aesthetic", "gaming", "clash") else "0.14"
    fade_out_start = max(0.5, duration - 1.2)

    audio_mix_labels = ["[voice]"]
    if bgm_file:
        audio_chains = [
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,highpass=f=85,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.18,asplit=2[voice][v_sc];"
        ]
    else:
        audio_chains = [
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,highpass=f=85,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.18[voice];"
        ]

    next_in = 1

    if bgm_file:
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
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
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:0.36,volume=0.35[whoosh];"
        )
        audio_mix_labels.append("[whoosh]")
        next_in += 1

    if sfx_file:
        cmd.extend(["-i", sfx_file])
        sfx_ms = int(peak_sec * 1000)
        audio_chains.append(
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:1.0,afade=t=out:st=0.65:d=0.35,adelay={sfx_ms}|{sfx_ms},volume=0.40[sfx];"
        )
        audio_mix_labels.append("[sfx]")
        next_in += 1

    if len(audio_mix_labels) == 1:
        audio_chains.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[a]")
    else:
        audio_chains.append(
            f"{''.join(audio_mix_labels)}amix=inputs={len(audio_mix_labels)}:duration=first:dropout_transition=2:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11[a]"
        )

    fc = video_chain + "".join(audio_chains)

    cmd.extend([
        "-filter_complex", fc,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "20",
        "-threads", "0",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_file,
    ])

    print(
        f"[MAG73 Pro Editor] Rendering {output_file} | Dur={duration:.1f}s | Style={edit_type} | "
        f"WideBlur={is_wide_blur} | Peak={peak_sec:.2f}s | DuckedBGM={bool(bgm_file)}"
    )
    subprocess.run(cmd, check=True, timeout=200)

    os.makedirs("output_clips", exist_ok=True)
    cover_path = os.path.join("output_clips", output_file.replace(".mp4", ".jpg"))
    thumb_sec = min(2.0, duration / 2.0)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{thumb_sec:.2f}",
            "-i", output_file, "-frames:v", "1", "-update", "1", "-q:v", "3", cover_path,
        ],
        check=False,
        timeout=20,
    )

    return output_file
