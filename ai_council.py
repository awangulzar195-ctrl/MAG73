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

# ALL 22 EXACT INSTAGRAM REEL SUB-TYPES GROUPED BY CATEGORY
SUBTYPES_BY_STYLE = {
    "aura": [
        "aura_minimal_glow",
        "aura_skull_freeze",
        "aura_mindset_statement",
        "aura_velocity_ramp",
        "aura_crimson_devil",
        "aura_ice_cold_drop",
        "roast_red_ribbon_drop",
        "switch_attitude_drop",
    ],
    "roast": [
        "roast_red_ribbon_drop",
        "roast_double_meaning",
        "aura_skull_freeze",
        "aura_crimson_devil",
        "switch_attitude_drop",
    ],
    "clash": [
        "roast_red_ribbon_drop",
        "aura_crimson_devil",
        "aura_skull_freeze",
        "switch_attitude_drop",
    ],
    "aesthetic": [
        "emo_brotherhood_story",
        "emo_wholesome_heart_drop",
        "emo_moody_tribute",
        "emo_broken_silence",
        "switch_banter_aesthetic",
    ],
    "vlog": [
        "emo_wholesome_heart_drop",
        "emo_brotherhood_story",
        "emo_moody_tribute",
        "comedy_red_ribbon",
        "switch_banter_aesthetic",
    ],
    "drama": [
        "emo_broken_silence",
        "emo_brotherhood_story",
        "roast_red_ribbon_drop",
        "aura_mindset_statement",
    ],
    "funny": [
        "comedy_letterbox_classic",
        "comedy_letterbox_lyric",
        "comedy_red_ribbon",
        "comedy_meme_pop",
        "switch_banter_aesthetic",
    ],
    "gaming": [
        "gaming_stacked_comeback",
        "gaming_esports_montage",
        "gaming_clutch_skull",
        "gaming_lobby_troll",
        "aura_velocity_ramp",
    ],
    "informative": [
        "aura_mindset_statement",
        "emo_moody_tribute",
    ],
    "clean": [
        "clean_minimal",
    ],
}

ALL_SUBTYPES = sorted({st for lst in SUBTYPES_BY_STYLE.values() for st in lst})

# DEFAULT EMOJI PER SUB-TYPE
DEFAULT_EMOJI_BY_SUBTYPE = {
    "roast_red_ribbon_drop": "skull",
    "roast_double_meaning": "eyes",
    "aura_minimal_glow": "cold",
    "aura_skull_freeze": "skull",
    "aura_mindset_statement": "none",
    "aura_velocity_ramp": "fire",
    "aura_crimson_devil": "crown",
    "aura_ice_cold_drop": "cold",
    "emo_brotherhood_story": "none",
    "emo_wholesome_heart_drop": "heart",
    "emo_moody_tribute": "none",
    "emo_broken_silence": "broken_heart",
    "comedy_letterbox_classic": "laugh",
    "comedy_letterbox_lyric": "laugh",
    "comedy_red_ribbon": "laugh",
    "comedy_meme_pop": "mindblown",
    "gaming_stacked_comeback": "fire",
    "gaming_esports_montage": "crown",
    "gaming_clutch_skull": "skull",
    "gaming_lobby_troll": "laugh",
    "switch_banter_aesthetic": "heart",
    "switch_attitude_drop": "crown",
    "clean_minimal": "none",
}

# HUGE ROTATING PHONK / EMOTIONAL / COMEDY / ESPORTS BGM POOLS (ZERO REPETITION!)
BGM_POOLS = {
    "aura": [
        "ytsearch1:dark brazilian phonk slowed reverb edit instrumental no copyright",
        "ytsearch1:sigma cold edit dark bass phonk slowed royalty free",
        "ytsearch1:aggressive funk montagen slowed bass drop no copyright",
        "ytsearch1:metamorphosis style dark phonk slowed instrumental no copyright",
        "ytsearch1:hardwave cyberpunk dark synth edit beat no copyright",
        "ytsearch1:menacing drill dark bass sports edit instrumental no copyright",
        "ytsearch1:dark sigma male attitude phonk instrumental royalty free",
        "ytsearch1:ultra slowed dark aura edit bass beat no copyright",
    ],
    "roast": [
        "ytsearch1:savage roast dark phonk edit instrumental no copyright",
        "ytsearch1:gangster sigma funk roast beat slowed no copyright",
        "ytsearch1:hard bass trap roast comeback instrumental no copyright",
        "ytsearch1:dark brazilian funk savage edit beat royalty free",
        "ytsearch1:menacing hip hop roast beat instrumental no copyright",
        "ytsearch1:cold sigma phonk drop instrumental no copyright",
    ],
    "aesthetic": [
        "ytsearch1:soulful punjabi slowed reverb emotional instrumental no copyright",
        "ytsearch1:emotional inspiring cinematic piano slowed instrumental no copyright",
        "ytsearch1:moody dark ambient motivation slowed beat no copyright",
        "ytsearch1:brotherhood loyalty emotional violin piano instrumental no copyright",
        "ytsearch1:aesthetic dreamy slowed reverb edit music no copyright",
        "ytsearch1:deep nostalgic lofi cinema instrumental no copyright",
    ],
    "gaming": [
        "ytsearch1:energetic esports montage phonk beat no copyright",
        "ytsearch1:fast hype electronic trap gaming clutch beat no copyright",
        "ytsearch1:brazilian funk gaming montage instrumental no copyright",
        "ytsearch1:adrenaline bass drop esports highlight music no copyright",
        "ytsearch1:hard trap montage edit beat instrumental no copyright",
        "ytsearch1:hyper aggressive gaming phonk instrumental no copyright",
    ],
    "clash": [
        "ytsearch1:intense dark trap confrontation beat no copyright",
        "ytsearch1:aggressive drill faceoff instrumental no copyright",
        "ytsearch1:heavy bass sigma clash phonk instrumental no copyright",
        "ytsearch1:epic dark suspense drop beat no copyright",
    ],
    "funny": [
        "ytsearch1:upbeat quirky comedy meme background beat no copyright",
        "ytsearch1:trending funny reel hip hop beat instrumental no copyright",
        "ytsearch1:playful bouncy comedy vlog beat no copyright",
        "ytsearch1:funny indian meme background music instrumental no copyright",
    ],
    "vlog": [
        "ytsearch1:warm emotional inspiring vlog piano beat no copyright",
        "ytsearch1:soulful aesthetic slowed instrumental vlog no copyright",
        "ytsearch1:modern cinematic storytelling lofi beat no copyright",
        "ytsearch1:chill lifestyle vlog groove instrumental no copyright",
    ],
    "drama": [
        "ytsearch1:cinematic suspense tension dark underscore no copyright",
        "ytsearch1:intense emotional strings tension beat no copyright",
        "ytsearch1:dark reality tv drama background beat no copyright",
        "ytsearch1:sad emotional piano slowed reverb instrumental no copyright",
    ],
    "informative": [
        "ytsearch1:clean modern documentary dark beat no copyright",
        "ytsearch1:minimal smart explainer background music no copyright",
        "ytsearch1:curious investigative podcast beat no copyright",
    ],
    "clean": [""],
}

SFX_POOLS = {
    "boom": [
        "ytsearch1:vine boom bass drop impact sound effect short",
        "ytsearch1:cinematic sub bass drop hit sfx short",
        "ytsearch1:deep phonk bass drop impact sfx",
    ],
    "laugh": [
        "ytsearch1:funny meme laugh sound effect short",
        "ytsearch1:indian funny laugh track meme sfx short",
        "ytsearch1:comedy laugh punchline sound effect short",
    ],
    "none": [""],
}

HYPE_STAMP_POOLS = {
    "aura": [
        "COLD", "ICE COLD", "UNPLAYABLE", "PURE CLASS", "GOD TIER", "BUILT DIFFERENT",
        "RESPECT", "CINEMA", "FINAL BOSS", "MAIN CHARACTER", "SILENCED", "FEARLESS",
        "PEAK FORM", "UNTOUCHABLE", "PRIME MODE", "LEVELS", "LEGEND", "ICE IN VEINS",
    ],
    "roast": [
        "ROASTED", "COOKED", "VIOLATION", "SAVAGE", "NO MERCY", "EXPOSED", "HUMBLED",
        "CHECKMATE", "BODYBAG", "GAME OVER", "CRITICAL HIT", "TOO BRUTAL", "KHATAM",
        "CAUGHT IN 4K", "OUTPLAYED", "PACKED UP", "NO RECOVERY",
    ],
    "gaming": [
        "CLUTCH", "CRACKED", "INSANE", "CLEAN", "DOMINATED", "PRO MOVE", "GOD MODE",
        "CHAOS", "SQUAD WIPE", "HACKER AIM", "HEADSHOT", "MVP", "UNREAL AIM", "DIFFED",
    ],
    "clash": [
        "COOKED", "HEATED", "NO WAY", "SAVAGE", "INTENSE", "COLD REPLY", "SHUT DOWN",
        "WAR MODE", "RAW TRUTH", "NO FILTER",
    ],
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


def _pick_unique_bgm_query(edit_type, subtype, seed):
    if subtype in ("emo_wholesome_heart_drop", "emo_brotherhood_story", "emo_moody_tribute", "emo_broken_silence", "switch_banter_aesthetic"):
        pool = BGM_POOLS["aesthetic"]
    elif subtype in ("roast_red_ribbon_drop", "roast_double_meaning"):
        pool = BGM_POOLS["roast"]
    elif subtype in ("aura_minimal_glow", "aura_skull_freeze", "aura_mindset_statement", "aura_velocity_ramp", "aura_crimson_devil", "aura_ice_cold_drop", "switch_attitude_drop"):
        pool = BGM_POOLS["aura"]
    elif subtype in ("gaming_stacked_comeback", "gaming_esports_montage", "gaming_clutch_skull"):
        pool = BGM_POOLS["gaming"]
    elif subtype in ("comedy_letterbox_classic", "comedy_letterbox_lyric", "comedy_red_ribbon", "comedy_meme_pop", "gaming_lobby_troll"):
        pool = BGM_POOLS["funny"]
    else:
        pool = BGM_POOLS.get(edit_type) or BGM_POOLS["vlog"]
    return pool[abs(int(seed)) % len(pool)]


def _pick_sfx_query(subtype, seed):
    if subtype in ("comedy_letterbox_classic", "comedy_letterbox_lyric", "comedy_red_ribbon", "comedy_meme_pop", "gaming_lobby_troll", "switch_banter_aesthetic"):
        pool = SFX_POOLS["laugh"]
        return pool[abs(int(seed)) % len(pool)], "laugh"
    if subtype in ("roast_red_ribbon_drop", "roast_double_meaning", "aura_minimal_glow", "aura_skull_freeze", "aura_velocity_ramp", "aura_crimson_devil", "aura_ice_cold_drop", "gaming_stacked_comeback", "gaming_clutch_skull", "switch_attitude_drop"):
        pool = SFX_POOLS["boom"]
        return pool[abs(int(seed)) % len(pool)], "boom"
    return "", "none"


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
        Listen to this entire audio and find ALL genuine 9/10 or 10/10 VIRAL INSTAGRAM REELS moments (14-26s each, score 86-100).
        {user_rule}
        Video Title: "{audience_signals.get('video_title', '')}"
        YouTube Most-Replayed Spikes (sec): {audience_signals.get('heatmap_spikes', [])}
        Style Preference: "{style_pref}" (if "auto", choose exact natural style + exact IG sub-type!).
        Available edit_subtype values: {json.dumps(ALL_SUBTYPES)}
        REJECT intros, sponsor ads, setup filler, and outros!

        Return ONLY valid JSON array:
        [{{"start": 42, "end": 62, "score": 92, "edit_type": "roast", "edit_subtype": "roast_red_ribbon_drop", "layout_mode": "vertical_full", "title_text": "ALWAYS READY TO ROAST THEM", "impact_stamp": "COOKED", "overlay_emoji": "skull", "peak_sec": 12}}]
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

        lang_arg = "en" if caption_lang == "en" else "hi"
        segments, info = model.transcribe(
            audio_path,
            language=lang_arg,
            word_timestamps=(not fast_scan),
            vad_filter=False,
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
                    "write Hindi words in crisp Roman Hindi (e.g. 'क्या'->'Kya', 'बात'->'baat', 'भाई'->'bhai'), "
                    "and write English words spelled in Hindi back into real English (e.g. 'आई'->'I', 'नीड'->'need', 'हेल्प'->'help'). "
                    "DO NOT translate Hindi sentences into English!"
                )

            prompt = f"""
            You are an expert Indian Hinglish caption formatter. {lang_rule}
            Video Topic Hint: "{context_hint}"
            CRITICAL: Return ONLY a valid JSON array of strings of the EXACT SAME LENGTH ({len(chunk)} items).
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
        print(f"[MAG73 Captions] Formatted {len(words)} words accurately.")
    except Exception as e:
        print(f"[MAG73 Captions] Format warning: {e}")
    return words


def extract_accurate_transcript(media_path="source_video.mp4", caption_lang="hinglish", is_audio_only=False, context_hint="", fast_scan=False):
    audio_path = "temp_vocal_16k.mp3"
    bitrate = "24k" if fast_scan else "64k"
    try:
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

    dur_check = _get_media_duration_sec(audio_path)
    if (not fast_scan) and len(words) < 12 and dur_check <= 45.0:
        g_txt, g_words = _gemini_transcribe_clip_audio(audio_path, caption_lang=caption_lang)
        if len(g_words) > len(words):
            words = g_words
            text = g_txt

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
    Runs on the 0.000s trimmed clip to lock in:
    - Exact IG Reel Sub-Type (`edit_subtype`) matching the TRUE dialogue vibe
    - Persistent Instagram Story Hook (`title_text`, 3-8 words like "QAZI IS ALWAYS READY TO ROAST THEM")
    - Exact climax drop second (`peak_sec`)
    - Matching Reaction Emoji PNG (`overlay_emoji`) + Contextual Impact Stamp
    """
    plugin_cfg = _get_plugin_config()
    banner_on = bool(plugin_cfg.get("banner_enabled", True))
    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    edit_type = str(clip_data.get("edit_type", "vlog")).lower()
    subtype = str(clip_data.get("edit_subtype", "")).strip().lower()
    dur = max(10.0, float(clip_data.get("end", 20.0)) - float(clip_data.get("start", 0.0)))
    run_num = int(os.getenv("GITHUB_RUN_NUMBER", "1") or "1")
    seed = run_num + int(clip_data.get("orig_start", 0)) + int(clip_data.get("clip_index", 0)) * 7

    if not banner_on or edit_type == "clean":
        clip_data["title_text"] = ""

    seg_txt = (segment_transcript or "").strip()
    if len(seg_txt) >= 12:
        try:
            allowed_subtypes = SUBTYPES_BY_STYLE.get(style_pref, ALL_SUBTYPES) if (style_pref in VALID_STYLES and style_pref != "auto") else ALL_SUBTYPES
            prompt = f"""
            You are a VIRAL INSTAGRAM REELS EDITOR. Analyze this EXACT 0.0s-to-{dur:.1f}s clip transcript and return ONLY a JSON object:
            - "edit_type": One of ["roast", "aura", "aesthetic", "funny", "gaming", "vlog", "drama", "clash", "informative", "clean"].
              CRITICAL: Emotional/charity/respect/brotherhood/storytelling -> "aesthetic" or "vlog" (NEVER "roast"/"aura"!).
              Funny banter/reality comedy/trolling -> "funny". Savage comeback/cold badass line -> "roast" or "aura".
            - "edit_subtype": Pick the EXACT best Instagram Reel template from: {json.dumps(allowed_subtypes)}
            - "title_text": Authentic Instagram Reel narrative hook (3-7 ASCII words, UPPERCASE or Title Case feel, strictly describing THIS clip! Examples: "ALWAYS READY TO ROAST THEM", "EVEN AFTER FIGHTING HE STOOD BY HIM", "ONLY LEGENDS UNDERSTAND THIS CONVO", "HE TALKED ABOUT HIS WIFE", "WAIT FOR THE END").
            - "peak_sec": Exact float second between {max(4.0, dur*0.35):.1f} and {max(5.5, dur-2.8):.1f} where the punchline/roast/drop/emotional close-up hits.
            - "overlay_emoji": Choose ONE from ["skull", "heart", "cold", "fire", "laugh", "crown", "eyes", "broken_heart", "mindblown", "none"] matching the exact mood!
            - "impact_stamp": Crisp 1-2 word UPPERCASE stamp ONLY for roast/aura/gaming/clash (e.g. "COOKED", "ICE COLD", "CLUTCH", "UNPLAYABLE"), else "".

            Video Title: "{clip_data.get('video_title', '')}"
            User Style Override: "{style_pref}"
            Current Draft Subtype: "{subtype}"
            Exact Clip Transcript:
            {seg_txt[:1800]}

            Return ONLY valid JSON:
            {{"edit_type": "roast", "edit_subtype": "roast_red_ribbon_drop", "title_text": "ALWAYS READY TO ROAST THEM", "peak_sec": 12.4, "overlay_emoji": "skull", "impact_stamp": "COOKED"}}
            """
            raw = (_call_groq(prompt, temperature=0.25) or "").strip()
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
                if isinstance(parsed, dict):
                    ai_et = str(parsed.get("edit_type", "")).strip().lower()
                    if style_pref == "auto" and ai_et in VALID_STYLES:
                        edit_type = ai_et
                        clip_data["edit_type"] = edit_type

                    ai_sub = str(parsed.get("edit_subtype", "")).strip().lower()
                    if ai_sub in allowed_subtypes:
                        subtype = ai_sub
                        clip_data["edit_subtype"] = subtype

                    if banner_on and edit_type != "clean":
                        t = re.sub(r"[^A-Za-z0-9 !?@#.,-]", "", str(parsed.get("title_text", ""))).strip().upper()
                        if 2 <= len(t.split()) <= 9:
                            clip_data["title_text"] = t

                    pk = float(parsed.get("peak_sec", 0))
                    if 3.5 <= pk <= dur - 2.2:
                        clip_data["peak_sec"] = round(pk, 2)

                    em = str(parsed.get("overlay_emoji", "")).strip().lower()
                    if em in ("skull", "heart", "cold", "fire", "laugh", "crown", "eyes", "broken_heart", "mindblown", "none"):
                        clip_data["overlay_emoji"] = em

                    st = re.sub(r"[^A-Za-z0-9 !?+-]", "", str(parsed.get("impact_stamp", ""))).strip().upper()
                    if edit_type in HYPE_STAMP_POOLS and st and "1000" not in st and len(st.split()) <= 2:
                        clip_data["impact_stamp"] = st
                    else:
                        clip_data["impact_stamp"] = ""
        except Exception as e:
            print(f"[MAG73 Meta] Refine warning: {e}")

    # Guarantee valid subtype + matched BGM/SFX/Emoji
    if subtype not in ALL_SUBTYPES:
        pool_sub = SUBTYPES_BY_STYLE.get(edit_type, SUBTYPES_BY_STYLE["vlog"])
        subtype = pool_sub[seed % len(pool_sub)]
        clip_data["edit_subtype"] = subtype

    if not clip_data.get("overlay_emoji"):
        clip_data["overlay_emoji"] = DEFAULT_EMOJI_BY_SUBTYPE.get(subtype, "none")

    if bool(plugin_cfg.get("bgm_enabled", True)) and edit_type != "clean":
        clip_data["bgm_query"] = _pick_unique_bgm_query(edit_type, subtype, seed)
    else:
        clip_data["bgm_query"] = ""

    if bool(plugin_cfg.get("sfx_enabled", True)) and edit_type != "clean":
        sfx_q, sfx_kind = _pick_sfx_query(subtype, seed)
        clip_data["sfx_query"] = sfx_q
        clip_data["sfx_kind"] = sfx_kind
    else:
        clip_data["sfx_query"] = ""
        clip_data["sfx_kind"] = "none"

    if edit_type not in HYPE_STAMP_POOLS or subtype.startswith("emo_") or subtype.startswith("comedy_"):
        clip_data["impact_stamp"] = ""
    else:
        cur_stamp = str(clip_data.get("impact_stamp", "")).strip().upper()
        if not cur_stamp or "1000" in cur_stamp:
            pool = HYPE_STAMP_POOLS[edit_type]
            clip_data["impact_stamp"] = pool[seed % len(pool)]

    print(
        f"[MAG73 IG Director] Style={edit_type} | Subtype={subtype} | Emoji={clip_data.get('overlay_emoji')} | "
        f"Hook='{clip_data.get('title_text','')}' | Peak={clip_data.get('peak_sec')}s | Stamp='{clip_data.get('impact_stamp','')}'"
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
        e = min(max_dur, float(c.get("end", s + 19)))
        if e - s < 12.0:
            e = min(max_dur, s + 18.0)
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
                "title_text": "" if not banner_enabled else "WAIT FOR THE END",
                "peak_sec": int(min(12.0, max(5.0, end_s * 0.6))),
            }
        ]

    # Distribute DIFFERENT sub-types across every clip so NO two clips look alike!
    style_counters = {}
    used_subtypes = set()
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
        mix_seed = run_seed + idx * 5 + count_for_style * 3

        pool_sub = SUBTYPES_BY_STYLE.get(et, SUBTYPES_BY_STYLE["vlog"])
        proposed_sub = str(c.get("edit_subtype", "")).strip().lower()
        if proposed_sub not in pool_sub or proposed_sub in used_subtypes:
            # Pick an unused sub-type from this category's pool for 100% variety!
            unused = [s for s in pool_sub if s not in used_subtypes]
            proposed_sub = unused[mix_seed % len(unused)] if unused else pool_sub[mix_seed % len(pool_sub)]
        c["edit_subtype"] = proposed_sub
        used_subtypes.add(proposed_sub)

        c["variant_id"] = mix_seed % 5
        c["caption_style"] = CAPTION_STYLES[mix_seed % len(CAPTION_STYLES)]
        if not c.get("overlay_emoji"):
            c["overlay_emoji"] = DEFAULT_EMOJI_BY_SUBTYPE.get(proposed_sub, "none")

        if bgm_enabled and et != "clean":
            c["bgm_query"] = _pick_unique_bgm_query(et, proposed_sub, mix_seed)
        else:
            c["bgm_query"] = ""

        if sfx_enabled and et != "clean":
            sfx_q, sfx_kind = _pick_sfx_query(proposed_sub, mix_seed)
            c["sfx_query"] = sfx_q
            c["sfx_kind"] = sfx_kind
        else:
            c["sfx_query"] = ""
            c["sfx_kind"] = "none"

        if not banner_enabled:
            c["title_text"] = ""
        elif not str(c.get("title_text", "")).strip() and et != "clean":
            c["title_text"] = "WAIT FOR THIS MOMENT"

        if et in HYPE_STAMP_POOLS and not proposed_sub.startswith(("emo_", "comedy_")):
            st = str(c.get("impact_stamp", "")).strip().upper()
            if not st or "1000" in st:
                pool = HYPE_STAMP_POOLS[et]
                c["impact_stamp"] = pool[mix_seed % len(pool)]
        else:
            c["impact_stamp"] = ""

    print(
        f"[MAG73 IG Director] Approved {len(clips)} diverse IG Reels: "
        f"{[(c['edit_type'], c['edit_subtype'], c['overlay_emoji']) for c in clips]}"
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
        for idx, sp in enumerate(audience_signals["heatmap_spikes"][:6]):
            st = max(0, int(sp) - 5)
            en = min(int(vid_dur), st + 22)
            hm_clips.append({
                "start": st, "end": en, "score": 90,
                "edit_type": "aura" if idx % 2 == 0 else "funny",
                "layout_mode": "vertical_full",
                "focus_x": "center", "title_text": "MOST REPLAYED MOMENT",
                "peak_sec": 12,
            })
        return _finalize_clip_list(hm_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title, is_live=False)

    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION (OBEY STRICTLY): {custom_prompt}\n" if custom_prompt else ""

    prompt = f"""
    You are a TOP VIRAL INSTAGRAM REELS CREATOR & CURATOR (10M+ views standard).
    {user_rule}
    Video Title: "{video_title}"
    Video Duration: {int(vid_dur)} seconds
    User Style Preference: "{style_pref}" (if "auto", mix natural distinct IG Reel styles!)

    AUDIENCE VIRAL SIGNALS:
    - YouTube Most-Replayed Heatmap Spikes (sec): {audience_signals.get('heatmap_spikes', [])}

    TIMESTAMPED TRANSCRIPT ([Xs] seconds):
    {transcript_text[:22000]}

    STRICT RULES:
    1. Pick ALL genuine 9/10 or 10/10 VIRAL MOMENTS across the ENTIRE video (14-25s each, score 85-100).
    2. HARD REJECT: sponsor ad reads, promo codes, intros, setup filler, and outros ("like subscribe bye").
    3. ASSIGN DISTINCT INSTAGRAM REEL SUB-TYPES ("edit_subtype") FROM THIS LIST:
       - Roast/Aura: "roast_red_ribbon_drop", "roast_double_meaning", "aura_minimal_glow", "aura_skull_freeze", "aura_mindset_statement", "aura_velocity_ramp", "aura_crimson_devil", "aura_ice_cold_drop"
       - Emotional/Vlog: "emo_brotherhood_story", "emo_wholesome_heart_drop", "emo_moody_tribute", "emo_broken_silence"
       - Comedy/Meme: "comedy_letterbox_classic", "comedy_letterbox_lyric", "comedy_red_ribbon", "comedy_meme_pop"
       - Gaming/Esports: "gaming_stacked_comeback", "gaming_esports_montage", "gaming_clutch_skull", "gaming_lobby_troll"
       - Switch: "switch_banter_aesthetic", "switch_attitude_drop"
    4. EXACT PERSISTENT IG HOOK ("title_text"): 3-7 uppercase ASCII words that frame the story (e.g. "ALWAYS READY TO ROAST THEM", "EVEN AFTER FIGHTING HE STOOD BY HIM").
    5. "overlay_emoji": Pick one of ["skull", "heart", "cold", "fire", "laugh", "crown", "eyes", "broken_heart", "mindblown", "none"].

    Return ONLY valid JSON array:
    [
      {{
        "start": 42,
        "end": 62,
        "score": 93,
        "edit_type": "roast",
        "edit_subtype": "roast_red_ribbon_drop",
        "layout_mode": "vertical_full",
        "focus_x": "center",
        "title_text": "ALWAYS READY TO ROAST THEM",
        "impact_stamp": "COOKED",
        "overlay_emoji": "skull",
        "peak_sec": 12
      }}
    ]
    """
    raw_out = _call_groq(prompt, temperature=0.25)
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
    You are an ELITE VIRAL STREAM CLIPPER & INSTAGRAM REELS DIRECTOR.
    {user_rule}
    Stream Title: "{video_title}"
    Captured Segment Duration: {int(vid_dur)}s
    Style Preference: "{style_pref}"

    Transcript:
    {transcript_text[:10000]}

    Pick the SINGLE best punchiest 14-24s highlight inside this captured live segment.
    Return ONLY valid JSON array of 1 item with "start", "end", "score" (88), "edit_type", "edit_subtype" (from {json.dumps(ALL_SUBTYPES)}), "layout_mode", "title_text" (3-6 uppercase ASCII words), "overlay_emoji", "impact_stamp", and "peak_sec".
    """
    raw_out = _call_groq(prompt, temperature=0.28)
    raw_clips = _clean_json(raw_out)
    clips = _finalize_clip_list(raw_clips, vid_dur, word_timestamps, style_pref, plugin_cfg, video_title=video_title, is_live=True)
    return clips, word_timestamps
