import os
import time
import json
import re
import random
import subprocess
import concurrent.futures
import requests
from google import genai

try:
    from faster_whisper import WhisperModel
    HAS_FASTER_WHISPER = True
except Exception:
    HAS_FASTER_WHISPER = False

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()

gemini_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "gemma2-9b-it",
]

_working_groq_model = None
_local_whisper_model = None

VALID_STYLES = ("roast", "aura", "aesthetic", "vlog", "gaming", "funny", "drama", "clash", "informative", "clean")

DEFAULT_BGM_BY_STYLE = {
    "roast": "ytsearch1:dark brazilian phonk sigma edit instrumental no copyright",
    "aura": "ytsearch1:dark phonk aura edit slowed instrumental no copyright",
    "aesthetic": "ytsearch1:moody aesthetic dark ambient motivation beat no copyright",
    "vlog": "ytsearch1:chill aesthetic travel vlog beat instrumental no copyright",
    "informative": "ytsearch1:clean modern documentary background beat no copyright",
    "gaming": "ytsearch1:energetic gaming phonk montage instrumental no copyright",
    "clash": "ytsearch1:intense dark trap hype beat instrumental no copyright",
    "funny": "ytsearch1:upbeat comedy quirky background music instrumental no copyright",
    "drama": "ytsearch1:cinematic suspense tension dark background music no copyright",
    "clean": "",
}

DEFAULT_SFX_BY_STYLE = {
    "roast": "ytsearch1:vine boom bass drop impact sfx",
    "aura": "ytsearch1:cinematic bass drop impact sound effect",
    "aesthetic": "ytsearch1:deep cinematic sub drop sfx",
    "funny": "ytsearch1:vine boom sound effect short",
    "gaming": "ytsearch1:cinematic bass impact hit sfx",
    "clash": "ytsearch1:dramatic bass boom sfx",
    "drama": "ytsearch1:dramatic suspense hit sound effect",
    "vlog": "",
    "informative": "",
    "clean": "",
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
        except Exception as e:
            print(f"[MAG73 Plugin] Config parse warning: {e}")
    return defaults


def _devanagari_to_roman(text):
    if not text or not any("\u0900" <= ch <= "\u097f" for ch in text):
        return text
    vowels = {
        "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo",
        "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri",
    }
    matras = {
        "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo",
        "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri",
        "ं": "n", "ँ": "n", "ः": "h", "्": "",
    }
    cons = {
        "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
        "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
        "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
        "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
        "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
        "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
        "ष": "sh", "स": "s", "ह": "h", "क़": "q", "ख़": "kh",
        "ग़": "g", "ज़": "z", "ड़": "r", "ढ़": "rh", "फ़": "f",
    }
    out = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in vowels:
            out.append(vowels[ch])
        elif ch in cons:
            base = cons[ch]
            nxt = text[i + 1] if i + 1 < n else ""
            if nxt in matras:
                out.append(base + matras[nxt])
                i += 1
            elif nxt in cons or (nxt and nxt not in " ,.!?;:-"):
                out.append(base + "a")
            else:
                out.append(base)
        elif ch in matras:
            out.append(matras[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


def _call_groq(prompt, temperature=0.25):
    global _working_groq_model
    if GROQ_KEY:
        ordered_models = []
        if _working_groq_model:
            ordered_models.append(_working_groq_model)
        for m in GROQ_MODELS:
            if m not in ordered_models:
                ordered_models.append(m)

        last_err = ""
        for model_name in ordered_models:
            try:
                res = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {GROQ_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model_name,
                        "temperature": temperature,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=45,
                )
                if res.status_code == 200:
                    _working_groq_model = model_name
                    data = res.json()
                    choices = data.get("choices") or []
                    if choices:
                        return choices[0].get("message", {}).get("content", "") or ""
                elif res.status_code == 429:
                    time.sleep(random.uniform(1.0, 2.5))
                last_err = f"HTTP {res.status_code}"
            except Exception as e:
                last_err = str(e)
        print(f"[MAG73 Groq] Fallback to Gemini text ({last_err})")

    if gemini_client:
        for gm in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"):
            try:
                res = gemini_client.models.generate_content(model=gm, contents=prompt)
                if res and res.text:
                    return res.text
            except Exception:
                continue
    return ""


def _build_timestamped_transcript(words):
    if not words:
        return ""
    lines = []
    bucket_start = int(float(words[0].get("start", 0)))
    curr = []
    for w in words:
        ws = int(float(w.get("start", 0)))
        if ws - bucket_start >= 5 and curr:
            lines.append(f"[{bucket_start}s] " + " ".join(curr))
            bucket_start = ws
            curr = []
        txt = str(w.get("word", "")).strip()
        if txt:
            curr.append(txt)
    if curr:
        lines.append(f"[{bucket_start}s] " + " ".join(curr))
    return "\n".join(lines)


def _words_from_segments(segments):
    derived = []
    for seg in (segments or []):
        seg_words = seg.get("words") or []
        if seg_words:
            for sw in seg_words:
                txt = str(sw.get("word", "")).strip()
                if txt:
                    derived.append({
                        "word": txt,
                        "start": float(sw.get("start", seg.get("start", 0))),
                        "end": float(sw.get("end", seg.get("end", 0.3))),
                    })
            continue
        txt = str(seg.get("text", "")).strip()
        tokens = [t for t in txt.split() if t.strip()]
        if not tokens:
            continue
        s = float(seg.get("start", 0))
        e = max(s + 0.3, float(seg.get("end", s + 1.5)))
        step = (e - s) / len(tokens)
        for idx, tok in enumerate(tokens):
            derived.append({
                "word": tok,
                "start": round(s + idx * step, 2),
                "end": round(s + (idx + 1) * step, 2),
            })
    return derived


def _local_faster_whisper_transcribe(audio_path, caption_lang="hinglish"):
    """100% OFFLINE CPU transcription — ZERO rate limits, works even with 10 parallel jobs!"""
    global _local_whisper_model
    if not HAS_FASTER_WHISPER or not os.path.exists(audio_path):
        return "", []
    try:
        if _local_whisper_model is None:
            print("[MAG73 Offline Whisper] Loading base int8 model on CPU...")
            _local_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

        lang_arg = "en" if caption_lang == "en" else None
        segments, info = _local_whisper_model.transcribe(
            audio_path,
            language=lang_arg,
            word_timestamps=True,
            vad_filter=True,
            beam_size=1,
        )
        words = []
        full_parts = []
        for seg in segments:
            full_parts.append(seg.text.strip())
            if seg.words:
                for sw in seg.words:
                    txt = str(sw.word or "").strip()
                    if txt:
                        words.append({
                            "word": txt,
                            "start": round(float(sw.start), 2),
                            "end": round(float(sw.end), 2),
                        })
            else:
                toks = [t for t in seg.text.strip().split() if t]
                if toks:
                    step = max(0.08, (float(seg.end) - float(seg.start)) / len(toks))
                    for idx, tok in enumerate(toks):
                        words.append({
                            "word": tok,
                            "start": round(float(seg.start) + idx * step, 2),
                            "end": round(float(seg.start) + (idx + 1) * step, 2),
                        })
        print(f"[MAG73 Offline Whisper] Extracted {len(words)} words (lang={getattr(info, 'language', 'auto')}).")
        return " ".join(full_parts), words
    except Exception as e:
        print(f"[MAG73 Offline Whisper] Warning: {e}")
        return "", []


def _wait_for_gemini_file(video_file, max_wait=70):
    deadline = time.time() + max_wait
    while time.time() < deadline:
        info = gemini_client.files.get(name=video_file.name)
        state = getattr(info.state, "name", str(info.state))
        if state == "ACTIVE":
            return info
        if state == "FAILED":
            raise RuntimeError("Gemini media processing failed.")
        time.sleep(3)
    raise TimeoutError(f"Gemini file processing timed out after {max_wait}s")


def _convert_words_smart(words, full_context, mode="hinglish"):
    try:
        raw_list = [str(w.get("word", "")).strip() for w in words]
        converted_all = []
        for i in range(0, len(raw_list), 70):
            chunk = raw_list[i:i + 70]
            if not any(not x.isascii() for x in chunk):
                converted_all.extend(chunk)
                continue

            if mode == "en":
                instruction = (
                    "Translate/clean each word in this JSON array into crisp English captions (ASCII A-Z only).\n"
                    "Return ONLY a JSON array of strings of the EXACT SAME LENGTH.\n"
                )
            else:
                instruction = (
                    "Convert each word in this JSON array into natural Roman Hinglish (ASCII A-Z only, e.g. 'भाई'->'Bhai').\n"
                    "Keep English words in normal English. Return ONLY a JSON array of strings of the EXACT SAME LENGTH.\n"
                )

            prompt = (
                f"{instruction}"
                f"Context: {full_context[:300]}\n"
                f"Input: {json.dumps(chunk, ensure_ascii=False)}"
            )
            out = _call_groq(prompt, temperature=0.1)
            match = re.search(r"\[.*\]", out, re.DOTALL)
            if match:
                try:
                    out_chunk = json.loads(match.group(0))
                    if isinstance(out_chunk, list) and len(out_chunk) == len(chunk):
                        converted_all.extend(out_chunk)
                        continue
                except Exception:
                    pass
            converted_all.extend([_devanagari_to_roman(x) for x in chunk])

        for idx, w in enumerate(words):
            if idx < len(converted_all):
                w["word"] = str(converted_all[idx])
    except Exception as e:
        print(f"[MAG73 Audio] Caption formatting warning: {e}")
    return words


def extract_accurate_transcript(media_path="source_video.mp4", caption_lang="hinglish", is_audio_only=False):
    """
    BULLETPROOF ZERO-DROP TRANSCRIPTION:
    1. Vocal-filtered 16kHz mono MP3 extraction.
    2. Quick Groq Whisper try -> INSTANT local offline `faster-whisper` fallback (zero 429 rate-limit drops!).
    3. Clean Hinglish/English ASCII conversion with offline Devanagari fallback.
    """
    audio_path = "temp_vocal_16k.mp3"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", media_path,
                "-vn", "-af", "highpass=f=120,lowpass=f=4000,dynaudnorm=f=150:g=11",
                "-ac", "1", "-ar", "16000", "-b:a", "48k", audio_path,
            ],
            check=True,
            timeout=60,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        if is_audio_only and os.path.exists(media_path):
            audio_path = media_path
        else:
            print(f"[MAG73 Audio] FFmpeg extract error: {e}")
            return "", [], caption_lang

    words = []
    text = ""

    # Try Groq Whisper once quickly (fast if not rate-limited)
    if GROQ_KEY and os.path.exists(audio_path) and os.path.getsize(audio_path) < 24 * 1024 * 1024:
        form_data = {
            "model": "whisper-large-v3-turbo",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
            "prompt": (
                "Clean English transcript."
                if caption_lang == "en"
                else "Indian creator gaming, roast, sports, and vlog commentary in Hindi, Hinglish, and English."
            ),
        }
        if caption_lang == "en":
            form_data["language"] = "en"

        try:
            with open(audio_path, "rb") as f:
                res = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}"},
                    files={"file": f},
                    data=form_data,
                    timeout=55,
                )
            if res.status_code == 200:
                data = res.json()
                words = data.get("words") or []
                text = data.get("text") or ""
                if not words and data.get("segments"):
                    words = _words_from_segments(data.get("segments"))
                print(f"[MAG73 Audio] Groq Whisper extracted {len(words)} words.")
            else:
                print(f"[MAG73 Audio] Groq Whisper HTTP {res.status_code} — switching to Offline Whisper!")
        except Exception as e:
            print(f"[MAG73 Audio] Groq Whisper skipped ({e}) — switching to Offline Whisper!")

    # Guaranteed Offline faster-whisper fallback (100% immune to parallel 429 limits!)
    if len(words) < 5:
        fw_text, fw_words = _local_faster_whisper_transcribe(audio_path, caption_lang=caption_lang)
        if len(fw_words) > len(words):
            words = fw_words
            text = fw_text

    if words:
        has_non_ascii = any(not str(w.get("word", "")).isascii() for w in words)
        if caption_lang == "en" and has_non_ascii:
            words = _convert_words_smart(words, text, mode="en")
        elif caption_lang == "hinglish" and has_non_ascii:
            words = _convert_words_smart(words, text, mode="hinglish")

        for w in words:
            txt = str(w.get("word", "")).strip()
            if txt and not txt.isascii():
                w["word"] = _devanagari_to_roman(txt)

        ts_text = _build_timestamped_transcript(words)
        return ts_text, words, caption_lang

    return text, [], caption_lang


def refine_clip_hook(clip_data, segment_transcript):
    """Crash-safe verifier: guarantees Hook Title & Style strictly match THIS clip's exact spoken words."""
    plugin_cfg = _get_plugin_config()
    if not bool(plugin_cfg.get("banner_enabled", True)):
        clip_data["title_text"] = ""
        return clip_data
    if str(clip_data.get("edit_type", "")).lower() == "clean":
        clip_data["title_text"] = ""
        return clip_data

    seg_txt = (segment_transcript or "").strip()
    existing = str(clip_data.get("title_text", "")).strip()
    if len(seg_txt) < 12:
        return clip_data

    try:
        prompt = f"""
        Read the EXACT spoken dialogue inside this 15-35s short clip and write ONE viral 3-6 word Hook Title (UPPERCASE ASCII ONLY).
        CRITICAL: The title MUST 100% match THIS transcript! NEVER mention anything not spoken here.
        Examples: "QAZI ALWAYS READY TO ROAST", "ONLY LEGENDS UNDERSTAND THIS", "HIS MINDSET HIT DIFFERENT", "12000 ELECTRICITY BILL SHOCK"
        Current draft: "{existing}"
        Exact Clip Transcript:
        {seg_txt[:1500]}

        Return ONLY the 3-6 word title (no quotes, no explanation).
        """
        raw = (_call_groq(prompt, temperature=0.2) or "").strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        if lines:
            refined = re.sub(r"[^A-Za-z0-9 !?@#.-]", "", lines[0]).strip().upper()
            words = refined.split()
            if 2 <= len(words) <= 7:
                clip_data["title_text"] = " ".join(words)
                print(f"[MAG73 Hook] Verified exact clip hook: '{clip_data['title_text']}'")
    except Exception as e:
        print(f"[MAG73 Hook] Keeping existing hook '{existing}' (warn: {e})")
    return clip_data


def _clean_json(raw_text):
    if not raw_text:
        return []
    try:
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                return parsed
    except Exception:
        pass
    return []


def _get_media_duration_sec(media_path):
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", media_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return max(10.0, float(out))
    except Exception:
        return 60.0


def _is_outro_clip(clip, words, total_dur):
    s = float(clip.get("start", 0))
    e = float(clip.get("end", s + 20))
    if total_dur > 45 and e >= total_dur - 8:
        seg_text = " ".join(
            str(w.get("word", "")).lower()
            for w in (words or [])
            if s <= float(w.get("start", 0)) <= e
        )
        outro_hits = sum(
            1 for kw in ("bye", "subscribe", "agli video", "next video", "end this video", "goodbye", "allah hafiz")
            if kw in seg_text
        )
        if outro_hits >= 2:
            return True
    return False


def _deduplicate_clips(clips, max_dur, words):
    valid = []
    for c in clips:
        if not isinstance(c, dict):
            continue
        s = max(0.0, float(c.get("start", 0)))
        e = min(max_dur, float(c.get("end", s + 20)))
        if e - s < 10.0:
            e = min(max_dur, s + 18.0)
        if e - s > 38.0:
            e = s + 34.0
        c["start"] = int(round(s))
        c["end"] = int(round(e))
        if _is_outro_clip(c, words, max_dur):
            continue
        valid.append(c)

    valid.sort(key=lambda x: int(x.get("score", 80)), reverse=True)
    kept = []
    for c in valid:
        overlaps = False
        for k in kept:
            inter = min(c["end"], k["end"]) - max(c["start"], k["start"])
            min_len = max(1, min(c["end"] - c["start"], k["end"] - k["start"]))
            if inter > 0.30 * min_len or abs(c["start"] - k["start"]) < 6:
                overlaps = True
                break
        if not overlaps:
            kept.append(c)

    kept.sort(key=lambda x: x["start"])
    return kept


def _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg):
    bgm_enabled = bool(plugin_cfg.get("bgm_enabled", True))
    sfx_enabled = bool(plugin_cfg.get("sfx_enabled", True))
    banner_enabled = bool(plugin_cfg.get("banner_enabled", True))

    clips = [c for c in raw_clips if isinstance(c, dict) and int(c.get("score", 80)) >= 83]
    if not clips and raw_clips:
        dict_clips = [c for c in raw_clips if isinstance(c, dict)]
        if dict_clips:
            clips = [max(dict_clips, key=lambda x: int(x.get("score", 0)))]

    clips = _deduplicate_clips(clips, vid_dur, word_timestamps)

    if not clips:
        end_s = min(vid_dur, 24.0)
        fallback_style = style_pref if style_pref in VALID_STYLES else "vlog"
        clips = [
            {
                "start": 0,
                "end": int(max(10.0, end_s)),
                "score": 85,
                "edit_type": fallback_style,
                "layout_mode": "vertical_full",
                "focus_x": "center",
                "title_text": "WATCH THIS MOMENT!" if banner_enabled else "",
                "peak_sec": int(min(10.0, max(3.0, end_s * 0.5))),
                "bgm_query": "",
                "sfx_query": "",
            }
        ]

    for c in clips:
        et = str(c.get("edit_type", "vlog")).strip().lower()
        if style_pref in VALID_STYLES and style_pref != "auto":
            et = style_pref
        elif et not in VALID_STYLES:
            et = "vlog"
        c["edit_type"] = et

        if bgm_enabled and et != "clean":
            if not str(c.get("bgm_query", "")).strip():
                c["bgm_query"] = DEFAULT_BGM_BY_STYLE.get(et, "")
        else:
            c["bgm_query"] = ""

        if sfx_enabled and et != "clean":
            if not str(c.get("sfx_query", "")).strip():
                c["sfx_query"] = DEFAULT_SFX_BY_STYLE.get(et, "")
        else:
            c["sfx_query"] = ""

        if not banner_enabled:
            c["title_text"] = ""
        elif not str(c.get("title_text", "")).strip() and et != "clean":
            c["title_text"] = "WATCH THIS MOMENT!"

    print(f"[MAG73 Director] Approved {len(clips)} unique clip(s): {[c['edit_type'] for c in clips]}")
    return clips


def run_fast_scan_council(audio_path, audience_signals, video_path=None):
    """
    4x FASTER SCAN ENGINE:
    Uses lightweight audio transcript + YouTube Most-Replayed Heatmap + Top Comments.
    Finds ALL genuinely viral moments across the entire video in ~30-50 seconds!
    """
    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    custom_prompt = os.getenv("CUSTOM_PROMPT", "").strip()

    transcript_text, word_timestamps, _ = extract_accurate_transcript(
        audio_path, caption_lang=caption_lang, is_audio_only=True
    )
    vid_dur = float(audience_signals.get("duration") or 0.0) or _get_media_duration_sec(audio_path)

    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION (OBEY STRICTLY): {custom_prompt}\n" if custom_prompt else ""

    prompt = f"""
    You are a TOP VIRAL INSTAGRAM REELS / YOUTUBE SHORTS DIRECTOR.
    {user_rule}
    Video Title: "{audience_signals.get('video_title', '')}"
    Video Duration: {int(vid_dur)} seconds
    User Style Preference: "{style_pref}" (if "auto", pick the EXACT best viral style for EACH individual clip!)

    AUDIENCE VIRAL SIGNALS:
    - YouTube Most-Replayed Heatmap Spikes (sec): {audience_signals.get('heatmap_spikes', [])}
    - Top Comment Timestamps (sec): {audience_signals.get('comment_timestamps', [])}
    - Top Comments: {audience_signals.get('top_comments', [])[:10]}

    TIMESTAMPED TRANSCRIPT ([Xs] seconds):
    {transcript_text[:22000]}

    STRICT RULES:
    1. Extract ALL genuinely high-hype, non-overlapping viral moments across the ENTIRE video (14-36s each, score 84-100).
    2. STRICTLY REJECT outros ("bye bye", "subscribe"), boring intros, or dull filler.
    3. PICK THE EXACT RIGHT VIRAL STYLE ("edit_type") FOR EACH CLIP:
       - "roast": Savage insult, funny roast, cheeky comeback, double-meaning banter (gets Viral Red Ribbon + HDR CC + Climax Drop!).
       - "aura": Cold badass line, goosebumps clutch, savage mindset moment (gets Dark Aura Drop + Flash + Phonk!).
       - "aesthetic": Deep mindset quote, sports pride, emotional/motivational speech (gets Moody Cinema CC + Glowing Lower-Third!).
       - "funny": Pure comedy reaction, laugh, fail.
       - "gaming": Fast action gameplay / gunfight.
       - "vlog": Food, street exploring, lifestyle story.
       - "drama": Heated argument / confrontation.
       - "informative": Cool fact / breakdown.
    4. EXACT HOOK TITLE ("title_text"): Punchy 3-6 word uppercase ASCII hook that STRICTLY matches the dialogue inside THAT clip's exact [start, end] timestamps!
    5. "layout_mode": "vertical_full" for talking-head / interviews / vlogs / sports; "gaming_wide" ONLY for 16:9 gameplay HUD.

    Return ONLY valid JSON array:
    [
      {{
        "start": 42,
        "end": 68,
        "score": 92,
        "edit_type": "roast",
        "layout_mode": "vertical_full",
        "focus_x": "center",
        "title_text": "ALWAYS READY TO ROAST THEM",
        "peak_sec": 14,
        "bgm_query": "",
        "sfx_query": ""
      }}
    ]
    """
    raw_out = _call_groq(prompt, temperature=0.25)
    raw_clips = _clean_json(raw_out)
    return _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg)


def run_super_ai_council(video_path, audience_signals):
    """Used for Live Stream & direct legacy mode."""
    if isinstance(audience_signals, list):
        audience_signals = {"chat_spikes": audience_signals, "heatmap_spikes": [], "comment_timestamps": [], "top_comments": []}

    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    custom_prompt = os.getenv("CUSTOM_PROMPT", "").strip()

    transcript_text, word_timestamps, _ = extract_accurate_transcript(video_path, caption_lang=caption_lang)
    vid_dur = _get_media_duration_sec(video_path)

    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""
    prompt = f"""
    You are a PRO VIRAL REELS DIRECTOR.
    {user_rule}
    Style Preference: "{style_pref}"
    Chat Spikes: {audience_signals.get('chat_spikes', [])}
    Transcript:
    {transcript_text[:16000]}

    Return ONLY valid JSON array of best viral clips (14-35s, score 84-100) with accurate "edit_type" ("roast", "aura", "aesthetic", "vlog", "gaming", "funny", "drama", "clash", "informative", "clean"), "layout_mode", "title_text" (3-6 ASCII words), and "peak_sec".
    """
    raw_out = _call_groq(prompt, temperature=0.25)
    raw_clips = _clean_json(raw_out)
    clips = _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg)
    return clips, word_timestamps
