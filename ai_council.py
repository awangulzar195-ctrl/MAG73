import os
import time
import json
import re
import random
import subprocess
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
CAPTION_STYLES = ("hormozi_pop", "boxed_pill", "neon_glow", "word_slam", "editorial_italic")

BGM_POOLS = {
    "aura": [
        "ytsearch1:dark phonk slowed reverb instrumental no copyright",
        "ytsearch1:sigma cold edit dark bass instrumental royalty free",
        "ytsearch1:aggressive funk montagen slowed instrumental no copyright",
        "ytsearch1:cinematic dark trap beat edit instrumental no copyright",
        "ytsearch1:hardwave cyberpunk dark synth edit beat no copyright",
        "ytsearch1:menacing drill beat instrumental sports edit no copyright",
    ],
    "roast": [
        "ytsearch1:savage roast hip hop trap beat instrumental no copyright",
        "ytsearch1:sigma roast dark funk beat instrumental royalty free",
        "ytsearch1:gangster comedy trap instrumental no copyright",
        "ytsearch1:hard bass boom bap roast beat no copyright",
        "ytsearch1:dark phonk meme edit instrumental no copyright",
        "ytsearch1:swagger hip hop beat instrumental no copyright",
    ],
    "aesthetic": [
        "ytsearch1:moody dark ambient motivation instrumental no copyright",
        "ytsearch1:slowed reverb emotional cinematic piano beat no copyright",
        "ytsearch1:dreamy synthwave aesthetic edit instrumental no copyright",
        "ytsearch1:deep atmospheric epic sports edit music no copyright",
        "ytsearch1:nostalgic lofi cinema beat instrumental no copyright",
        "ytsearch1:emotional orchestral trap beat instrumental no copyright",
    ],
    "gaming": [
        "ytsearch1:energetic gaming montage phonk beat no copyright",
        "ytsearch1:fast hype electronic trap gaming beat no copyright",
        "ytsearch1:esports clutch montage dubstep instrumental no copyright",
        "ytsearch1:brazilian funk gaming edit instrumental no copyright",
        "ytsearch1:adrenaline drum and bass gaming beat no copyright",
        "ytsearch1:hard trap montage beat instrumental no copyright",
    ],
    "clash": [
        "ytsearch1:intense dark trap confrontation beat no copyright",
        "ytsearch1:aggressive drill instrumental hype no copyright",
        "ytsearch1:epic faceoff suspense beat instrumental no copyright",
        "ytsearch1:heavy bass tension edit music no copyright",
    ],
    "funny": [
        "ytsearch1:upbeat quirky comedy background beat no copyright",
        "ytsearch1:playful pizzicato meme background music no copyright",
        "ytsearch1:bouncy hip hop funny vlog beat no copyright",
        "ytsearch1:goofy jazz comedy instrumental no copyright",
    ],
    "vlog": [
        "ytsearch1:chill aesthetic travel vlog lofi beat no copyright",
        "ytsearch1:modern lifestyle vlog groove instrumental no copyright",
        "ytsearch1:warm acoustic chill hip hop vlog beat no copyright",
        "ytsearch1:smooth upbeat summer vlog music no copyright",
    ],
    "drama": [
        "ytsearch1:cinematic suspense tension dark underscore no copyright",
        "ytsearch1:dramatic pulse thriller background music no copyright",
        "ytsearch1:intense emotional strings tension beat no copyright",
        "ytsearch1:dark reality tv drama background music no copyright",
    ],
    "informative": [
        "ytsearch1:clean modern documentary tech beat no copyright",
        "ytsearch1:minimal smart explainer background music no copyright",
        "ytsearch1:sleek corporate lo-fi documentary beat no copyright",
        "ytsearch1:curious investigative podcast background music no copyright",
    ],
    "clean": [""],
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

FALLBACK_STAMPS = {
    "aura": ["UNPLAYABLE", "COLD", "PURE CLASS", "LETHAL", "INSANE"],
    "roast": ["ROASTED", "COOKED", "VIOLATION", "SAVAGE", "NO MERCY"],
    "gaming": ["CLUTCH", "CRACKED", "CLEAN", "INSANE"],
    "clash": ["COOKED", "HEATED", "NO WAY", "SAVAGE"],
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


def _pick_unique_bgm_query(edit_type, seed):
    pool = BGM_POOLS.get(edit_type) or BGM_POOLS["vlog"]
    return pool[abs(int(seed)) % len(pool)]


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


def _build_timestamped_transcript(words, bucket_sec=3):
    if not words:
        return ""
    lines = []
    bucket_start = round(float(words[0].get("start", 0)), 1)
    curr = []
    for w in words:
        ws = round(float(w.get("start", 0)), 1)
        if ws - bucket_start >= bucket_sec and curr:
            lines.append(f"[{bucket_start:.1f}s] " + " ".join(curr))
            bucket_start = ws
            curr = []
        txt = str(w.get("word", "")).strip()
        if txt:
            curr.append(txt)
    if curr:
        lines.append(f"[{bucket_start:.1f}s] " + " ".join(curr))
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
    """Offline `small` int8 Whisper with NO instructional prompt so zero words are ever hallucinated."""
    global _local_whisper_model
    if not HAS_FASTER_WHISPER or not os.path.exists(audio_path):
        return "", []
    try:
        if _local_whisper_model is None:
            print("[MAG73 Offline Whisper] Loading small int8 model on CPU...")
            try:
                _local_whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
            except Exception:
                _local_whisper_model = WhisperModel("base", device="cpu", compute_type="int8")

        lang_arg = "en" if caption_lang == "en" else None
        segments, info = _local_whisper_model.transcribe(
            audio_path,
            language=lang_arg,
            word_timestamps=True,
            vad_filter=True,
            condition_on_previous_text=False,
            beam_size=2,
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


def _proofread_and_format_words(words, full_context, mode="hinglish", context_hint=""):
    if not words:
        return words
    try:
        raw_list = [str(w.get("word", "")).strip() for w in words]
        fixed_all = []
        for i in range(0, len(raw_list), 65):
            chunk = raw_list[i:i + 65]
            lang_rule = (
                "Fix obvious ASR spelling errors into clean English (ASCII A-Z)."
                if mode == "en"
                else "Fix obvious ASR spelling errors AND convert any Hindi script into clean Roman Hinglish (ASCII A-Z). Keep English words in English."
            )
            prompt = f"""
            You are a caption proofreader. {lang_rule}
            Video Title Context: "{context_hint}"
            Fix misheard proper names or sports/gaming terms using the title context. Do NOT invent new words.
            CRITICAL: Return ONLY a valid JSON array of strings of the EXACT SAME LENGTH ({len(chunk)} items).
            Sentence Context: {full_context[:320]}
            Input Array: {json.dumps(chunk, ensure_ascii=False)}
            """
            out = _call_groq(prompt, temperature=0.1)
            match = re.search(r"\[.*\]", out, re.DOTALL)
            if match:
                try:
                    out_chunk = json.loads(match.group(0))
                    if isinstance(out_chunk, list) and len(out_chunk) == len(chunk):
                        fixed_all.extend([_devanagari_to_roman(str(x)) for x in out_chunk])
                        continue
                except Exception:
                    pass
            fixed_all.extend([_devanagari_to_roman(x) for x in chunk])

        for idx, w in enumerate(words):
            if idx < len(fixed_all):
                w["word"] = str(fixed_all[idx])
        print(f"[MAG73 Captions] Proofread {len(words)} words cleanly.")
    except Exception as e:
        print(f"[MAG73 Captions] Proofread warning: {e}")
    return words


def extract_accurate_transcript(media_path="source_video.mp4", caption_lang="hinglish", is_audio_only=False, context_hint=""):
    """Clean Whisper extraction with ZERO instructional prompt leakage."""
    audio_path = "temp_vocal_16k.mp3"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", media_path,
                "-vn", "-af", "highpass=f=110,lowpass=f=4200,dynaudnorm=f=150:g=11",
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

    if GROQ_KEY and os.path.exists(audio_path) and os.path.getsize(audio_path) < 24 * 1024 * 1024:
        form_data = {
            "model": "whisper-large-v3-turbo",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
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
                print(f"[MAG73 Audio] Groq Whisper HTTP {res.status_code} — using Offline Whisper small!")
        except Exception as e:
            print(f"[MAG73 Audio] Groq Whisper skipped ({e}) — using Offline Whisper small!")

    if len(words) < 5:
        fw_text, fw_words = _local_faster_whisper_transcribe(audio_path, caption_lang=caption_lang)
        if len(fw_words) > len(words):
            words = fw_words
            text = fw_text

    if words:
        if len(words) <= 220:
            words = _proofread_and_format_words(words, text, mode=caption_lang, context_hint=context_hint)
        else:
            for w in words:
                txt = str(w.get("word", "")).strip()
                if txt and not txt.isascii():
                    w["word"] = _devanagari_to_roman(txt)

        ts_text = _build_timestamped_transcript(words, bucket_sec=3 if len(words) <= 220 else 5)
        return ts_text, words, caption_lang

    return text, [], caption_lang


def refine_clip_metadata(clip_data, segment_transcript, word_timestamps):
    plugin_cfg = _get_plugin_config()
    banner_on = bool(plugin_cfg.get("banner_enabled", True))
    edit_type = str(clip_data.get("edit_type", "vlog")).lower()
    dur = max(10.0, float(clip_data.get("end", 20.0)) - float(clip_data.get("start", 0.0)))
    seed = int(clip_data.get("orig_start", 0)) + int(clip_data.get("clip_index", 0)) * 7

    if not banner_on or edit_type == "clean":
        clip_data["title_text"] = ""

    seg_txt = (segment_transcript or "").strip()
    if len(seg_txt) >= 12:
        try:
            prompt = f"""
            Analyze this EXACT 0.0s-to-{dur:.1f}s clip transcript and return ONLY a JSON object:
            - "title_text": Punchy 3-5 word UPPERCASE ASCII hook strictly about THIS clip.
            - "peak_sec": Exact float second between {max(3.0, dur*0.28):.1f} and {max(5.0, dur-2.5):.1f} where the biggest reaction, shot, punchline, or climax occurs.
            - "impact_stamp": A crisp 1-2 word UPPERCASE stamp matching the moment (e.g. "UNPLAYABLE", "INSANE CATCH", "COOKED", "COLD", "SAVAGE") ONLY if style is aura/roast/gaming/clash, else "".

            Style: {edit_type}
            Video Title: "{clip_data.get('video_title', '')}"
            Transcript:
            {seg_txt[:1800]}

            Return ONLY JSON: {{"title_text": "...", "peak_sec": 9.5, "impact_stamp": "UNPLAYABLE"}}
            """
            raw = (_call_groq(prompt, temperature=0.25) or "").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, dict):
                    if banner_on and edit_type != "clean":
                        t = re.sub(r"[^A-Za-z0-9 !?@#.-]", "", str(parsed.get("title_text", ""))).strip().upper()
                        if 2 <= len(t.split()) <= 6:
                            clip_data["title_text"] = t
                    pk = float(parsed.get("peak_sec", 0))
                    if 2.5 <= pk <= dur - 2.0:
                        clip_data["peak_sec"] = round(pk, 2)
                    st = re.sub(r"[^A-Za-z0-9 !?+-]", "", str(parsed.get("impact_stamp", ""))).strip().upper()
                    if st and "1000" not in st and len(st.split()) <= 2:
                        clip_data["impact_stamp"] = st
        except Exception as e:
            print(f"[MAG73 Meta] Refine warning: {e}")

    if edit_type in FALLBACK_STAMPS:
        cur_stamp = str(clip_data.get("impact_stamp", "")).strip().upper()
        if not cur_stamp or "1000" in cur_stamp:
            pool = FALLBACK_STAMPS[edit_type]
            clip_data["impact_stamp"] = pool[seed % len(pool)]
    else:
        clip_data["impact_stamp"] = ""

    print(
        f"[MAG73 Meta] Hook='{clip_data.get('title_text','')}' | Peak={clip_data.get('peak_sec')}s | "
        f"Stamp='{clip_data.get('impact_stamp','')}' | Variant={clip_data.get('variant_id')} | CapStyle={clip_data.get('caption_style')}"
    )
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


def _is_low_value_clip(clip, words, total_dur):
    """Automatically rejects outros, sponsor ad reads, and boring setup filler."""
    s = float(clip.get("start", 0))
    e = float(clip.get("end", s + 20))
    seg_text = " ".join(
        str(w.get("word", "")).lower()
        for w in (words or [])
        if s <= float(w.get("start", 0)) <= e
    )

    # Reject sponsor / ad reads
    sponsor_hits = sum(
        1 for kw in ("sponsored by", "use my code", "promo code", "download the app", "link in description", "brought to you by")
        if kw in seg_text
    )
    if sponsor_hits >= 1:
        print(f"[MAG73 Filter] Rejected sponsor/ad clip [{int(s)}s-{int(e)}s].")
        return True

    # Reject YouTube outros
    if total_dur > 45 and e >= total_dur - 10:
        outro_hits = sum(
            1 for kw in ("bye", "subscribe", "agli video", "next video", "end this video", "goodbye", "allah hafiz")
            if kw in seg_text
        )
        if outro_hits >= 2:
            print(f"[MAG73 Filter] Rejected outro clip [{int(s)}s-{int(e)}s].")
            return True
    return False


def _deduplicate_clips(clips, max_dur, words):
    valid = []
    for c in clips:
        if not isinstance(c, dict):
            continue
        s = max(0.0, float(c.get("start", 0)))
        e = min(max_dur, float(c.get("end", s + 18)))
        if e - s < 11.0:
            e = min(max_dur, s + 17.0)
        if e - s > 27.0:
            e = s + 25.0
        c["start"] = int(round(s))
        c["end"] = int(round(e))
        if _is_low_value_clip(c, words, max_dur):
            continue
        valid.append(c)

    valid.sort(key=lambda x: int(x.get("score", 80)), reverse=True)
    kept = []
    for c in valid:
        overlaps = False
        for k in kept:
            inter = min(c["end"], k["end"]) - max(c["start"], k["start"])
            min_len = max(1, min(c["end"] - c["start"], k["end"] - k["start"]))
            if inter > 0.30 * min_len or abs(c["start"] - k["start"]) < 8:
                overlaps = True
                break
        if not overlaps:
            kept.append(c)

    kept.sort(key=lambda x: x["start"])
    return kept


def _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=""):
    bgm_enabled = bool(plugin_cfg.get("bgm_enabled", True))
    sfx_enabled = bool(plugin_cfg.get("sfx_enabled", True))
    banner_enabled = bool(plugin_cfg.get("banner_enabled", True))

    # Strict elite threshold (score >= 87) so only genuine bangers pass!
    clips = [c for c in raw_clips if isinstance(c, dict) and int(c.get("score", 80)) >= 87]
    if not clips and raw_clips:
        dict_clips = [c for c in raw_clips if isinstance(c, dict)]
        if dict_clips:
            clips = [max(dict_clips, key=lambda x: int(x.get("score", 0)))]

    clips = _deduplicate_clips(clips, vid_dur, word_timestamps)

    if not clips:
        end_s = min(vid_dur, 22.0)
        fallback_style = style_pref if style_pref in VALID_STYLES else "vlog"
        clips = [
            {
                "start": 0,
                "end": int(max(10.0, end_s)),
                "score": 88,
                "edit_type": fallback_style,
                "layout_mode": "vertical_full",
                "focus_x": "center",
                "title_text": "WATCH THIS MOMENT!" if banner_enabled else "",
                "peak_sec": int(min(10.0, max(3.0, end_s * 0.5))),
            }
        ]

    style_counters = {}
    for idx, c in enumerate(clips):
        et = str(c.get("edit_type", "vlog")).strip().lower()
        if style_pref in VALID_STYLES and style_pref != "auto":
            et = style_pref
        elif et not in VALID_STYLES:
            et = "vlog"
        c["edit_type"] = et
        c["video_title"] = video_title

        count_for_style = style_counters.get(et, 0)
        style_counters[et] = count_for_style + 1

        c["variant_id"] = (count_for_style + idx) % 5
        c["caption_style"] = CAPTION_STYLES[(idx + count_for_style) % len(CAPTION_STYLES)]

        if bgm_enabled and et != "clean":
            c["bgm_query"] = _pick_unique_bgm_query(et, count_for_style + idx)
        else:
            c["bgm_query"] = ""

        if sfx_enabled and et != "clean":
            c["sfx_query"] = DEFAULT_SFX_BY_STYLE.get(et, "")
        else:
            c["sfx_query"] = ""

        if not banner_enabled:
            c["title_text"] = ""
        elif not str(c.get("title_text", "")).strip() and et != "clean":
            c["title_text"] = "WATCH THIS MOMENT!"

        if et in FALLBACK_STAMPS:
            st = str(c.get("impact_stamp", "")).strip().upper()
            if not st or "1000" in st:
                pool = FALLBACK_STAMPS[et]
                c["impact_stamp"] = pool[(idx + count_for_style) % len(pool)]
        else:
            c["impact_stamp"] = ""

    print(
        f"[MAG73 Director] Approved {len(clips)} elite clip(s): "
        f"{[(c['edit_type'], 'v'+str(c['variant_id']), c['caption_style']) for c in clips]}"
    )
    return clips


def run_fast_scan_council(audio_path, audience_signals, video_path=None):
    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    custom_prompt = os.getenv("CUSTOM_PROMPT", "").strip()
    video_title = str(audience_signals.get("video_title", "") or "")

    transcript_text, word_timestamps, _ = extract_accurate_transcript(
        audio_path, caption_lang=caption_lang, is_audio_only=True, context_hint=video_title
    )
    vid_dur = float(audience_signals.get("duration") or 0.0) or _get_media_duration_sec(audio_path)

    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION (OBEY STRICTLY): {custom_prompt}\n" if custom_prompt else ""

    prompt = f"""
    You are a RUTHLESS, ELITE VIRAL REELS / SHORTS CURATOR (10M+ views standard).
    {user_rule}
    Video Title: "{video_title}"
    Video Duration: {int(vid_dur)} seconds
    User Style Preference: "{style_pref}" (if "auto", give EACH clip its own natural distinct style!)

    AUDIENCE VIRAL SIGNALS (Prioritize these moments!):
    - YouTube Most-Replayed Heatmap Spikes (sec): {audience_signals.get('heatmap_spikes', [])}
    - Top Comment Timestamps (sec): {audience_signals.get('comment_timestamps', [])}
    - Top Comments: {audience_signals.get('top_comments', [])[:10]}

    TIMESTAMPED TRANSCRIPT ([Xs] seconds):
    {transcript_text[:22000]}

    STRICT ELITE CURATION RULES (CRITICAL):
    1. ONLY pick genuine 9/10 or 10/10 VIRAL BANGERS (score 87-100): insane catches/shots/kills, hilarious roasts, shocking twists, mind-blowing reactions, intense clashes, or viral punchlines.
    2. HARD REJECT ALL OF THESE:
       - Sponsored segments / product demos / ad reads (e.g. asking an AI/app a promo question, promo codes).
       - Boring setup / walking around / placing fielders ("go back, move left, sir more more").
       - Intros ("welcome back"), rule explanations, quiet filler, and outros ("like subscribe bye").
    3. TIGHT PUNCHY PACING: Keep clips tight (**14 to 25 seconds**). Start 2 seconds BEFORE the hook/action and end cleanly right after the payoff/reaction!
    4. MIX STYLES NATURALLY ("roast", "aura", "aesthetic", "funny", "gaming", "vlog", "drama", "clash", "informative").
    5. EXACT HOOK TITLE ("title_text"): Punchy 3-5 word uppercase ASCII hook strictly about THAT clip.
    6. "impact_stamp": Unique 1-2 word stamp ("INSANE CATCH", "UNPLAYABLE", "COOKED", "SAVAGE", "PURE CLASS").

    Return ONLY valid JSON array:
    [
      {{
        "start": 42,
        "end": 62,
        "score": 93,
        "edit_type": "aura",
        "layout_mode": "vertical_full",
        "focus_x": "center",
        "title_text": "UNBELIEVABLE ONE HANDED CATCH",
        "impact_stamp": "UNREAL",
        "peak_sec": 10
      }}
    ]
    """
    raw_out = _call_groq(prompt, temperature=0.22)
    raw_clips = _clean_json(raw_out)
    return _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title)


def run_super_ai_council(video_path, audience_signals):
    if isinstance(audience_signals, list):
        audience_signals = {"chat_spikes": audience_signals, "heatmap_spikes": [], "comment_timestamps": [], "top_comments": []}

    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    custom_prompt = os.getenv("CUSTOM_PROMPT", "").strip()
    video_title = str(audience_signals.get("video_title", "") or "")

    transcript_text, word_timestamps, _ = extract_accurate_transcript(
        video_path, caption_lang=caption_lang, context_hint=video_title
    )
    vid_dur = _get_media_duration_sec(video_path)

    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""
    prompt = f"""
    You are an ELITE VIRAL REELS DIRECTOR.
    {user_rule}
    Style Preference: "{style_pref}"
    Chat Spikes: {audience_signals.get('chat_spikes', [])}
    Transcript:
    {transcript_text[:16000]}

    Return ONLY valid JSON array of genuine peak viral moments (14-25s, score 87-100, reject filler/setup/ads) with diverse "edit_type", "layout_mode", "title_text" (3-5 ASCII words), "impact_stamp" (1-2 words), and "peak_sec".
    """
    raw_out = _call_groq(prompt, temperature=0.22)
    raw_clips = _clean_json(raw_out)
    clips = _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title)
    return clips, word_timestamps
