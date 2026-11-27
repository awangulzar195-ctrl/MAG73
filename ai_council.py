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
_local_whisper_models = {}

VALID_STYLES = ("roast", "aura", "aesthetic", "vlog", "gaming", "funny", "drama", "clash", "informative", "clean")
LIVE_VARIETY_STYLES = ("gaming", "funny", "clash", "aura", "roast")
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
        "ytsearch1:emotional inspiring cinematic piano instrumental no copyright",
        "ytsearch1:moody dark ambient motivation instrumental no copyright",
        "ytsearch1:slowed reverb emotional cinema beat no copyright",
        "ytsearch1:deep atmospheric epic sports edit music no copyright",
        "ytsearch1:nostalgic lofi cinema beat instrumental no copyright",
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
        "ytsearch1:warm emotional inspiring vlog piano beat no copyright",
        "ytsearch1:chill aesthetic lifestyle vlog lofi beat no copyright",
        "ytsearch1:modern cinematic storytelling vlog music no copyright",
        "ytsearch1:smooth acoustic chill hip hop vlog beat no copyright",
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
    ],
    "clean": [""],
}

DEFAULT_SFX_BY_STYLE = {
    "roast": "ytsearch1:vine boom bass drop impact sfx",
    "aura": "ytsearch1:cinematic bass drop impact sound effect",
    "gaming": "ytsearch1:cinematic bass impact hit sfx",
    "clash": "ytsearch1:dramatic bass boom sfx",
    "funny": "ytsearch1:vine boom sound effect short",
    "aesthetic": "",
    "vlog": "",
    "drama": "",
    "informative": "",
    "clean": "",
}

# Stamps ONLY for genuine hype/action/roast styles (NEVER vlog/aesthetic/drama!)
HYPE_STAMP_POOLS = {
    "aura": ["COLD", "ICE COLD", "UNPLAYABLE", "PURE CLASS", "GOD TIER", "BUILT DIFFERENT", "RESPECT", "CINEMA"],
    "roast": ["ROASTED", "COOKED", "VIOLATION", "SAVAGE", "NO MERCY", "EXPOSED", "HUMBLED", "CHECKMATE"],
    "gaming": ["CLUTCH", "CRACKED", "INSANE", "CLEAN", "DOMINATED", "PRO MOVE", "GOD MODE", "CHAOS"],
    "clash": ["COOKED", "HEATED", "NO WAY", "SAVAGE", "INTENSE", "COLD REPLY"],
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
                    timeout=40,
                )
                if res.status_code == 200:
                    _working_groq_model = model_name
                    data = res.json()
                    choices = data.get("choices") or []
                    if choices:
                        return choices[0].get("message", {}).get("content", "") or ""
                elif res.status_code == 429:
                    time.sleep(random.uniform(1.0, 2.0))
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


def _gemini_transcribe_clip_audio(audio_path, caption_lang="hinglish"):
    """
    HIGH-NOISE GAMER AUDIO RESCUE:
    When loud GTA/BGMI game noise makes Whisper miss Hindi speech, Gemini 2.5 Flash listens
    directly to the clip audio and outputs accurate timestamped Hinglish/English phrases!
    """
    if not gemini_client or not audio_path or not os.path.exists(audio_path):
        return "", []
    try:
        print("[MAG73 Audio] Running Gemini direct audio transcription rescue...")
        uploaded = gemini_client.files.upload(file=audio_path)
        deadline = time.time() + 45
        audio_file = uploaded
        while time.time() < deadline:
            info = gemini_client.files.get(name=uploaded.name)
            state = getattr(info.state, "name", str(info.state))
            if state == "ACTIVE":
                audio_file = info
                break
            if state == "FAILED":
                return "", []
            time.sleep(2)

        style_rule = (
            "clean English (ASCII A-Z)"
            if caption_lang == "en"
            else "natural Roman Hinglish (write Hindi spoken words in Roman letters like 'Arre bhai train rok de', keep English words in English — NEVER translate Hindi into English!)"
        )
        prompt = f"""
        Listen carefully to ALL spoken human dialogue in this short clip (ignore game engine/background noise).
        Transcribe EVERY spoken sentence accurately in {style_rule} with exact start and end seconds.
        Break into short 2-5 word caption chunks.
        Return ONLY a valid JSON array:
        [{{"start": 0.4, "end": 1.8, "text": "Arre ye dekho kya kar raha hai"}}]
        """
        for gm in ("gemini-2.5-flash", "gemini-2.0-flash"):
            try:
                res = gemini_client.models.generate_content(model=gm, contents=[audio_file, prompt])
                items = _clean_json(res.text or "")
                words = []
                full_parts = []
                for it in items:
                    txt = str(it.get("text", "")).strip()
                    toks = [t for t in txt.split() if t]
                    if not toks:
                        continue
                    full_parts.append(txt)
                    s = max(0.0, float(it.get("start", 0)))
                    e = max(s + 0.3, float(it.get("end", s + 1.1)))
                    step = (e - s) / len(toks)
                    for idx, tok in enumerate(toks):
                        words.append({
                            "word": _devanagari_to_roman(tok),
                            "start": round(s + idx * step, 2),
                            "end": round(s + (idx + 1) * step, 2),
                        })
                if len(words) >= 5:
                    print(f"[MAG73 Audio] Gemini rescue transcribed {len(words)} words cleanly!")
                    return " ".join(full_parts), words
            except Exception as e:
                print(f"[MAG73 Audio] Gemini rescue {gm} warn: {str(e)[:80]}")
    except Exception as e:
        print(f"[MAG73 Audio] Gemini rescue warning: {e}")
    return "", []


def _gemini_direct_audio_scan(audio_path, audience_signals, style_pref, custom_prompt):
    if not gemini_client or not audio_path or not os.path.exists(audio_path):
        return []
    try:
        print("[MAG73 Fast Scan] Using Gemini direct cloud audio scan...")
        uploaded = gemini_client.files.upload(file=audio_path)
        deadline = time.time() + 45
        audio_file = uploaded
        while time.time() < deadline:
            info = gemini_client.files.get(name=uploaded.name)
            state = getattr(info.state, "name", str(info.state))
            if state == "ACTIVE":
                audio_file = info
                break
            if state == "FAILED":
                return []
            time.sleep(2)

        user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""
        prompt = f"""
        Listen to this entire audio and find ALL genuine 9/10 or 10/10 VIRAL REELS / SHORTS moments (14-25s each, score 86-100).
        {user_rule}
        Video Title: "{audience_signals.get('video_title', '')}"
        YouTube Most-Replayed Spikes (sec): {audience_signals.get('heatmap_spikes', [])}
        Style Preference: "{style_pref}" (if "auto", choose exact natural style: "vlog", "aesthetic", "gaming", "funny", "roast", "aura", "clash", "drama", "informative").
        CRITICAL: Emotional / charity / storytelling / vlog moments MUST be "vlog" or "aesthetic" with impact_stamp ""!
        REJECT intros, sponsor ads, setup filler, and outros!

        Return ONLY valid JSON array:
        [{{"start": 42, "end": 62, "score": 92, "edit_type": "vlog", "layout_mode": "vertical_full", "focus_x": "center", "title_text": "DREAM RESTAURANT REVEAL", "impact_stamp": "", "peak_sec": 10}}]
        """
        for gm in ("gemini-2.5-flash", "gemini-2.0-flash"):
            try:
                res = gemini_client.models.generate_content(model=gm, contents=[audio_file, prompt])
                clips = _clean_json(res.text or "")
                if clips:
                    print(f"[MAG73 Fast Scan] Gemini direct audio found {len(clips)} viral clip(s)!")
                    return clips
            except Exception as e:
                print(f"[MAG73 Fast Scan] {gm} warning: {str(e)[:80]}")
    except Exception as e:
        print(f"[MAG73 Fast Scan] Gemini audio scan warning: {e}")
    return []


def _local_faster_whisper_transcribe(audio_path, caption_lang="hinglish", fast_scan=False):
    if not HAS_FASTER_WHISPER or not os.path.exists(audio_path):
        return "", []
    model_size = "tiny" if fast_scan else "base"
    try:
        model = _local_whisper_models.get(model_size)
        if model is None:
            print(f"[MAG73 Offline Whisper] Loading {model_size} int8 model on CPU...")
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            _local_whisper_models[model_size] = model

        # Force language="hi" for Hinglish so mixed Hindi+English NEVER turns into broken English!
        lang_arg = "en" if caption_lang == "en" else "hi"
        segments, info = model.transcribe(
            audio_path,
            language=lang_arg,
            word_timestamps=(not fast_scan),
            vad_filter=False,  # Keep FALSE so loud gaming audio never drops Hindi commentary!
            condition_on_previous_text=False,
            beam_size=(1 if fast_scan else 2),
        )
        words = []
        full_parts = []
        for seg in segments:
            full_parts.append(seg.text.strip())
            if (not fast_scan) and seg.words:
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
        print(f"[MAG73 Offline Whisper ({model_size}, lang={lang_arg})] Extracted {len(words)} words.")
        return " ".join(full_parts), words
    except Exception as e:
        print(f"[MAG73 Offline Whisper] Warning: {e}")
        return "", []


def _proofread_and_format_words(words, full_context, mode="hinglish", context_hint=""):
    """
    Converts Devanagari Hindi -> crisp natural Roman Hinglish (e.g. 'भाई रोक दे' -> 'Bhai rok de')
    and Devanagari-spelled English -> clean English (e.g. 'आई नीड योर हेल्प' -> 'I need your help'),
    while strictly preserving exact word count and timestamps!
    """
    if not words:
        return words
    try:
        raw_list = [str(w.get("word", "")).strip() for w in words]
        fixed_all = []
        for i in range(0, len(raw_list), 60):
            chunk = raw_list[i:i + 60]
            if mode == "en":
                lang_rule = "Translate/clean every item into crisp natural English (ASCII A-Z only)."
            else:
                lang_rule = (
                    "Convert every item into natural Roman Hinglish (ASCII A-Z only): "
                    "write Hindi words in crisp Roman Hindi (e.g. 'क्या'->'Kya', 'बात'->'baat', 'भाई'->'bhai', 'रोक'->'rok'), "
                    "and write English words spelled in Hindi back into real English (e.g. 'आई'->'I', 'नीड'->'need', 'हेल्प'->'help', 'ट्रेन'->'train', 'स्पॉन्सर'->'sponsor'). "
                    "DO NOT translate Hindi sentences into English!"
                )

            prompt = f"""
            You are an expert Indian Hinglish caption formatter. {lang_rule}
            Video Topic Hint: "{context_hint}"
            CRITICAL: Return ONLY a valid JSON array of strings of the EXACT SAME LENGTH ({len(chunk)} items). Do NOT merge or drop items!
            Sentence Context: {full_context[:350]}
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
        print(f"[MAG73 Captions] Formatted {len(words)} Hinglish/English words accurately.")
    except Exception as e:
        print(f"[MAG73 Captions] Format warning: {e}")
    return words


def extract_accurate_transcript(media_path="source_video.mp4", caption_lang="hinglish", is_audio_only=False, context_hint="", fast_scan=False):
    audio_path = "temp_vocal_16k.mp3"
    bitrate = "24k" if fast_scan else "64k"
    try:
        # Gentle vocal clarity filter (preserves Hindi voice cleanly even in loud GTA/BGMI streams!)
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", media_path,
                "-vn", "-af", "highpass=f=90,dynaudnorm=f=150:g=9",
                "-ac", "1", "-ar", "16000", "-b:a", bitrate, audio_path,
            ],
            check=True,
            timeout=50,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        if is_audio_only and media_path and os.path.exists(media_path):
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
            # KEY FIX: Force language="hi" for Hinglish so Hindi NEVER gets mistranslated to broken English!
            "language": "en" if caption_lang == "en" else "hi",
        }
        try:
            with open(audio_path, "rb") as f:
                res = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {GROQ_KEY}"},
                    files={"file": f},
                    data=form_data,
                    timeout=45,
                )
            if res.status_code == 200:
                data = res.json()
                words = data.get("words") or []
                text = data.get("text") or ""
                if not words and data.get("segments"):
                    words = _words_from_segments(data.get("segments"))
                print(f"[MAG73 Audio] Groq Whisper ({form_data['language']}) extracted {len(words)} words.")
            else:
                print(f"[MAG73 Audio] Groq Whisper HTTP {res.status_code}")
        except Exception as e:
            print(f"[MAG73 Audio] Groq Whisper skipped ({e})")

    # For short clips (<=45s) where loud game audio caused Whisper to return <12 words, rescue via Gemini Audio!
    dur_check = _get_media_duration_sec(audio_path)
    if (not fast_scan) and len(words) < 12 and dur_check <= 45.0:
        g_txt, g_words = _gemini_transcribe_clip_audio(audio_path, caption_lang=caption_lang)
        if len(g_words) > len(words):
            words = g_words
            text = g_txt

    # Offline fallback only if still empty and short enough
    if len(words) < 5 and ((not fast_scan) or dur_check <= 240.0):
        fw_text, fw_words = _local_faster_whisper_transcribe(
            audio_path, caption_lang=caption_lang, fast_scan=fast_scan
        )
        if len(fw_words) > len(words):
            words = fw_words
            text = fw_text

    if words:
        if (not fast_scan) and len(words) <= 220:
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
    """
    Verifies on the EXACT 0.000s trimmed clip:
    1. True mood (`edit_type`): ensures emotional/charity/story clips stay `vlog`/`aesthetic` (NO SAVAGE/LETHAL/B&W!).
    2. Exact matching Hook Title (never generic 'HIGHLIGHT MOMENT!').
    3. Exact climax `peak_sec` and contextual stamp ONLY if hype/action/roast.
    """
    plugin_cfg = _get_plugin_config()
    banner_on = bool(plugin_cfg.get("banner_enabled", True))
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    edit_type = str(clip_data.get("edit_type", "vlog")).lower()
    dur = max(10.0, float(clip_data.get("end", 20.0)) - float(clip_data.get("start", 0.0)))
    run_num = int(os.getenv("GITHUB_RUN_NUMBER", "1") or "1")
    seed = run_num + int(clip_data.get("orig_start", 0)) + int(clip_data.get("clip_index", 0)) * 7

    if not banner_on or edit_type == "clean":
        clip_data["title_text"] = ""

    seg_txt = (segment_transcript or "").strip()
    if len(seg_txt) >= 12:
        try:
            prompt = f"""
            Analyze this EXACT 0.0s-to-{dur:.1f}s clip transcript and return ONLY a JSON object:
            - "edit_type": Pick the TRUE mood of this clip from ["vlog", "aesthetic", "gaming", "funny", "roast", "aura", "clash", "drama", "informative", "clean"].
              CRITICAL: If someone is asking for help, sharing an emotional/inspiring story, charity, medals, or calm vlog -> MUST be "vlog" or "aesthetic" (NEVER "roast" or "aura"!).
              If it is chaotic GTA/BGMI/gaming stream shouting/chasing/clutches -> "gaming", "funny", or "clash".
            - "title_text": Punchy 3-5 word UPPERCASE ASCII hook strictly about THIS transcript (e.g. "HELPING A NATIONAL CHAMPION", "TRAIN NAHI RUK RAHI BHAI!").
            - "peak_sec": Exact float second between {max(3.0, dur*0.28):.1f} and {max(5.0, dur-2.2):.1f} where the biggest reaction/payoff happens.
            - "impact_stamp": Crisp 1-2 word UPPERCASE stamp ONLY for gaming/roast/aura/clash (e.g. "CHAOS", "CLUTCH", "COOKED", "UNPLAYABLE"). MUST be "" (empty string) for vlog, aesthetic, drama, informative, clean!

            Video Title: "{clip_data.get('video_title', '')}"
            Current Style Hint: "{edit_type}" (User override: "{style_pref}")
            Exact Clip Transcript:
            {seg_txt[:1800]}

            Return ONLY JSON: {{"edit_type": "vlog", "title_text": "...", "peak_sec": 10.5, "impact_stamp": ""}}
            """
            raw = (_call_groq(prompt, temperature=0.2) or "").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, dict):
                    ai_et = str(parsed.get("edit_type", "")).strip().lower()
                    if style_pref == "auto" and ai_et in VALID_STYLES:
                        edit_type = ai_et
                        clip_data["edit_type"] = edit_type
                        if bool(plugin_cfg.get("bgm_enabled", True)) and edit_type != "clean":
                            clip_data["bgm_query"] = _pick_unique_bgm_query(edit_type, seed)
                        clip_data["sfx_query"] = DEFAULT_SFX_BY_STYLE.get(edit_type, "") if bool(plugin_cfg.get("sfx_enabled", True)) else ""

                    if banner_on and edit_type != "clean":
                        t = re.sub(r"[^A-Za-z0-9 !?@#.-]", "", str(parsed.get("title_text", ""))).strip().upper()
                        if 2 <= len(t.split()) <= 6:
                            clip_data["title_text"] = t

                    pk = float(parsed.get("peak_sec", 0))
                    if 2.5 <= pk <= dur - 2.0:
                        clip_data["peak_sec"] = round(pk, 2)

                    st = re.sub(r"[^A-Za-z0-9 !?+-]", "", str(parsed.get("impact_stamp", ""))).strip().upper()
                    if edit_type in HYPE_STAMP_POOLS and st and "1000" not in st and len(st.split()) <= 2:
                        clip_data["impact_stamp"] = st
                    else:
                        clip_data["impact_stamp"] = ""
        except Exception as e:
            print(f"[MAG73 Meta] Refine warning: {e}")

    # Strictly forbid stamps on vlog/aesthetic/drama/informative/clean!
    if edit_type not in HYPE_STAMP_POOLS:
        clip_data["impact_stamp"] = ""
    else:
        cur_stamp = str(clip_data.get("impact_stamp", "")).strip().upper()
        if not cur_stamp or "1000" in cur_stamp:
            pool = HYPE_STAMP_POOLS[edit_type]
            clip_data["impact_stamp"] = pool[seed % len(pool)]

    print(
        f"[MAG73 Meta] Style={edit_type} | Hook='{clip_data.get('title_text','')}' | "
        f"Peak={clip_data.get('peak_sec')}s | Stamp='{clip_data.get('impact_stamp','')}'"
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
    if not media_path or not os.path.exists(media_path):
        return 60.0
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
    s = float(clip.get("start", 0))
    e = float(clip.get("end", s + 20))
    seg_text = " ".join(
        str(w.get("word", "")).lower()
        for w in (words or [])
        if s <= float(w.get("start", 0)) <= e
    )
    sponsor_hits = sum(
        1 for kw in ("sponsored by", "use my code", "promo code", "download the app", "link in description", "brought to you by")
        if kw in seg_text
    )
    if sponsor_hits >= 1:
        return True
    if total_dur > 45 and e >= total_dur - 10:
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


def _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title="", is_live=False):
    bgm_enabled = bool(plugin_cfg.get("bgm_enabled", True))
    sfx_enabled = bool(plugin_cfg.get("sfx_enabled", True))
    banner_enabled = bool(plugin_cfg.get("banner_enabled", True))
    run_seed = int(os.getenv("GITHUB_RUN_NUMBER", "0") or "0") + int(time.time()) % 97

    dict_clips = [c for c in (raw_clips or []) if isinstance(c, dict)]
    clips = [c for c in dict_clips if int(c.get("score", 80)) >= (78 if is_live else 84)]
    if not clips and dict_clips:
        clips = sorted(dict_clips, key=lambda x: int(x.get("score", 0)), reverse=True)[:4]

    clips = _deduplicate_clips(clips, vid_dur, word_timestamps)

    if not clips:
        end_s = min(vid_dur, 22.0)
        fallback_style = style_pref if style_pref in VALID_STYLES else (
            LIVE_VARIETY_STYLES[run_seed % len(LIVE_VARIETY_STYLES)] if is_live else "vlog"
        )
        clips = [
            {
                "start": 0,
                "end": int(max(12.0, end_s)),
                "score": 86,
                "edit_type": fallback_style,
                "layout_mode": "vertical_full",
                "focus_x": "center",
                "title_text": "" if not banner_enabled else "CRAZY MOMENT!",
                "peak_sec": int(min(10.0, max(3.5, end_s * 0.5))),
            }
        ]

    style_counters = {}
    for idx, c in enumerate(clips):
        et = str(c.get("edit_type", "vlog")).strip().lower()
        if style_pref in VALID_STYLES and style_pref != "auto":
            et = style_pref
        elif et not in VALID_STYLES:
            et = LIVE_VARIETY_STYLES[(run_seed + idx) % len(LIVE_VARIETY_STYLES)] if is_live else "vlog"
        c["edit_type"] = et
        c["video_title"] = video_title

        count_for_style = style_counters.get(et, 0)
        style_counters[et] = count_for_style + 1

        mix_seed = run_seed + idx * 3 + count_for_style
        c["variant_id"] = mix_seed % 5
        c["caption_style"] = CAPTION_STYLES[mix_seed % len(CAPTION_STYLES)]

        if bgm_enabled and et != "clean":
            c["bgm_query"] = _pick_unique_bgm_query(et, mix_seed)
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

        if et in HYPE_STAMP_POOLS:
            st = str(c.get("impact_stamp", "")).strip().upper()
            if not st or "1000" in st:
                pool = HYPE_STAMP_POOLS[et]
                c["impact_stamp"] = pool[mix_seed % len(pool)]
        else:
            c["impact_stamp"] = ""

    print(
        f"[MAG73 Director] Approved {len(clips)} clip(s): "
        f"{[(c['edit_type'], 'v'+str(c['variant_id']), c['caption_style']) for c in clips]}"
    )
    return clips


def run_fast_scan_council(audio_path, audience_signals, video_path=None, preloaded_words=None):
    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    custom_prompt = os.getenv("CUSTOM_PROMPT", "").strip()
    video_title = str(audience_signals.get("video_title", "") or "")

    word_timestamps = []
    transcript_text = ""

    if preloaded_words and len(preloaded_words) >= 35:
        word_timestamps = preloaded_words
        for w in word_timestamps:
            txt = str(w.get("word", "")).strip()
            if txt and not txt.isascii():
                w["word"] = _devanagari_to_roman(txt)
        transcript_text = _build_timestamped_transcript(word_timestamps, bucket_sec=5)
        print(f"[MAG73 Fast Scan] Using instant YouTube transcript ({len(word_timestamps)} words)!")
    elif audio_path and os.path.exists(audio_path):
        transcript_text, word_timestamps, _ = extract_accurate_transcript(
            audio_path, caption_lang=caption_lang, is_audio_only=True, context_hint=video_title, fast_scan=True
        )

    vid_dur = float(audience_signals.get("duration") or 0.0)
    if vid_dur <= 0:
        vid_dur = _get_media_duration_sec(audio_path) if audio_path else (
            float(word_timestamps[-1]["end"]) if word_timestamps else 180.0
        )

    if len(transcript_text) < 40 and audio_path and os.path.exists(audio_path):
        gem_clips = _gemini_direct_audio_scan(audio_path, audience_signals, style_pref, custom_prompt)
        if gem_clips:
            return _finalize_clip_list(gem_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title, is_live=False)

    if len(transcript_text) < 40 and audience_signals.get("heatmap_spikes"):
        hm_clips = []
        for sp in audience_signals["heatmap_spikes"][:6]:
            st = max(0, int(sp) - 5)
            en = min(int(vid_dur), st + 22)
            hm_clips.append({
                "start": st, "end": en, "score": 90,
                "edit_type": "vlog", "layout_mode": "vertical_full",
                "focus_x": "center", "title_text": "MOST REPLAYED MOMENT",
                "impact_stamp": "", "peak_sec": 10,
            })
        return _finalize_clip_list(hm_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title, is_live=False)

    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION (OBEY STRICTLY): {custom_prompt}\n" if custom_prompt else ""

    prompt = f"""
    You are a RUTHLESS, ELITE VIRAL REELS / SHORTS CURATOR (10M+ views standard).
    {user_rule}
    Video Title: "{video_title}"
    Video Duration: {int(vid_dur)} seconds
    User Style Preference: "{style_pref}" (if "auto", give EACH clip its exact natural style!)

    AUDIENCE VIRAL SIGNALS:
    - YouTube Most-Replayed Heatmap Spikes (sec): {audience_signals.get('heatmap_spikes', [])}

    TIMESTAMPED TRANSCRIPT ([Xs] seconds):
    {transcript_text[:22000]}

    STRICT ELITE CURATION RULES:
    1. Pick ALL genuine 9/10 or 10/10 VIRAL MOMENTS across the ENTIRE video (14-25s each, score 85-100).
    2. HARD REJECT: sponsor ad reads, promo codes, boring setup filler, and outros ("like subscribe bye").
    3. ACCURATE STYLE PER CLIP:
       - Emotional / charity / inspiring / vlog storytelling -> "vlog" or "aesthetic" (impact_stamp MUST be "")!
       - Gaming clutches / chaotic gameplay -> "gaming" or "funny".
       - Savage insults / cold comebacks -> "roast" or "aura".
    4. EXACT HOOK TITLE ("title_text"): Punchy 3-5 word uppercase ASCII hook strictly about THAT clip.

    Return ONLY valid JSON array:
    [
      {{
        "start": 42,
        "end": 62,
        "score": 93,
        "edit_type": "vlog",
        "layout_mode": "vertical_full",
        "focus_x": "center",
        "title_text": "HELPING A NATIONAL CHAMPION",
        "impact_stamp": "",
        "peak_sec": 10
      }}
    ]
    """
    raw_out = _call_groq(prompt, temperature=0.22)
    raw_clips = _clean_json(raw_out)
    return _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title, is_live=False)


def run_super_ai_council(video_path, audience_signals):
    if isinstance(audience_signals, list):
        audience_signals = {"chat_spikes": audience_signals, "heatmap_spikes": [], "comment_timestamps": [], "top_comments": [], "video_title": ""}

    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    custom_prompt = os.getenv("CUSTOM_PROMPT", "").strip()
    video_title = str(audience_signals.get("video_title", "") or "")

    transcript_text, word_timestamps, _ = extract_accurate_transcript(
        video_path, caption_lang=caption_lang, context_hint=video_title, fast_scan=False
    )
    vid_dur = _get_media_duration_sec(video_path)

    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""
    prompt = f"""
    You are an ELITE VIRAL STREAM CLIPPER & REELS DIRECTOR.
    {user_rule}
    Stream Title: "{video_title}"
    Captured Segment Duration: {int(vid_dur)}s
    Style Preference: "{style_pref}" (if "auto", choose the exact best style from: "gaming", "funny", "aura", "roast", "clash", "vlog", "aesthetic")

    Transcript:
    {transcript_text[:10000]}

    Pick the SINGLE best punchiest 14-24s highlight inside this captured live segment.
    Return ONLY valid JSON array of 1 item with "start", "end", "score" (88), "edit_type", "layout_mode", "title_text" (3-5 uppercase ASCII words matching the spoken dialogue!), "impact_stamp" (1-2 words for gaming/roast/aura/clash, else ""), and "peak_sec".
    """
    raw_out = _call_groq(prompt, temperature=0.28)
    raw_clips = _clean_json(raw_out)
    clips = _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title, is_live=True)
    return clips, word_timestamps
