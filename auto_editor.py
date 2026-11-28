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

# HIGH-RES 512x512 NOTO EMOJI PNGs (with Twemoji CDN fallback) — CRISP REAL IG REELS EMOJIS!
EMOJI_CODES = {
    "skull": "1f480",
    "heart": "2764",
    "fire": "1f525",
    "cold": "1f976",
    "laugh": "1f602",
    "crown": "1f451",
    "eyes": "1f440",
    "broken_heart": "1f494",
    "mindblown": "1f92f",
    "hundred": "1f4af",
    "cool": "1f60e",
}

# =============================================================================
# ALL 22 INSTAGRAM REEL SUB-TYPE BLUEPRINTS
# mode: "two_part_drop" (real slow-mo + beat-drop song switch!) OR "continuous"
# hook_style: "red_ribbon" | "letterbox_top" | "minimal_glow" | "aqua_glow" | "italic_warm" | "top_pill"
# drop_cc: "bw_dark" | "sepia_warm" | "crimson" | "ice_blue" | "aesthetic_glow" | "hdr_punch"
# =============================================================================
SUBTYPE_SPECS = {
    # --- 1. AURA / ROAST / SAVAGE (8 SUB-TYPES) ---
    "roast_red_ribbon_drop": {
        "mode": "two_part_drop", "hook_style": "red_ribbon", "drop_cc": "bw_dark",
        "slow_factor": 1.42, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H0015CCFA&", "hl": "&H0015CCFA&", "pbar": "0xEF4444", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.81 1/1'", "eq=contrast=1.12:saturation=1.18:brightness=0.01", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "roast_double_meaning": {
        "mode": "two_part_drop", "hook_style": "red_ribbon", "drop_cc": "hdr_punch",
        "slow_factor": 1.35, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H0015CCFA&", "hl": "&H0000D7FF&", "pbar": "0xF59E0B", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.26 0.5/0.53 0.75/0.81 1/1'", "eq=contrast=1.10:saturation=1.20:brightness=0.01", "unsharp=3:3:0.60:3:3:0.0"],
    },
    "aura_minimal_glow": {
        "mode": "two_part_drop", "hook_style": "minimal_glow", "drop_cc": "bw_dark",
        "slow_factor": 1.48, "shake": True, "flash": True, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H00F8BD38&", "pbar": "0x38BDF8", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.24 0.5/0.52 0.75/0.80 1/1'", "eq=contrast=1.14:saturation=0.95:brightness=-0.01", "vignette=PI/6", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "aura_skull_freeze": {
        "mode": "two_part_drop", "hook_style": "green_glow", "drop_cc": "bw_dark",
        "slow_factor": 1.72, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H0080DE4A&", "hl": "&H0080DE4A&", "pbar": "0x4ADE80", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.81 1/1'", "eq=contrast=1.14:saturation=1.12", "unsharp=3:3:0.70:3:3:0.0"],
    },
    "aura_mindset_statement": {
        "mode": "continuous", "hook_style": "minimal_glow", "drop_cc": "hdr_punch",
        "slow_factor": 1.0, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0015CCFA&", "pbar": "0xF59E0B", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.24 0.5/0.52 0.75/0.80 1/1'", "eq=contrast=1.15:saturation=0.92:brightness=-0.01", "vignette=PI/5", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "aura_velocity_ramp": {
        "mode": "two_part_drop", "hook_style": "top_pill", "drop_cc": "hdr_punch",
        "slow_factor": 1.50, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H0000D7FF&", "hl": "&H0000D7FF&", "pbar": "0xF97316", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.82 1/1'", "eq=contrast=1.14:saturation=1.22", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "aura_crimson_devil": {
        "mode": "two_part_drop", "hook_style": "red_ribbon", "drop_cc": "crimson",
        "slow_factor": 1.45, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H005555FF&", "hl": "&H005555FF&", "pbar": "0xF43F5E", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.24 0.5/0.52 0.75/0.80 1/1'", "eq=contrast=1.14:saturation=1.08", "vignette=PI/6", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "aura_ice_cold_drop": {
        "mode": "two_part_drop", "hook_style": "aqua_glow", "drop_cc": "ice_blue",
        "slow_factor": 1.48, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H00F8BD38&", "hl": "&H00F8BD38&", "pbar": "0x38BDF8", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.80 1/1'", "eq=contrast=1.12:saturation=1.04", "colorbalance=rs=-0.04:gs=0.01:bs=0.06", "unsharp=3:3:0.65:3:3:0.0"],
    },

    # --- 2. EMOTIONAL / BROTHERHOOD / STORYTELLING (4 SUB-TYPES) ---
    "emo_brotherhood_story": {
        "mode": "continuous", "hook_style": "italic_warm", "drop_cc": "aesthetic_glow",
        "slow_factor": 1.0, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0015CCFA&", "pbar": "0xF59E0B", "letterbox": False,
        "base_cc": ["curves=m='0/0.03 0.25/0.26 0.5/0.53 0.75/0.80 1/1'", "eq=contrast=1.08:saturation=1.06:brightness=0.01", "colorbalance=rs=0.05:gs=0.02:bs=-0.04", "vignette=PI/6", "unsharp=3:3:0.45:3:3:0.0"],
    },
    "emo_wholesome_heart_drop": {
        "mode": "two_part_drop", "hook_style": "aqua_glow", "drop_cc": "sepia_warm",
        "slow_factor": 1.45, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H00EED322&", "hl": "&H00EED322&", "pbar": "0x22D3EE", "letterbox": False,
        "base_cc": ["curves=m='0/0.03 0.25/0.26 0.5/0.54 0.75/0.81 1/1'", "eq=contrast=1.08:saturation=1.14:brightness=0.01", "unsharp=3:3:0.45:3:3:0.0"],
    },
    "emo_moody_tribute": {
        "mode": "continuous", "hook_style": "minimal_glow", "drop_cc": "aesthetic_glow",
        "slow_factor": 1.0, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0000D7FF&", "pbar": "0xFACC15", "letterbox": False,
        "base_cc": ["curves=m='0/0.03 0.25/0.26 0.5/0.53 0.75/0.80 1/1'", "eq=contrast=1.10:saturation=0.98", "colorbalance=rs=0.03:gs=0.01:bs=0.03", "vignette=PI/5", "unsharp=3:3:0.45:3:3:0.0"],
    },
    "emo_broken_silence": {
        "mode": "two_part_drop", "hook_style": "italic_warm", "drop_cc": "ice_blue",
        "slow_factor": 1.50, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H00F8BD38&", "hl": "&H00F8BD38&", "pbar": "0x60A5FA", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.24 0.5/0.51 0.75/0.78 1/1'", "eq=contrast=1.10:saturation=0.82", "vignette=PI/5"],
    },

    # --- 3. COMEDY / REALITY SHOW / MEME (4 SUB-TYPES) ---
    "comedy_letterbox_classic": {
        "mode": "continuous", "hook_style": "letterbox_top", "drop_cc": "hdr_punch",
        "slow_factor": 1.0, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0015CCFA&", "pbar": "0xFACC15", "letterbox": True,
        "base_cc": ["eq=contrast=1.08:saturation=1.16:brightness=0.02", "unsharp=3:3:0.50:3:3:0.0"],
    },
    "comedy_letterbox_lyric": {
        "mode": "two_part_drop", "hook_style": "letterbox_top", "drop_cc": "hdr_punch",
        "slow_factor": 1.35, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H0015CCFA&", "hl": "&H0015CCFA&", "pbar": "0xFACC15", "letterbox": True,
        "base_cc": ["eq=contrast=1.09:saturation=1.18:brightness=0.02", "unsharp=3:3:0.50:3:3:0.0"],
    },
    "comedy_red_ribbon": {
        "mode": "continuous", "hook_style": "red_ribbon", "drop_cc": "hdr_punch",
        "slow_factor": 1.0, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0015CCFA&", "pbar": "0xEF4444", "letterbox": False,
        "base_cc": ["eq=contrast=1.09:saturation=1.20:brightness=0.02", "unsharp=3:3:0.50:3:3:0.0"],
    },
    "comedy_meme_pop": {
        "mode": "continuous", "hook_style": "top_pill", "drop_cc": "hdr_punch",
        "slow_factor": 1.0, "shake": True, "flash": False, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0080DE4A&", "pbar": "0xFACC15", "letterbox": False,
        "base_cc": ["eq=contrast=1.10:saturation=1.22:brightness=0.02", "unsharp=3:3:0.55:3:3:0.0"],
    },

    # --- 4. GAMING / ESPORTS (4 SUB-TYPES) ---
    "gaming_stacked_comeback": {
        "mode": "two_part_drop", "hook_style": "top_pill", "drop_cc": "hdr_punch",
        "slow_factor": 1.38, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H0080DE4A&", "hl": "&H0080DE4A&", "pbar": "0x4ADE80", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.54 0.75/0.82 1/1'", "eq=contrast=1.12:saturation=1.24", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "gaming_esports_montage": {
        "mode": "continuous", "hook_style": "top_pill", "drop_cc": "hdr_punch",
        "slow_factor": 1.0, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H00EED322&", "hl": "&H0080DE4A&", "pbar": "0x22D3EE", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.54 0.75/0.82 1/1'", "eq=contrast=1.13:saturation=1.22", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "gaming_clutch_skull": {
        "mode": "two_part_drop", "hook_style": "red_ribbon", "drop_cc": "bw_dark",
        "slow_factor": 1.55, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H005555FF&", "hl": "&H0080DE4A&", "pbar": "0xEF4444", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.81 1/1'", "eq=contrast=1.13:saturation=1.20", "unsharp=3:3:0.65:3:3:0.0"],
    },
    "gaming_lobby_troll": {
        "mode": "continuous", "hook_style": "letterbox_top", "drop_cc": "hdr_punch",
        "slow_factor": 1.0, "shake": True, "flash": False, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0080DE4A&", "pbar": "0xFACC15", "letterbox": True,
        "base_cc": ["eq=contrast=1.10:saturation=1.20:brightness=0.01", "unsharp=3:3:0.55:3:3:0.0"],
    },

    # --- 5. BANTER-TO-AESTHETIC / VIBE-SWITCH (2 SUB-TYPES) ---
    "switch_banter_aesthetic": {
        "mode": "two_part_drop", "hook_style": "red_ribbon", "drop_cc": "aesthetic_glow",
        "slow_factor": 1.52, "shake": False, "flash": True, "stamp_on_drop": False,
        "acc": "&H0015CCFA&", "hl": "&H0015CCFA&", "pbar": "0xF59E0B", "letterbox": False,
        "base_cc": ["eq=contrast=1.08:saturation=1.18:brightness=0.02", "unsharp=3:3:0.50:3:3:0.0"],
    },
    "switch_attitude_drop": {
        "mode": "two_part_drop", "hook_style": "minimal_glow", "drop_cc": "crimson",
        "slow_factor": 1.45, "shake": True, "flash": True, "stamp_on_drop": True,
        "acc": "&H0000D7FF&", "hl": "&H0000D7FF&", "pbar": "0xEF4444", "letterbox": False,
        "base_cc": ["curves=m='0/0.02 0.25/0.25 0.5/0.53 0.75/0.81 1/1'", "eq=contrast=1.12:saturation=1.14", "unsharp=3:3:0.60:3:3:0.0"],
    },

    # --- CLEAN ---
    "clean_minimal": {
        "mode": "continuous", "hook_style": "top_pill", "drop_cc": "hdr_punch",
        "slow_factor": 1.0, "shake": False, "flash": False, "stamp_on_drop": False,
        "acc": "&H00FFFFFF&", "hl": "&H0015CCFA&", "pbar": "0x6366F1", "letterbox": False,
        "base_cc": ["eq=contrast=1.06:saturation=1.08", "unsharp=3:3:0.40:3:3:0.0"],
    },
}

HYPE_WORDS = {
    "INSANE", "COLD", "AURA", "LEGEND", "GOAT", "KING", "BOSS", "BEAST", "SAVAGE", "LETHAL",
    "COOKED", "ROAST", "ROASTED", "VIOLATION", "EXPOSED", "DESTROYED", "HUMBLED", "OWNED",
    "CRAZY", "WILD", "CHAOS", "OMG", "WTF", "BHAI", "AREY", "KHATAM", "CLUTCH", "HEADSHOT",
    "ACE", "WIPE", "HACKER", "CRACKED", "CLEAN", "OP", "GG", "WIN", "BOOM", "BANG", "SIX",
    "FOUR", "OUT", "CATCH", "YORKER", "ZABARDAST", "GAJAB", "FIRE", "SYSTUM", "100", "200",
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


def _download_emoji_png(emoji_name):
    """Downloads a razor-sharp 512x512 transparent emoji PNG (Noto -> Twemoji fallback)."""
    name = (emoji_name or "").strip().lower()
    if not name or name == "none" or name not in EMOJI_CODES:
        return None
    code = EMOJI_CODES[name]
    out_path = f"emoji_{name}.png"
    if os.path.exists(out_path) and os.path.getsize(out_path) > 1000:
        return out_path

    urls = [
        f"https://raw.githubusercontent.com/googlefonts/noto-emoji/main/png/512/emoji_u{code}.png",
        f"https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/{code}.png",
    ]
    for u in urls:
        try:
            r = requests.get(u, timeout=12)
            if r.status_code == 200 and len(r.content) > 800:
                with open(out_path, "wb") as f:
                    f.write(r.content)
                print(f"[MAG73 Emoji] Loaded HD PNG overlay: {name}")
                return out_path
        except Exception:
            continue
    return None


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


def _probe_audio_duration(audio_path):
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", audio_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return max(1.0, float(out))
    except Exception:
        return 30.0


def _detect_top_facecam_vertical(video_path, start, duration):
    if not HAS_CV2:
        return False
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return False
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            cap.release()
            return False

        hits = 0
        for sec_off in (0.5, 1.5, 2.5, 4.0):
            if sec_off > duration:
                break
            cap.set(cv2.CAP_PROP_POS_MSEC, (start + sec_off) * 1000.0)
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            fh, fw = frame.shape[:2]
            if fh <= fw:
                break
            top_strip = frame[0:int(fh * 0.32), :]
            gray = cv2.cvtColor(top_strip, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5, minSize=(40, 40))
            if len(faces) > 0:
                hits += 1
        cap.release()
        return hits >= 2
    except Exception:
        return False


def _build_smart_face_crop_expr(video_path, start, duration, focus_x):
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
            if fh >= fw:
                cap.release()
                return "(iw-ow)/2"

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

        return expr
    except Exception:
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
        return round(best_end - start, 2)
    return min(duration, avail_max)


def _analyze_audio_and_sync_peak(video_path, start, duration, ai_peak_sec=None, is_live=False):
    fallback_peak = float(ai_peak_sec) if (ai_peak_sec and 4.0 <= float(ai_peak_sec) <= duration - 2.8) else max(4.5, duration * 0.58)
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
        bgm_thresh = 0.095 if is_live else 0.080
        has_existing_bgm = p25_floor > bgm_thresh

        if ai_peak_sec and 4.0 <= float(ai_peak_sec) <= duration - 2.8:
            win_s = max(4.0, float(ai_peak_sec) - 1.3)
            win_e = min(duration - 2.8, float(ai_peak_sec) + 1.3)
        else:
            win_s = max(4.0, duration * 0.45)
            win_e = max(win_s + 1.0, duration - 3.0)

        lo = min(len(rms_list) - 1, max(1, int(win_s / 0.20)))
        hi = max(lo + 1, min(len(rms_list), int(win_e / 0.20)))
        peak_idx = lo
        peak_val = -1.0
        for idx in range(lo, hi):
            if rms_list[idx] > peak_val:
                peak_val = rms_list[idx]
                peak_idx = idx

        synced_peak = round(peak_idx * 0.20, 2)
        return synced_peak, has_existing_bgm
    except Exception:
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


def _generate_synth_boom(out_path):
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "aevalsrc=sin(2*PI*(120*exp(-3.2*t)+34)*t)*exp(-2.3*t)*0.92:d=0.90:s=44100",
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


def _format_ig_two_line(title_text, acc_col, white_first=True):
    words = title_text.split()
    if len(words) <= 2:
        return f"{{\\c{acc_col}}}{title_text}"
    mid = max(1, len(words) // 2)
    l1 = " ".join(words[:mid])
    l2 = " ".join(words[mid:])
    if white_first:
        return f"{{\\c&H00FFFFFF&}}{l1}\\N{{\\c{acc_col}}}{l2}"
    return f"{{\\c{acc_col}}}{l1}\\N{{\\c&H00FFFFFF&}}{l2}"


def _build_drop_cc_filters(drop_cc):
    """Exact Instagram Reels Climax Color Grades (Part 2)."""
    if drop_cc == "bw_dark":
        return ["hue=s=0", "eq=contrast=1.22:brightness=-0.02", "vignette=PI/5", "unsharp=3:3:0.75:3:3:0.0"]
    if drop_cc == "sepia_warm":
        return [
            "hue=s=0.18",
            "colorbalance=rs=0.10:gs=0.04:bs=-0.08",
            "eq=contrast=1.14:brightness=0.01",
            "vignette=PI/5",
        ]
    if drop_cc == "crimson":
        return [
            "eq=contrast=1.22:saturation=0.72:brightness=-0.02",
            "colorbalance=rs=0.16:gs=-0.06:bs=-0.06",
            "vignette=PI/5",
            "unsharp=3:3:0.70:3:3:0.0",
        ]
    if drop_cc == "ice_blue":
        return [
            "eq=contrast=1.18:saturation=0.80:brightness=-0.01",
            "colorbalance=rs=-0.10:gs=0.02:bs=0.16",
            "vignette=PI/5",
            "unsharp=3:3:0.70:3:3:0.0",
        ]
    if drop_cc == "aesthetic_glow":
        return [
            "curves=m='0/0.04 0.25/0.28 0.5/0.56 0.75/0.83 1/1'",
            "eq=contrast=1.12:saturation=1.24:brightness=0.03",
            "colorbalance=rs=0.06:gs=0.02:bs=-0.04",
            "vignette=PI/6",
            "unsharp=3:3:0.55:3:3:0.0",
        ]
    # hdr_punch
    return [
        "curves=m='0/0.02 0.25/0.25 0.5/0.54 0.75/0.83 1/1'",
        "eq=contrast=1.18:saturation=1.28:brightness=0.01",
        "unsharp=3:3:0.75:3:3:0.0",
    ]


def _generate_ass_file(
    ass_path, font_name, spec, clip_dur, title_text, words, word_offset_s,
    caption_style, has_top_facecam, captions_on, is_ig_minimal_cap,
    stamp_text="", stamp_start=0.0, stamp_dur=0.0
):
    """
    Generates pixel-perfect Instagram Reels typography using exact \\an5\\pos(540,Y):
    - Persistent Story Hook stays ON the entire segment (NEVER vanishes after 3s!).
    - Clean non-clashing captions so faces & ribbons always stay crystal clear.
    """
    hook_style = spec["hook_style"]
    acc = spec["acc"]
    hl = spec["hl"]

    # Hook Style & Exact Y coordinate
    hook_y = 1250
    hook_italic = 0
    hook_size = 56
    hook_outline = 6
    hook_border_style = 1
    hook_outline_col = "&H00000000"
    hook_blur = 0.0

    if hook_style == "red_ribbon":
        hook_y = 1245
        hook_size = 54
        hook_outline = 5
    elif hook_style == "letterbox_top":
        hook_y = 335
        hook_size = 54
        hook_outline = 3
    elif hook_style == "italic_warm":
        hook_y = 1410
        hook_size = 50
        hook_italic = -1
        hook_outline = 5
        hook_blur = 1.2
    elif hook_style == "aqua_glow":
        hook_y = 1380
        hook_size = 52
        hook_outline = 5
        hook_blur = 1.5
    elif hook_style == "green_glow":
        hook_y = 1380
        hook_size = 54
        hook_outline = 5
        hook_blur = 1.4
    elif hook_style == "minimal_glow":
        hook_y = 1400
        hook_size = 52
        hook_outline = 5
        hook_blur = 1.2
    else:  # top_pill
        hook_y = 540 if has_top_facecam else 255
        hook_size = 50
        hook_border_style = 3
        hook_outline = 16
        hook_outline_col = "&H260E1220"

    # Caption styling: sleek smaller IG subtitles when Story Hook is active, bold Hormozi on gaming/clean!
    cap_margin_v = 195 if is_ig_minimal_cap else 340
    cap_size = 56 if is_ig_minimal_cap else (82 if caption_style == "word_slam" else 74)
    if spec["letterbox"]:
        cap_margin_v = 230
        cap_size = 54

    if caption_style == "boxed_pill" and not is_ig_minimal_cap:
        cap_style_line = f"Style: Default,{font_name},{cap_size},&H00FFFFFF,{hl},&H280B0F18,&H00000000,-1,0,0,0,100,100,1,0,3,14,0,2,60,60,{cap_margin_v},1"
    elif caption_style == "editorial_italic":
        cap_style_line = f"Style: Default,{font_name},{cap_size},&H00FFFFFF,{hl},&H00000000,&HB0000000,-1,-1,0,0,100,100,1,0,1,6,3,2,60,60,{cap_margin_v},1"
    else:
        cap_style_line = f"Style: Default,{font_name},{cap_size},&H00FFFFFF,{hl},&H00000000,&HC0000000,-1,0,0,0,100,100,1,0,1,8,4,2,60,60,{cap_margin_v},1"

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{cap_style_line}
Style: Hook,{font_name},{hook_size},&H00FFFFFF,&H00FFFFFF,{hook_outline_col},&HAA000000,-1,{hook_italic},0,0,100,100,2,0,{hook_border_style},{hook_outline},3,5,65,65,40,1
Style: Stamp,{font_name},96,{acc},&H00FFFFFF,&H00000000,&HCC000000,-1,0,0,0,100,100,3,0,1,12,6,5,40,40,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []

    # 1. PERSISTENT IG STORY HOOK (stays from 0.05s all the way to clip_dur!)
    if title_text:
        white_first = hook_style not in ("aqua_glow", "green_glow")
        styled_hook = _format_ig_two_line(title_text, acc, white_first=white_first)
        blur_tag = f"\\blur{hook_blur}" if hook_blur > 0 else ""
        anim_hook = (
            f"{{\\an5\\pos(540,{hook_y}){blur_tag}\\fad(120,180)"
            r"\fscx85\fscy85\t(0,140,\fscx103\fscy103)\t(140,240,\fscx100\fscy100)}"
            + styled_hook
        )
        lines.append(f"Dialogue: 2,{_format_ass_time(0.05)},{_format_ass_time(max(0.5, clip_dur - 0.05))},Hook,,0,0,0,,{anim_hook}")

    # 2. CLIMAX IMPACT STAMP (for beat-drop / hype punch!)
    if stamp_text and stamp_dur > 0.3:
        st_e = min(clip_dur - 0.05, stamp_start + stamp_dur)
        if st_e > stamp_start + 0.25:
            anim_stamp = r"{\an5\pos(540,780)\fad(40,240)\fscx165\fscy165\t(0,110,\fscx100\fscy100)}" + stamp_text
            lines.append(f"Dialogue: 3,{_format_ass_time(stamp_start)},{_format_ass_time(st_e)},Stamp,,0,0,0,,{anim_stamp}")

    # 3. ZERO-OVERLAP CAPTIONS
    if captions_on and words:
        raw_clip_words = []
        for w in words:
            ws = float(w.get("start", 0)) - word_offset_s
            we = float(w.get("end", ws + 0.25)) - word_offset_s
            txt = _clean_text(w.get("word", "")).upper()
            if not txt:
                continue
            if we >= 0.0 and ws <= clip_dur:
                rel_s = max(0.0, ws)
                rel_e = min(clip_dur, we)
                if rel_e - rel_s > 0.85:
                    rel_e = rel_s + 0.72
                if rel_e - rel_s < 0.08:
                    rel_e = rel_s + 0.16
                raw_clip_words.append({"word": txt, "start": rel_s, "end": rel_e})

        raw_clip_words.sort(key=lambda x: x["start"])
        max_w = 4 if is_ig_minimal_cap else (2 if caption_style == "word_slam" else 3)
        max_c = 22 if is_ig_minimal_cap else (11 if caption_style == "word_slam" else 15)

        chunks = []
        current = []
        for w in raw_clip_words:
            if not current:
                current.append(w)
                continue
            gap = w["start"] - current[-1]["end"]
            curr_len = sum(len(x["word"]) + 1 for x in current)
            if len(current) >= max_w or (curr_len + len(w["word"]) > max_c) or gap > 0.45:
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
                ev_end = chunk[active_idx + 1]["start"] if active_idx + 1 < len(chunk) else (active_w["end"] + 0.06)
                if ev_end <= ev_start + 0.05:
                    ev_end = ev_start + 0.14

                styled_parts = []
                for idx, w_obj in enumerate(chunk):
                    word_clean = re.sub(r"[^A-Z0-9]", "", w_obj["word"])
                    is_hype = word_clean in HYPE_WORDS or word_clean.isdigit()
                    if idx == active_idx:
                        scale = 114 if is_hype else 108
                        styled_parts.append(
                            f"{{\\c{hl}\\fscx{scale}\\fscy{scale}}}{w_obj['word']}{{\\c&H00FFFFFF&\\fscx100\\fscy100}}"
                        )
                    else:
                        styled_parts.append(w_obj["word"])
                flat_events.append({"start": ev_start, "end": ev_end, "text": " ".join(styled_parts)})

        for i in range(len(flat_events) - 1):
            if flat_events[i]["end"] >= flat_events[i + 1]["start"]:
                flat_events[i]["end"] = max(flat_events[i]["start"] + 0.04, flat_events[i + 1]["start"] - 0.01)

        for ev in flat_events:
            if ev["end"] > ev["start"] + 0.02:
                lines.append(
                    f"Dialogue: 0,{_format_ass_time(ev['start'])},{_format_ass_time(ev['end'])},Default,,0,0,0,,{ev['text']}"
                )

    if not lines:
        return None
    with open(ass_path, "w", encoding="utf-8") as f:
        f.write(header + "\n".join(lines))
    return ass_path


def _build_base_frame_chain(video_path, start, dur, in_w, in_h, focus_x, spec, z_expr, x_expr, y_expr):
    """Builds either Classic IG Letterbox (black bars) or 1080x1920 Full-Screen Motion-Tracked Vertical."""
    if spec["letterbox"]:
        # Solid black IG Meme Letterbox (1080x1920) with crisp centered video!
        vid_h = 880 if in_w >= in_h else 1120
        return (
            f"color=c=black:s=1080x1920:r=30:d={dur:.2f}[bg_blk];"
            f"[0:v]fps=30,scale=1080:{vid_h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop=1080:{vid_h},"
            f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=1080x{vid_h}:fps=30,"
            f"setpts=PTS-STARTPTS[fg_vid];"
            f"[bg_blk][fg_vid]overlay=0:(H-h)/2:shortest=1,setsar=1,format=yuv420p[base];"
        )

    face_crop_x = _build_smart_face_crop_expr(video_path, start, dur, focus_x)
    return (
        f"[0:v]fps=30,scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop=1080:1920:x='{face_crop_x}':y='(ih-1920)/2',"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d=1:s=1080x1920:fps=30,"
        f"setpts=PTS-STARTPTS,setsar=1,format=yuv420p[base];"
    )


def _render_two_part_drop_reel(
    video_path, start, duration, peak_sec, in_w, in_h, focus_x, spec, subtype,
    font_name, words, caption_style, has_top_facecam, title_text, impact_stamp,
    emoji_png, bgm_file, sfx_file, sfx_kind, custom_ffmpeg, captions_on, output_file, index
):
    """
    TRUE INSTAGRAM REELS 2-PART BEAT-DROP ARCHITECTURE:
    - PART 1 (0 to peak_sec): Crisp buildup + PERSISTENT Story Hook/Red Ribbon/Letterbox + synced dialogue & captions + subtle intro/laugh SFX.
    - PART 2 (peak_sec to end): Hard white flash + REAL SLOW-MO (0.60x-0.74x) + Climax CC (B&W/Sepia/Crimson/Ice/Glow) +
      Camera Shake + High-Res Emoji PNG Pop + Impact Stamp + LOUD BEAT-DROP SONG SWITCH (seeks right into the beat)!
    """
    p1_dur = max(4.5, min(duration - 3.0, peak_sec))
    p2_src_dur = max(2.6, min(4.2, duration - p1_dur))
    slow_f = float(spec.get("slow_factor", 1.42))
    p2_out_dur = round(p2_src_dur * slow_f, 2)

    p1_file = f"part1_{index}.mp4"
    p2_file = f"part2_{index}.mp4"

    # ==================== RENDER PART 1 (BUILDUP) ====================
    p1_frames = max(30, int(p1_dur * 30))
    z1 = f"1.01+0.07*max(0,1-on/12)+0.05*min(1,on/{p1_frames})"
    base1 = _build_base_frame_chain(
        video_path, start, p1_dur, in_w, in_h, focus_x, spec,
        z1, "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    )

    ass1 = _generate_ass_file(
        f"ass_p1_{index}.ass", font_name, spec, p1_dur, title_text,
        words, start, caption_style, has_top_facecam, captions_on,
        is_ig_minimal_cap=True,
    )

    vf1 = list(spec["base_cc"])
    # Translucent Red Ribbon behind persistent hook (stays ON for ALL of Part 1!)
    if title_text and spec["hook_style"] == "red_ribbon":
        vf1.append("drawbox=x=0:y=1150:w=iw:h=190:color=0x99111B@0.76:t=fill")
    if custom_ffmpeg and ";" not in custom_ffmpeg and "[" not in custom_ffmpeg:
        vf1.append(custom_ffmpeg)
    if ass1 and os.path.exists(ass1):
        vf1.append(f"ass={ass1}:fontsdir=.")

    cmd1 = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{p1_dur:.3f}", "-i", video_path]
    a_labels1 = ["[v_main]"]
    a_chains1 = [
        "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,highpass=f=85,"
        "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.20[v_main];"
    ]
    next_i1 = 1

    # For emotional heart drop or banter switch, play gentle buildup music under Part 1
    if bgm_file and subtype in ("emo_wholesome_heart_drop", "emo_broken_silence"):
        cmd1.extend(["-stream_loop", "-1", "-i", bgm_file])
        a_chains1.append(
            f"[{next_i1}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:{p1_dur:.2f},asetpts=PTS-STARTPTS,afade=t=in:st=0:d=0.6,volume=0.12[bgm1];"
        )
        a_labels1.append("[bgm1]")
        next_i1 += 1

    # Add viral laugh SFX near end of Part 1 for banter/comedy switch!
    if sfx_file and sfx_kind == "laugh":
        cmd1.extend(["-i", sfx_file])
        delay_ms = int(max(0.5, p1_dur - 1.4) * 1000)
        a_chains1.append(
            f"[{next_i1}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:1.3,adelay={delay_ms}|{delay_ms},volume=0.45[lsfx];"
        )
        a_labels1.append("[lsfx]")
        next_i1 += 1

    if len(a_labels1) == 1:
        a_chains1.append("[v_main]loudnorm=I=-14:TP=-1.5:LRA=11[a1]")
    else:
        a_chains1.append(
            f"{''.join(a_labels1)}amix=inputs={len(a_labels1)}:duration=first:dropout_transition=2:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11[a1]"
        )

    fc1 = f"{base1}[base]{','.join(vf1)},format=yuv420p[v1];" + "".join(a_chains1)
    cmd1.extend([
        "-filter_complex", fc1, "-map", "[v1]", "-map", "[a1]",
        "-t", f"{p1_dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        p1_file,
    ])
    subprocess.run(cmd1, check=True, timeout=140)

    # ==================== RENDER PART 2 (SLOW-MO CLIMAX DROP + SONG SWITCH + EMOJI PNG) ====================
    p2_start = start + p1_dur
    shake_win = "between(on/30,0.00,0.42)"
    z2 = f"1.04+0.12*max(0,1-on/10)+0.06*min(1,on/{max(30, int(p2_out_dur * 30))})"
    x2 = f"clip(iw/2-(iw/zoom/2)+18*sin(on*3.3)*{shake_win},0,iw-iw/zoom)" if spec["shake"] else "iw/2-(iw/zoom/2)"
    y2 = f"clip(ih/2-(ih/zoom/2)+18*cos(on*3.8)*{shake_win},0,ih-ih/zoom)" if spec["shake"] else "ih/2-(ih/zoom/2)"

    # Slow-mo time stretch on video BEFORE zoompan so motion stays buttery 30fps!
    if spec["letterbox"]:
        vid_h = 880 if in_w >= in_h else 1120
        base2 = (
            f"color=c=black:s=1080x1920:r=30:d={p2_out_dur:.2f}[bg_blk];"
            f"[0:v]setpts={slow_f:.2f}*PTS,fps=30,"
            f"scale=1080:{vid_h}:force_original_aspect_ratio=increase:flags=lanczos,crop=1080:{vid_h},"
            f"zoompan=z='{z2}':x='{x2}':y='{y2}':d=1:s=1080x{vid_h}:fps=30,"
            f"setpts=PTS-STARTPTS[fg_vid];"
            f"[bg_blk][fg_vid]overlay=0:(H-h)/2:shortest=1,setsar=1,format=yuv420p[base];"
        )
    else:
        crop_x2 = _build_smart_face_crop_expr(video_path, p2_start, p2_src_dur, focus_x)
        base2 = (
            f"[0:v]setpts={slow_f:.2f}*PTS,fps=30,"
            f"scale=1080:1920:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop=1080:1920:x='{crop_x2}':y='(ih-1920)/2',"
            f"zoompan=z='{z2}':x='{x2}':y='{y2}':d=1:s=1080x1920:fps=30,"
            f"setpts=PTS-STARTPTS,setsar=1,format=yuv420p[base];"
        )

    vf2 = []
    if spec["flash"]:
        vf2.append("eq=brightness=0.38:enable='between(t,0.00,0.11)'")
    vf2.extend(_build_drop_cc_filters(spec["drop_cc"]))

    # Keep top caption in Letterbox Lyric Outro, otherwise clear hook & pop Impact Stamp!
    p2_hook = title_text if spec["letterbox"] else ""
    p2_stamp = impact_stamp if spec["stamp_on_drop"] else ""
    ass2 = _generate_ass_file(
        f"ass_p2_{index}.ass", font_name, spec, p2_out_dur, p2_hook,
        [], 0.0, caption_style, has_top_facecam, captions_on=False,
        is_ig_minimal_cap=True,
        stamp_text=p2_stamp, stamp_start=0.10, stamp_dur=min(1.8, p2_out_dur - 0.3),
    )
    if ass2 and os.path.exists(ass2):
        vf2.append(f"ass={ass2}:fontsdir=.")

    cmd2 = ["ffmpeg", "-y", "-ss", f"{p2_start:.3f}", "-t", f"{p2_src_dur:.3f}", "-i", video_path]
    next_i2 = 1

    # Video chain + High-Res Emoji PNG Pop Overlay!
    if emoji_png and os.path.exists(emoji_png):
        cmd2.extend(["-loop", "1", "-i", emoji_png])
        em_idx = next_i2
        next_i2 += 1
        em_y = 1040 if p2_stamp else 1280
        em_size = 185 if subtype == "aura_skull_freeze" else 160
        v_chain2 = (
            f"{base2}[base]{','.join(vf2)}[v_cc];"
            f"[{em_idx}:v]format=rgba,scale={em_size}:-1:flags=lanczos,"
            f"fade=t=in:st=0.08:d=0.14:alpha=1,fade=t=out:st={max(0.5, p2_out_dur-0.45):.2f}:d=0.40:alpha=1[em];"
            f"[v_cc][em]overlay=x=(W-w)/2:y={em_y}:shortest=1,format=yuv420p[v2];"
        )
    else:
        v_chain2 = f"{base2}[base]{','.join(vf2)},format=yuv420p[v2];"

    # Audio chain for Part 2: Original voice fades out cleanly -> LOUD BEAT-DROP SONG TAKES OVER!
    a_labels2 = ["[v_tail]"]
    a_chains2 = [
        f"[0:a]aformat=sample_rates=44100:channel_layouts=stereo,"
        f"atrim=0:{min(0.8, p2_src_dur):.2f},afade=t=out:st=0.12:d=0.55,"
        f"apad=whole_dur={p2_out_dur:.2f},volume=0.35[v_tail];"
    ]

    if bgm_file and os.path.exists(bgm_file):
        bgm_dur = _probe_audio_duration(bgm_file)
        # Seek directly into the drop/beat section of the phonk/soulful track!
        drop_ss = min(15.0, max(0.0, bgm_dur * 0.25))
        cmd2.extend(["-ss", f"{drop_ss:.2f}", "-stream_loop", "-1", "-i", bgm_file])
        fade_out_s = max(0.4, p2_out_dur - 0.85)
        a_chains2.append(
            f"[{next_i2}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:{p2_out_dur:.2f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.12,afade=t=out:st={fade_out_s:.2f}:d=0.80,volume=0.88[drop_bgm];"
        )
        a_labels2.append("[drop_bgm]")
        next_i2 += 1

    boom_sfx = sfx_file if (sfx_file and sfx_kind == "boom") else _generate_synth_boom(f"drop_boom_{index}.mp3")
    if boom_sfx and os.path.exists(boom_sfx):
        cmd2.extend(["-i", boom_sfx])
        a_chains2.append(
            f"[{next_i2}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:1.0,afade=t=out:st=0.60:d=0.35,volume=0.65[drop_sfx];"
        )
        a_labels2.append("[drop_sfx]")
        next_i2 += 1

    a_chains2.append(
        f"{''.join(a_labels2)}amix=inputs={len(a_labels2)}:duration=longest:dropout_transition=2:normalize=0,"
        f"atrim=0:{p2_out_dur:.2f},loudnorm=I=-14:TP=-1.5:LRA=11[a2]"
    )

    fc2 = v_chain2 + "".join(a_chains2)
    cmd2.extend([
        "-filter_complex", fc2, "-map", "[v2]", "-map", "[a2]",
        "-t", f"{p2_out_dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-ar", "44100", "-ac", "2", "-b:a", "192k",
        p2_file,
    ])
    subprocess.run(cmd2, check=True, timeout=140)

    # ==================== SEAMLESS CONCAT + TOP PROGRESS BAR ====================
    total_dur = p1_dur + p2_out_dur
    cmd_cat = [
        "ffmpeg", "-y", "-i", p1_file, "-i", p2_file,
        "-filter_complex",
        (
            f"[0:v][0:a][1:v][1:a]concat=n=2:v=1:a=1[vcat][acat];"
            f"color=c={spec['pbar']}:s=1080x7:r=30[pbar];"
            f"[vcat][pbar]overlay=x='-W+(W*min(t/{total_dur:.2f},1))':y=0:shortest=1,format=yuv420p[vout]"
        ),
        "-map", "[vout]", "-map", "[acat]",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-preset", "fast", "-crf", "18", "-threads", "0",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        output_file,
    ]
    subprocess.run(cmd_cat, check=True, timeout=140)


def _render_continuous_ig_reel(
    video_path, start, duration, peak_sec, in_w, in_h, focus_x, spec, subtype,
    font_name, words, caption_style, has_top_facecam, title_text, impact_stamp,
    emoji_png, bgm_file, sfx_file, sfx_kind, custom_ffmpeg, captions_on, output_file, index
):
    """
    Continuous IG Reel Renderer (Emotional Brotherhood, Mindset Statement, Letterbox Comedy,
    Red Ribbon Comedy, Esports Montage, Meme Pop, Clean Raw) with PERSISTENT Title/Ribbon!
    """
    dur_frames = max(30, int(duration * 30))
    pk = float(peak_sec)
    peak_bell = f"max(0,1-abs(on/30-{pk:.2f})/0.85)"
    shake_win = f"between(on/30,{pk:.2f},{pk+0.35:.2f})"

    if spec["shake"]:
        z_expr = f"1.01+0.09*max(0,1-on/12)+0.04*min(1,on/{dur_frames})+0.11*{peak_bell}"
        x_expr = f"clip(iw/2-(iw/zoom/2)+12*sin(on*3.1)*{shake_win},0,iw-iw/zoom)"
        y_expr = f"clip(ih/2-(ih/zoom/2)+12*cos(on*3.5)*{shake_win},0,ih-ih/zoom)"
    else:
        z_expr = f"1.01+0.06*max(0,1-on/14)+0.05*min(1,on/{dur_frames})+0.05*{peak_bell}"
        x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)"

    base_graph = _build_base_frame_chain(
        video_path, start, duration, in_w, in_h, focus_x, spec, z_expr, x_expr, y_expr
    )

    is_ig_minimal_cap = subtype not in ("gaming_esports_montage", "clean_minimal")
    ass_file = _generate_ass_file(
        f"ass_full_{index}.ass", font_name, spec, duration, title_text,
        words, start, caption_style, has_top_facecam, captions_on,
        is_ig_minimal_cap=is_ig_minimal_cap,
        stamp_text=(impact_stamp if spec["stamp_on_drop"] else ""),
        stamp_start=pk, stamp_dur=1.1,
    )

    vf = list(spec["base_cc"])
    if spec["flash"]:
        vf.append(f"eq=brightness=0.26:enable='between(t,{pk:.2f},{pk+0.10:.2f})'")
    if title_text and spec["hook_style"] == "red_ribbon":
        vf.append("drawbox=x=0:y=1150:w=iw:h=190:color=0x99111B@0.76:t=fill")
    if custom_ffmpeg and ";" not in custom_ffmpeg and "[" not in custom_ffmpeg:
        vf.append(custom_ffmpeg)
    if ass_file and os.path.exists(ass_file):
        vf.append(f"ass={ass_file}:fontsdir=.")

    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", video_path]
    next_in = 1

    # Add crisp Emoji PNG (persistent beside letterbox top title, OR pop on comedy punchline!)
    if emoji_png and os.path.exists(emoji_png):
        cmd.extend(["-loop", "1", "-i", emoji_png])
        em_idx = next_in
        next_in += 1
        if spec["letterbox"]:
            # Clean reaction emoji centered right beneath top letterbox caption!
            v_chain = (
                f"{base_graph}[base]{','.join(vf)}[v_cc];"
                f"[{em_idx}:v]format=rgba,scale=92:-1:flags=lanczos[em];"
                f"[v_cc][em]overlay=x=(W-w)/2:y=415:shortest=1[v_em];"
            )
        else:
            # Meme pop right at the comedy/action peak!
            v_chain = (
                f"{base_graph}[base]{','.join(vf)}[v_cc];"
                f"[{em_idx}:v]format=rgba,scale=150:-1:flags=lanczos[em];"
                f"[v_cc][em]overlay=x=(W-w)/2:y=780:enable='between(t,{pk:.2f},{min(duration-0.2, pk+1.6):.2f})':shortest=1[v_em];"
            )
        last_v = "[v_em]"
    else:
        v_chain = f"{base_graph}[base]{','.join(vf)}[v_cc];"
        last_v = "[v_cc]"

    v_chain += (
        f"color=c={spec['pbar']}:s=1080x7:r=30[pbar];"
        f"{last_v}[pbar]overlay=x='-W+(W*min(t/{duration:.2f},1))':y=0:shortest=1,format=yuv420p[vout];"
    )

    # Audio mix
    fade_out_s = max(0.5, duration - 1.1)
    bgm_vol = "0.20" if subtype in ("aura_mindset_statement", "gaming_esports_montage") else "0.14"

    a_labels = ["[voice]"]
    if bgm_file:
        a_chains = [
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,highpass=f=85,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.18,asplit=2[voice][v_sc];"
        ]
        cmd.extend(["-stream_loop", "-1", "-i", bgm_file])
        a_chains.append(
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:{duration:.2f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.6,afade=t=out:st={fade_out_s:.2f}:d=1.1,volume={bgm_vol}[bgm_pre];"
            f"[bgm_pre][v_sc]sidechaincompress=threshold=0.03:ratio=5:attack=25:release=320[bgm];"
        )
        a_labels.append("[bgm]")
        next_in += 1
    else:
        a_chains = [
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,highpass=f=85,"
            "acompressor=threshold=-18dB:ratio=3:attack=5:release=50,volume=1.18[voice];"
        ]

    if sfx_file and os.path.exists(sfx_file):
        cmd.extend(["-i", sfx_file])
        sfx_ms = int(pk * 1000)
        a_chains.append(
            f"[{next_in}:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            f"atrim=0:1.4,afade=t=out:st=1.0:d=0.4,adelay={sfx_ms}|{sfx_ms},volume=0.45[sfx];"
        )
        a_labels.append("[sfx]")
        next_in += 1

    if len(a_labels) == 1:
        a_chains.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    else:
        a_chains.append(
            f"{''.join(a_labels)}amix=inputs={len(a_labels)}:duration=first:dropout_transition=2:normalize=0,"
            f"loudnorm=I=-14:TP=-1.5:LRA=11[aout]"
        )

    fc = v_chain + "".join(a_chains)
    cmd.extend([
        "-filter_complex", fc, "-map", "[vout]", "-map", "[aout]",
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-preset", "fast", "-crf", "18", "-threads", "0",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        output_file,
    ])
    subprocess.run(cmd, check=True, timeout=220)


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
    end = float(clip_data.get("end", start + 19))
    raw_duration = max(9.0, min(27.0, end - start))
    duration = _snap_clean_duration(start, raw_duration, max_file_dur, word_timestamps)

    orig_start = int(float(clip_data.get("orig_start", start)))
    edit_type = re.sub(r"[^a-zA-Z0-9_]", "", str(clip_data.get("edit_type", "vlog"))).lower() or "vlog"
    subtype = str(clip_data.get("edit_subtype", "")).strip().lower()
    if subtype not in SUBTYPE_SPECS:
        subtype = "clean_minimal" if edit_type == "clean" else "roast_red_ribbon_drop"
    spec = SUBTYPE_SPECS[subtype]

    caption_style = str(clip_data.get("caption_style", "hormozi_pop")).strip().lower()
    focus_x = str(clip_data.get("focus_x", "center")).lower()
    title_text = _clean_text(clip_data.get("title_text", "")).upper() if banner_enabled else ""
    impact_stamp = _clean_text(clip_data.get("impact_stamp", "")).upper() if spec["stamp_on_drop"] else ""

    ai_peak = clip_data.get("peak_sec", None)
    is_live = bool(clip_data.get("is_live", False))
    peak_sec, has_existing_bgm = _analyze_audio_and_sync_peak(
        video_path, start, duration, ai_peak_sec=ai_peak, is_live=is_live
    )

    has_top_facecam = (in_h > in_w) and _detect_top_facecam_vertical(video_path, start, duration)

    mm, ss = divmod(max(0, orig_start), 60)
    output_file = f"MAG73_{edit_type.upper()}_{mm:02d}m{ss:02d}s_Clip_{index + 1}.mp4"

    # Fetch BGM & SFX (for two_part_drop, ALWAYS fetch the drop music so the beat switch hits hard!)
    bgm_file = None
    if bgm_enabled and edit_type != "clean":
        if spec["mode"] == "two_part_drop" or not has_existing_bgm:
            bgm_file = _fetch_audio(clip_data.get("bgm_query", ""), f"bgm_{index}_{subtype}")

    sfx_kind = str(clip_data.get("sfx_kind", "none")).lower()
    sfx_file = None
    if sfx_enabled and edit_type != "clean" and sfx_kind != "none":
        sfx_file = _fetch_audio(clip_data.get("sfx_query", ""), f"sfx_{index}_{sfx_kind}")

    emoji_png = _download_emoji_png(clip_data.get("overlay_emoji", "none")) if edit_type != "clean" else None
    captions_on = (caption_lang != "off")

    print(
        f"[MAG73 IG Engine] Rendering {output_file} | Subtype={subtype} ({spec['mode']}) | "
        f"HookStyle={spec['hook_style']} | DropCC={spec['drop_cc']} | Emoji={clip_data.get('overlay_emoji')} | Peak={peak_sec:.2f}s"
    )

    if spec["mode"] == "two_part_drop" and duration >= 8.5:
        try:
            _render_two_part_drop_reel(
                video_path, start, duration, peak_sec, in_w, in_h, focus_x, spec, subtype,
                font_name, word_timestamps, caption_style, has_top_facecam, title_text, impact_stamp,
                emoji_png, bgm_file, sfx_file, sfx_kind, custom_ffmpeg, captions_on, output_file, index
            )
        except Exception as e:
            print(f"[MAG73 IG Engine] Two-part fallback to continuous ({e})")
            _render_continuous_ig_reel(
                video_path, start, duration, peak_sec, in_w, in_h, focus_x, spec, subtype,
                font_name, word_timestamps, caption_style, has_top_facecam, title_text, impact_stamp,
                emoji_png, bgm_file, sfx_file, sfx_kind, custom_ffmpeg, captions_on, output_file, index
            )
    else:
        _render_continuous_ig_reel(
            video_path, start, duration, peak_sec, in_w, in_h, focus_x, spec, subtype,
            font_name, word_timestamps, caption_style, has_top_facecam, title_text, impact_stamp,
            emoji_png, bgm_file, sfx_file, sfx_kind, custom_ffmpeg, captions_on, output_file, index
        )

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
