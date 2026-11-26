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

# PRO CINEMA HDR CC VARIANTS:
# - Lifted shadow curves (ZERO crushed pitch-black faces!)
# - Crisp 3x3 micro-sharpening (sharp 1080p HD look, zero muddy artifacts)
# - Smart 2.0-second B&W Silver Burst ONLY on obsidian_bw climax (snaps back to crisp HDR color!)
VISUAL_VARIANTS = [
    {
        "name": "obsidian_silver_burst",
        "hl": "&H0015CCFA&", "pop": "&H004444FF&", "acc": "&H0015CCFA&",
        "ribbon": "0x11131C@0.82", "pbar": "0xEF4444", "border": "0xEF4444",
        "base_grade": [
            "curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.80 1/1'",
            "eq=contrast=1.08:saturation=1.15:brightness=0.01",
            "unsharp=3:3:0.55:3:3:0.0",
        ],
        "climax_grade": lambda pk: [
            f"eq=brightness=0.30:enable='between(t,{pk:.2f},{pk+0.10:.2f})'",
            f"hue=s=0:enable='between(t,{pk+0.10:.2f},{pk+2.10:.2f})'",
            f"eq=contrast=1.14:brightness=0.03:enable='between(t,{pk+0.10:.2f},{pk+2.10:.2f})'",
        ],
    },
    {
        "name": "crimson_hdr",
        "hl": "&H005555FF&", "pop": "&H0015CCFA&", "acc": "&H005555FF&",
        "ribbon": "0x7F1119@0.78", "pbar": "0xF43F5E", "border": "0xF43F5E",
        "base_grade": [
            "curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.80 1/1'",
            "eq=contrast=1.09:saturation=1.18:brightness=0.01",
            "colorbalance=rs=0.04:gs=0.00:bs=-0.02",
            "unsharp=3:3:0.55:3:3:0.0",
        ],
        "climax_grade": lambda pk: [
            f"eq=brightness=0.28:enable='between(t,{pk:.2f},{pk+0.10:.2f})'",
            f"colorbalance=rs=0.09:gs=-0.03:bs=-0.03:enable='between(t,{pk+0.10:.2f},{pk+2.20:.2f})'",
        ],
    },
    {
        "name": "ice_cinema",
        "hl": "&H00F8BD38&", "pop": "&H00FFFFFF&", "acc": "&H00F8BD38&",
        "ribbon": "0x0A192F@0.82", "pbar": "0x38BDF8", "border": "0x38BDF8",
        "base_grade": [
            "curves=m='0/0.02 0.25/0.26 0.5/0.53 0.75/0.80 1/1'",
            "eq=contrast=1.08:saturation=1.14:brightness=0.01",
            "colorbalance=rs=-0.03:gs=0.01:bs=0.05",
            "unsharp=3:3:0.55:3:3:0.0",
        ],
        "climax_grade": lambda pk: [
            f"eq=brightness=0.26:enable='between(t,{pk:.2f},{pk+0.10:.2f})'",
            f"colorbalance=rs=-0.06:gs=0.01:bs=0.10:enable='between(t,{pk+0.10:.2f},{pk+2.10:.2f})'",
        ],
    },
    {
        "name": "golden_vibrant",
        "hl": "&H0000D7FF&", "pop": "&H0080DE4A&", "acc": "&H0000D7FF&",
        "ribbon": "0x1E1506@0.82", "pbar": "0xF59E0B", "border": "0xF59E0B",
        "base_grade": [
            "curves=m='0/0.02 0.25/0.26 0.5/0.54 0.75/0.81 1/1'",
            "eq=contrast=1.08:saturation=1.22:brightness=0.02",
            "colorbalance=rs=0.04:gs=0.02:bs=-0.04",
            "unsharp=3:3:0.55:3:3:0.0",
        ],
        "climax_grade": lambda pk: [
            f"eq=brightness=0.24:enable='between(t,{pk:.2f},{pk+0.10:.2f})'",
            f"eq=contrast=1.12:saturation=1.28:enable='between(t,{pk+0.10:.2f},{pk+2.00:.2f})'",
        ],
    },
    {
        "name": "emerald_pop",
        "hl": "&H0080DE4A&", "pop": "&H0015CCFA&", "acc": "&H0080DE4A&",
        "ribbon": "0x091A14@0.82", "pbar": "0x4ADE80", "border": "0x4ADE80",
        "base_grade": [
            "curves=m='0/0.02 0.25/0.26 0.5/0.53 0.75/0.80 1/1'",
            "eq=contrast=1.09:saturation=1.18:brightness=0.01",
            "colorbalance=rs=-0.02:gs=0.03:bs=0.02",
            "unsharp=3:3:0.55:3:3:0.0",
        ],
        "climax_grade": lambda pk: [
            f"eq=brightness=0.26:enable='between(t,{pk:.2f},{pk+0.10:.2f})'",
            f"eq=contrast=1.14:saturation=1.25:enable='between(t,{pk+0.10:.2f},{pk+2.00:.2f})'",
        ],
    },
]

HYPE_WORDS = {
    "SIX", "FOUR", "OUT", "CATCH", "OMG", "WTF", "BRO", "BHAI", "ROAST", "CLUTCH",
    "YORKER", "INSANE", "CRAZY", "BOOM", "DEAD", "WIN", "AURA", "LEGEND", "COLD", "100", "200",
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
        w = int(streams[0].get("width", 1920))
        h = int(streams[0].get("height", 1080))
        dur = float((data.get("format") or {}).get("duration", 60.0))
        return w, h, dur
    except Exception:
        return 1920, 1080, 60.0


def _build_smart_face_crop_expr(video_path, start, duration, focus_x):
    """Anti-poster motion-verified speaker & central action auto-reframer."""
    fallback_x = "0.22*(iw-ow)" if focus_x == "left" else ("0.78*(iw-ow)" if focus_x == "right" else "(iw-ow)/2")
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
        step = 0.35
        t_rel = 0.0
        prev_gray = None
        prev_thumb = None

        while t_rel <= duration:
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + t_rel) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            fh, fw = frame.shape[:2]
            scale = 480.0 / max(1, fw)
            sh = max(1, int(fh * scale))
            small = cv2.resize(frame, (480, sh))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)

            thumb = cv2.resize(gray, (64, 36))
            is_cut = False
            diff_map = None
            if prev_thumb is not None and prev_gray is not None:
                scene_diff = float(np.mean(np.abs(thumb.astype(np.float32) - prev_thumb.astype(np.float32))))
                if scene_diff > 27.0:
                    is_cut = True
                else:
                    diff_map = cv2.absdiff(gray, prev_gray)
            prev_thumb = thumb
            prev_gray = gray

            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.18, minNeighbors=6, minSize=(42, 42))
            valid_faces = []
            for (fx, fy, fw_b, fh_b) in faces:
                cx_n = (fx + fw_b * 0.5) / 480.0
                cy_n = (fy + fh_b * 0.5) / float(sh)
                w_n = fw_b / 480.0

                in_bottom_corner = (cy_n > 0.44) and (cx_n > 0.68 or cx_n < 0.32)
                if in_bottom_corner and w_n < 0.28:
                    continue

                roi_motion = 10.0
                if diff_map is not None:
                    roi = diff_map[fy:fy + fh_b, fx:fx + fw_b]
                    roi_motion = float(np.mean(roi)) if roi.size > 0 else 0.0
                    if roi_motion < 4.5:
                        continue

                valid_faces.append((cx_n, w_n * w_n * (roi_motion + 1.0)))

            face_x = max(valid_faces, key=lambda x: x[1])[0] if valid_faces else None

            action_x = None
            if face_x is None and diff_map is not None:
                x1, x2 = int(480 * 0.12), int(480 * 0.76)
                y1, y2 = int(sh * 0.08), int(sh * 0.80)
                sub = diff_map[y1:y2, x1:x2]
                if sub.size > 0 and float(np.mean(sub)) > 6.0:
                    col_energy = np.mean(sub, axis=0)
                    col_energy = np.where(col_energy > np.percentile(col_energy, 65), col_energy, 0.0)
                    total_e = float(np.sum(col_energy))
                    if total_e > 0:
                        xs_idx = np.arange(x1, x2, dtype=np.float32)
                        raw_cx = float(np.sum(xs_idx * col_energy) / total_e) / 480.0
                        action_x = max(0.28, min(0.72, raw_cx * 0.55 + 0.50 * 0.45))

            samples.append({"t": round(t_rel, 2), "cut": is_cut, "fx": face_x, "ax": action_x})
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
        for sh_list in shots[:14]:
            fxs = sorted([x["fx"] for x in sh_list if x["fx"] is not None])
            axs = sorted([x["ax"] for x in sh_list if x["ax"] is not None])
            if len(fxs) >= 2:
                cx = fxs[len(fxs) // 2]
            elif axs:
                cx = axs[len(axs) // 2]
            else:
                cx = 0.50
            cx = max(0.22, min(0.75, cx))
            shot_targets.append((sh_list[0]["t"], sh_list[-1]["t"] + step, cx))

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

        print(f"[MAG73 SmartCrop] Reframed {len(merged)} shot(s): {[round(x[2],2) for x in merged]}")
        return expr
    except Exception as e:
        print(f"[MAG73 SmartCrop] Fallback to center crop: {e}")
        return fallback_x


def _snap_clean_duration(start, duration, max_file_dur, words):
    avail_max = max(8.0, min(28.0, max_file_dur - start - 0.08))
    target_end = start + duration
    if not words:
        return min(duration, avail_max)

    best_end = None
    for i, w in enumerate(words):
        we = float(w.get("end", 0))
        if target_end - 1.4 <= we <= min(start + avail_max, target_end + 1.8):
            txt = str(w.get("word", "")).strip()
            nxt_gap = (float(words[i + 1].get("start", we)) - we) if i + 1 < len(words) else 1.0
            if txt.endswith((".", "!", "?")) or nxt_gap >= 0.35:
                best_end = min(start + avail_max, we + 0.30)
                if we >= target_end - 0.4:
                    break

    if best_end and (best_end - start) >= 9.0:
        snapped = round(best_end - start, 2)
        print(f"[MAG73 Pacing] Snapped clip end cleanly: {duration:.1f}s -> {snapped:.1f}s")
        return snapped
    return min(duration, avail_max)


def _analyze_audio_and_sync_peak(video_path, start, duration, ai_peak_sec=None):
    fallback_peak = float(ai_peak_sec) if (ai_peak_sec and 2.5 <= float(ai_peak_sec) <= duration - 2.0) else max(3.5, duration * 0.50)
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
            return round(fallback_peak, 2), False

        bucket_samples = 1600
        rms_list = []
        for off in range(0, total_samples - bucket_samples + 1, bucket_samples):
            chunk = struct.unpack(f"<{bucket_samples}h", raw[off * 2:(off + bucket_samples) * 2])
            sq = sum(s * s for s in chunk) / bucket_samples
            rms_list.append(math.sqrt(sq) / 32768.0)

        if len(rms_list) < 10:
            return round(fallback_peak, 2), False

        sorted_rms = sorted(rms_list)
        p25_floor = sorted_rms[len(sorted_rms) // 4]
        has_existing_bgm = p25_floor > 0.042

        if ai_peak_sec and 2.5 <= float(ai_peak_sec) <= duration - 2.0:
            win_s = max(2.5, float(ai_peak_sec) - 1.4)
            win_e = min(duration - 1.8, float(ai_peak_sec) + 1.4)
        else:
            win_s = duration * 0.35
            win_e = duration * 0.78

        lo = min(len(rms_list) - 1, max(1, int(win_s / 0.20)))
        hi = max(lo + 1, min(len(rms_list), int(win_e / 0.20)))
        peak_idx = lo
        peak_val = -1.0
        for idx in range(lo, hi):
            if rms_list[idx] > peak_val:
                peak_val = rms_list[idx]
                peak_idx = idx

        synced_peak = round(peak_idx * 0.20, 2)
        print(f"[MAG73 DSP] Synced climax peak={synced_peak:.2f}s (AI hint={ai_peak_sec}) | ExistingBGM={has_existing_bgm}")
        return synced_peak, has_existing_bgm
    except Exception as e:
        print(f"[MAG73 DSP] Audio profile fallback: {e}")
        return round(fallback_peak, 2), False


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
                "-i", "anoisesrc=color=pink:duration=0.35:sample_rate=44100",
                "-af", "bandpass=f=950:width_type=h:w=1100,afade=t=in:st=0:d=0.12,afade=t=out:st=0.15:d=0.20,volume=0.48",
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
            expr = "sin(2*PI*(195*exp(-6.5*t)+46)*t)*exp(-4.2*t)*0.82"
            dur = "0.52"
        else:
            expr = "sin(2*PI*(110*exp(-3.0*t)+34)*t)*exp(-2.5*t)*0.86"
            dur = "0.80"
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
    words = title_text.split()
    if len(words) <= 2:
        return f"{{\\c{acc_col}}}{title_text}"
    mid = max(1, len(words) // 2)
    return " ".join(words[:mid]) + f"\\N{{\\c{acc_col}}}" + " ".join(words[mid:])


def generate_pro_ass(
    words, clip_start, clip_end, font_name, edit_type, variant, caption_style,
    is_wide_blur, title_text, impact_stamp, peak_sec, ass_path, captions_on=True
):
    hl_color = variant["hl"]
    pop_color = variant["pop"]
    acc_color = variant["acc"]

    cap_margin_v = 320 if is_wide_blur else 380
    hook_margin_v = 205 if not is_wide_blur else 255

    if caption_style == "boxed_pill":
        cap_style_line = (
            f"Style: Default,{font_name},74,&H00FFFFFF,{hl_color},&H280B0F18,&H00000000,"
            f"-1,0,0,0,100,100,1,0,3,15,0,2,60,60,{cap_margin_v},1"
        )
        max_words_chunk, max_chars_chunk = 3, 16
    elif caption_style == "neon_glow":
        cap_style_line = (
            f"Style: Default,{font_name},80,&H00FFFFFF,{hl_color},{hl_color},&HAA000000,"
            f"-1,0,0,0,100,100,2,0,1,5,3,2,60,60,{cap_margin_v},1"
        )
        max_words_chunk, max_chars_chunk = 3, 15
    elif caption_style == "word_slam":
        cap_style_line = (
            f"Style: Default,{font_name},94,&H00FFFFFF,{hl_color},&H00000000,&HC8000000,"
            f"-1,0,0,0,100,100,2,0,1,11,5,2,50,50,{cap_margin_v + 20},1"
        )
        max_words_chunk, max_chars_chunk = 2, 11
    elif caption_style == "editorial_italic":
        cap_style_line = (
            f"Style: Default,{font_name},78,&H00FFFFFF,{hl_color},&H00000000,&HB0000000,"
            f"-1,-1,0,0,100,100,1,0,1,7,4,2,65,65,{cap_margin_v},1"
        )
        max_words_chunk, max_chars_chunk = 3, 17
    else:
        cap_style_line = (
            f"Style: Default,{font_name},84,&H00FFFFFF,{hl_color},&H00000000,&HC0000000,"
            f"-1,0,0,0,100,100,1,0,1,10,5,2,60,60,{cap_margin_v},1"
        )
        max_words_chunk, max_chars_chunk = 3, 14

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{cap_style_line}
Style: Hook,{font_name},56,&H00FFFFFF,&H00FFFFFF,&H00000000,&HAA000000,-1,0,0,0,100,100,2,0,1,6,4,8,65,65,{hook_margin_v},1
Style: Stamp,{font_name},92,{acc_color},&H00FFFFFF,&H00000000,&HCC000000,-1,0,0,0,100,100,3,0,1,11,6,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    hook_end = min(3.10, max(2.2, (clip_end - clip_start) * 0.25))

    if title_text and edit_type != "clean":
        styled_hook = _format_two_line_hook(title_text, acc_color)
        anim_hook = (
            r"{\fad(80,240)\fscx76\fscy76\t(0,120,\fscx106\fscy106)\t(120,210,\fscx100\fscy100)}"
            + styled_hook
        )
        lines.append(f"Dialogue: 2,{_format_ass_time(0.08)},{_format_ass_time(hook_end)},Hook,,0,0,0,,{anim_hook}")

    if impact_stamp and edit_type in ("roast", "aura", "clash", "gaming"):
        st_s = peak_sec + 0.04
        st_e = min(clip_end - clip_start - 0.25, st_s + 1.05)
        if st_e > st_s + 0.35:
            anim_stamp = r"{\fad(40,220)\fscx155\fscy155\t(0,110,\fscx100\fscy100)}" + impact_stamp
            lines.append(f"Dialogue: 3,{_format_ass_time(st_s)},{_format_ass_time(st_e)},Stamp,,0,0,0,,{anim_stamp}")

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
                if rel_e - rel_s > 0.90:
                    rel_e = rel_s + 0.75
                if rel_e - rel_s < 0.08:
                    rel_e = rel_s + 0.16
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
            if len(current) >= max_words_chunk or (curr_len + len(w["word"]) > max_chars_chunk) or gap > 0.45:
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
                    ev_end = active_w["end"] + 0.06
                if ev_end <= ev_start + 0.05:
                    ev_end = ev_start + 0.14

                styled_parts = []
                for idx, w_obj in enumerate(chunk):
                    word_clean = re.sub(r"[^A-Z0-9]", "", w_obj["word"])
                    is_hype = word_clean in HYPE_WORDS or word_clean.isdigit()
                    if idx == active_idx:
                        col = pop_color if is_hype else hl_color
                        scale = 116 if is_hype else 110
                        if caption_style == "neon_glow":
                            styled_parts.append(
                                f"{{\\blur2\\c{col}\\fscx{scale}\\fscy{scale}}}{w_obj['word']}{{\\blur0\\c&H00FFFFFF&\\fscx100\\fscy100}}"
                            )
                        else:
                            styled_parts.append(
                                f"{{\\c{col}\\fscx{scale}\\fscy{scale}}}{w_obj['word']}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}"
                            )
                    else:
                        styled_parts.append(w_obj["word"])

                line_text = " ".join(styled_parts)
                if active_idx == 0:
                    if caption_style == "word_slam":
                        line_text = r"{\fscx125\fscy125\t(0,80,\fscx100\fscy100)}" + line_text
                    else:
                        line_text = r"{\fscx86\fscy86\t(0,60,\fscx105\fscy105)\t(60,110,\fscx100\fscy100)}" + line_text

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

        print(f"[MAG73 Captions] Template={caption_style} | {len(flat_events)} zero-overlap events.")

    if not lines:
        return None, hook_end
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines))
    return ass_path, hook_end


def _build_layout_and_motion(video_path, start, in_w, in_h, focus_x, duration, edit_type, variant, peak_sec, layout_mode):
    """
    NATIVE 1080x1920 CRYSTAL HD PIPELINE (NO 720p downscale!):
    Subtle sharp zoom (max 1.14x) preserves full 1080p clarity without pixelation!
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

    peak_bell = f"max(0,1-abs(on/30-{pk:.2f})/0.80)"
    shake_win = f"between(on/30,{pk:.2f},{pk+0.36:.2f})"

    if edit_type in ("roast", "aura"):
        z_expr = f"1.01+0.08*max(0,1-on/11)+0.04*min(1,on/{dur_frames})+0.12*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+14*sin(on*3.1)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+14*cos(on*3.6)*{shake_win},0,ih-ih/zoom)"
    elif edit_type == "aesthetic":
        z_expr = f"1.01+0.07*max(0,1-on/14)+0.06*min(1,on/{dur_frames})+0.07*{peak_bell}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"
    elif edit_type in ("funny", "gaming", "clash"):
        z_expr = f"1.00+0.08*max(0,1-on/11)+0.03*min(1,on/{dur_frames})+0.11*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+11*sin(on*3.1)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+11*cos(on*3.5)*{shake_win},0,ih-ih/zoom)"
    else:
        z_expr = f"1.00+0.06*max(0,1-on/12)+0.04*min(1,on/{dur_frames})+0.06*{peak_bell}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    if is_wide_blur:
        graph = (
            f"[0:v]fps=30,split=2[bg_src][fg_src];"
            f"[bg_src]scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:1920,"
            f"boxblur=24:6,eq=brightness=-0.05:saturation=1.22,setpts=PTS-STARTPTS[bg];"
            f"[fg_src]crop=iw*0.92:ih:iw*0.04:0,scale=1080:780:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:780,"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=1080x780:fps=30,"
            f"setpts=PTS-STARTPTS,pad=1080:788:0:4:color={variant['border']}[fg];"
            f"[bg][fg]overlay=0:(H-h)/2:shortest=1,setsar=1[base];"
        )
    else:
        face_crop_x = _build_smart_face_crop_expr(video_path, start, duration, focus_x)
        # Native full 1080x1920 Lanczos crop + zoompan for crisp HD clarity!
        graph = (
            f"[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop=1080:1920:x='{face_crop_x}':y='(ih-1920)/2',"
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
    in_w, in_h, max_file_dur = _probe_video_info(video_path)

    start = max(0.0, float(clip_data.get("start", 0)))
    end = float(clip_data.get("end", start + 18))
    raw_duration = max(8.0, min(28.0, end - start))
    duration = _snap_clean_duration(start, raw_duration, max_file_dur, word_timestamps)

    orig_start = int(float(clip_data.get("orig_start", start)))
    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "vlog"))).lower() or "vlog"

    variant_id = int(clip_data.get("variant_id", (index + orig_start) % len(VISUAL_VARIANTS))) % len(VISUAL_VARIANTS)
    variant = VISUAL_VARIANTS[variant_id]
    caption_style = str(clip_data.get("caption_style", "hormozi_pop")).strip().lower()

    layout_mode = str(clip_data.get("layout_mode", "auto")).strip().lower()
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _clean_text(clip_data.get("title_text", "")).upper() if banner_enabled else ""
    impact_stamp = _clean_text(clip_data.get("impact_stamp", "")).upper()

    ai_peak = clip_data.get("peak_sec", None)
    peak_sec, has_existing_bgm = _analyze_audio_and_sync_peak(video_path, start, duration, ai_peak_sec=ai_peak)

    mm, ss = divmod(max(0, orig_start), 60)
    output_file = f"MAG73_{edit_type.upper()}_{mm:02d}m{ss:02d}s_Clip_{index + 1}.mp4"

    bgm_file = None
    if bgm_enabled and edit_type != "clean" and not has_existing_bgm:
        bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}_{variant_id}")

    whoosh_file = _generate_whoosh_sfx(f"whoosh_{index}.mp3") if (sfx_enabled and edit_type != "clean") else None

    sfx_file = None
    if sfx_enabled and edit_type in ("roast", "aura", "aesthetic", "funny", "gaming", "clash", "drama"):
        sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}_{variant_id}")
        if not sfx_file:
            sfx_file = _generate_synth_sfx(f"synth_sfx_{index}.mp3", edit_type)

    layout_graph, is_wide_blur = _build_layout_and_motion(
        video_path, start, in_w, in_h, focus_x, duration, edit_type, variant, peak_sec, layout_mode
    )

    ass_file, hook_end = generate_pro_ass(
        word_timestamps,
        start,
        start + duration,
        font_name,
        edit_type,
        variant,
        caption_style,
        is_wide_blur,
        title_text,
        impact_stamp,
        peak_sec,
        f"cap_{index}.ass",
        captions_on=(caption_lang != "off"),
    )

    if edit_type == "clean":
        post_vf = ["eq=contrast=1.06:saturation=1.08", "unsharp=3:3:0.40:3:3:0.0"]
    else:
        post_vf = list(variant["base_grade"])
        if edit_type in ("roast", "aura", "aesthetic", "clash", "gaming", "drama", "funny"):
            post_vf.extend(variant["climax_grade"](peak_sec))

    if title_text and edit_type != "clean" and not is_wide_blur:
        post_vf.append(
            f"drawbox=x=0:y=175:w=iw:h=175:color={variant['ribbon']}:t=fill:enable='between(t,0.08,{hook_end:.2f})'"
        )

    if custom_ffmpeg and ";" not in custom_ffmpeg and "[" not in custom_ffmpeg:
        post_vf.append(custom_ffmpeg)

    if ass_file and os.path.exists(ass_file):
        post_vf.append(f"ass={ass_file}:fontsdir=.")

    video_chain = (
        f"{layout_graph}"
        f"[base]{','.join(post_vf)}[v_graded];"
        f"color=c={variant['pbar']}:s=1080x8:r=30[pbar];"
        f"[v_graded][pbar]overlay=x='-W+(W*min(t/{duration:.2f},1))':y=0:shortest=1[v];"
    )

    cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", video_path]

    bgm_vol = "0.19" if edit_type in ("roast", "aura", "aesthetic", "gaming", "clash") else "0.13"
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
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:0.35,volume=0.32[whoosh];"
        )
        audio_mix_labels.append("[whoosh]")
        next_in += 1

    if sfx_file:
        cmd.extend(["-i", sfx_file])
        sfx_ms = int(peak_sec * 1000)
        audio_chains.append(
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:0.95,afade=t=out:st=0.60:d=0.35,adelay={sfx_ms}|{sfx_ms},volume=0.38[sfx];"
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

    # Crystal HD 1080p export (High profile, CRF 18, crisp Lanczos, zero muddiness)
    cmd.extend([
        "-filter_complex", fc,
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264",
        "-profile:v", "high",
        "-pix_fmt", "yuv420p",
        "-preset", "fast",
        "-crf", "18",
        "-threads", "0",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
        output_file,
    ])

    print(
        f"[MAG73 Pro HD Editor] Rendering {output_file} ({in_w}x{in_h} -> 1080x1920 CRF18) | "
        f"Style={edit_type} | Variant={variant['name']} | CapStyle={caption_style} | Peak={peak_sec:.2f}s"
    )
    subprocess.run(cmd, check=True, timeout=240)

    os.makedirs("output_clips", exist_ok=True)
    cover_path = os.path.join("output_clips", output_file.replace(".mp4", ".jpg"))
    thumb_sec = min(2.0, duration / 2.0)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{thumb_sec:.2f}",
            "-i", output_file, "-frames:v", "1", "-update", "1", "-q:v", "2", cover_path,
        ],
        check=False,
        timeout=20,
    )

    return output_file
