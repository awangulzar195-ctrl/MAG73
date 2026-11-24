import os
import time
import json
import re
import subprocess
import concurrent.futures
import requests
from google import genai

GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GROQ_KEY = os.getenv("GROQ_API_KEY", "").strip()

gemini_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

GROQ_MODELS = [
    "llama-3.1-8b-instant",
    "llama-3.3-70b-versatile",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "gemma2-9b-it",
]

_working_groq_model = None

VALID_STYLES = ("vlog", "gaming", "clash", "funny", "aura", "drama", "informative", "clean")


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
    """Offline fallback transliterator so Hindi words never vanish if LLM fails."""
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
    """Multi-model Groq engine with automatic fallback to Gemini text."""
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
                    timeout=60,
                )
                if res.status_code == 200:
                    _working_groq_model = model_name
                    data = res.json()
                    choices = data.get("choices") or []
                    if choices:
                        return choices[0].get("message", {}).get("content", "")
                last_err = f"HTTP {res.status_code}: {res.text[:140]}"
            except Exception as e:
                last_err = str(e)
        print(f"[MAG73 Groq] Models skipped ({last_err}), trying Gemini text fallback...")

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
        if ws - bucket_start >= 6 and curr:
            lines.append(f"[{bucket_start}s] " + " ".join(curr))
            bucket_start = ws
            curr = []
        txt = str(w.get("word", "")).strip()
        if txt:
            curr.append(txt)
    if curr:
        lines.append(f"[{bucket_start}s] " + " ".join(curr))
    return "\n".join(lines)


def extract_accurate_transcript(video_path="source_video.mp4", caption_lang="hinglish"):
    """Auto-detects spoken language via Whisper so English vlogs stay English and Hindi becomes crisp Hinglish."""
    if not GROQ_KEY:
        return "", [], caption_lang
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", video_path,
                "-vn", "-acodec", "libmp3lame", "-q:a", "4", "temp_audio.mp3",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        form_data = {
            "model": "whisper-large-v3-turbo",
            "response_format": "verbose_json",
            "timestamp_granularities[]": "word",
        }
        if caption_lang == "en":
            form_data["language"] = "en"

        with open("temp_audio.mp3", "rb") as f:
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": f},
                data=form_data,
                timeout=120,
            )
        if res.status_code != 200:
            print(f"[MAG73 Audio] Whisper HTTP {res.status_code}")
            return "", [], caption_lang

        data = res.json()
        words = data.get("words") or []
        text = data.get("text") or ""
        detected_lang = str(data.get("language", "")).lower()
        print(f"[MAG73 Audio] Extracted {len(words)} words (detected={detected_lang}, target={caption_lang}).")

        if words:
            has_non_ascii = any(not str(w.get("word", "")).isascii() for w in words)
            if caption_lang == "en" and has_non_ascii:
                words = _convert_words_smart(words, text, mode="en")
            elif caption_lang == "hinglish" and has_non_ascii:
                words = _convert_words_smart(words, text, mode="hinglish")

            # Final safety guarantee: transliterate any leftover Devanagari so captions never vanish
            for w in words:
                txt = str(w.get("word", "")).strip()
                if txt and not txt.isascii():
                    w["word"] = _devanagari_to_roman(txt)

            ts_text = _build_timestamped_transcript(words)
            return ts_text, words, caption_lang

        return text, words, caption_lang
    except Exception as e:
        print(f"[MAG73 Audio] Transcript skipped: {e}")
        return "", [], caption_lang


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
                    "Convert each word in this JSON array into clean Roman Hinglish (ASCII A-Z only, e.g. 'भाई'->'Bhai', 'चाय'->'Chai').\n"
                    "Keep English words in normal English. Do NOT translate Hindi to English, write Hindi in Roman letters.\n"
                    "Return ONLY a JSON array of strings of the EXACT SAME LENGTH.\n"
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
        print(f"[MAG73 Audio] {mode.upper()} captions processed cleanly.")
    except Exception as e:
        print(f"[MAG73 Audio] Caption formatting warning: {e}")
    return words


def _wait_for_gemini_file(video_file):
    while True:
        info = gemini_client.files.get(name=video_file.name)
        state = getattr(info.state, "name", str(info.state))
        if state == "ACTIVE":
            return info
        if state == "FAILED":
            raise RuntimeError("Gemini video processing failed.")
        time.sleep(3)


def _expert_gemini_vision(video_path, transcript_text, audience_signals, custom_prompt):
    if not gemini_client:
        return "[]"
    try:
        uploaded_file = gemini_client.files.upload(file=video_path)
        video_file = _wait_for_gemini_file(uploaded_file)

        user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""

        prompt = f"""
        You are a PRO SHORT-FORM VIRAL DIRECTOR (CapCut / OpusClip level).
        {user_rule}
        Watch the ENTIRE video and identify:
        1. What genre is this video? (food/travel vlog, gaming stream, comedy/roast, podcast, reality drama, etc.)
        2. Extract ALL genuinely engaging, non-overlapping highlight moments across the ENTIRE video (14-35s each, score 82-100).
        3. DIFFERENT VIBES PER CLIP: One video can produce DIFFERENT clip styles! For each clip pick the EXACT matching "edit_type":
           - "vlog": Food tasting, street exploring, travel story, warm cinematic moment.
           - "gaming": Fast action, gunfight, clutch, gameplay hype.
           - "funny": Hilarious reaction, spicy shock, awkward laugh, roast, fail.
           - "aura": Cold savage comeback, insane clutch, epic goosebumps drop.
           - "drama": Real heated argument, intense clash, emotional tension.
           - "informative": Cool fact, price reveal, local secret, tip.
           - "clean": Pure natural moment needing only captions.
        4. NEVER label a food/travel vlog or gameplay as "drama" unless people are actually arguing!
        5. Set "peak_sec" (seconds from clip start where the reaction/taste/kill/punchline hits).
        6. Set "title_text": Catchy 3-5 word viral hook (ASCII only, e.g. "SPICY SHOCK IN KASHMIR!", "INSANE 1V4 CLUTCH!", "CHEAPEST BREAKFAST EVER?").

        Audience signals:
        - Live Chat Spikes: {audience_signals.get('chat_spikes', [])}
        - Comment Timestamps: {audience_signals.get('comment_timestamps', [])}

        Return ONLY a JSON list:
        [{{"start": int, "end": int, "score": 82-100, "edit_type": "vlog|gaming|funny|aura|drama|informative|clean", "peak_sec": int, "focus_x": "center", "title_text": "SHORT HOOK", "reason": "..."}}]

        Timestamped Transcript:
        {transcript_text[:10000]}
        """
        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"):
            try:
                res = gemini_client.models.generate_content(model=model_name, contents=[video_file, prompt])
                print(f"[MAG73 Vision] Analyzed via {model_name}")
                return res.text or "[]"
            except Exception as e:
                print(f"[MAG73 Vision] {model_name} skipped ({str(e)[:80]}), trying next...")
    except Exception as e:
        print(f"[MAG73 Vision] Fallback to transcript mode: {e}")
    return "[]"


def _expert_groq_dialogue(transcript_text, audience_signals, custom_prompt):
    if not transcript_text:
        return "[]"
    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""
    prompt = f"""
    {user_rule}
    Read this ENTIRE TIMESTAMPED transcript ([Xs] seconds) and extract ALL genuinely engaging, non-overlapping highlight moments (14-35s each, score 82-100).
    Match EACH clip's actual mood with its own "edit_type" from: "vlog", "gaming", "funny", "aura", "drama", "informative", "clean".
    NEVER call a food/travel/informative clip "drama"!
    Include "peak_sec" (seconds from clip start where the punchline/reaction hits) and a catchy 3-5 word ASCII "title_text".

    Comment Timestamps: {audience_signals.get('comment_timestamps', [])}
    Top Comments: {audience_signals.get('top_comments', [])[:10]}
    Chat Spikes: {audience_signals.get('chat_spikes', [])}

    Timestamped Transcript:
    {transcript_text[:16000]}

    Return ONLY a JSON list:
    [{{"start": 10, "end": 30, "score": 88, "edit_type": "funny", "peak_sec": 12, "title_text": "WAIT FOR HIS REACTION!", "reason": "..."}}]
    """
    return _call_groq(prompt, temperature=0.3)


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


def _get_video_duration_sec(video_path):
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", video_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return max(10.0, float(out))
    except Exception:
        return 60.0


def _deduplicate_clips(clips, max_dur):
    """Removes overlapping/duplicate clips so the same segment is never rendered twice."""
    valid = []
    for c in clips:
        if not isinstance(c, dict):
            continue
        s = max(0.0, float(c.get("start", 0)))
        e = min(max_dur, float(c.get("end", s + 20)))
        if e - s < 8.0:
            e = min(max_dur, s + 16.0)
        if e - s > 36.0:
            e = s + 34.0
        c["start"] = int(round(s))
        c["end"] = int(round(e))
        valid.append(c)

    # Prioritize highest scores, skip heavily overlapping segments
    valid.sort(key=lambda x: int(x.get("score", 80)), reverse=True)
    kept = []
    for c in valid:
        overlaps = False
        for k in kept:
            inter = min(c["end"], k["end"]) - max(c["start"], k["start"])
            min_len = max(1, min(c["end"] - c["start"], k["end"] - k["start"]))
            if inter > 0.35 * min_len or abs(c["start"] - k["start"]) < 5:
                overlaps = True
                break
        if not overlaps:
            kept.append(c)

    kept.sort(key=lambda x: x["start"])
    return kept


def run_super_ai_council(video_path, audience_signals):
    if isinstance(audience_signals, list):
        audience_signals = {"chat_spikes": audience_signals, "comment_timestamps": [], "top_comments": []}

    plugin_cfg = _get_plugin_config()
    caption_lang = str(plugin_cfg.get("caption_lang", "hinglish")).lower()
    bgm_enabled = bool(plugin_cfg.get("bgm_enabled", True))
    sfx_enabled = bool(plugin_cfg.get("sfx_enabled", True))
    banner_enabled = bool(plugin_cfg.get("banner_enabled", True))
    custom_prompt = os.getenv("CUSTOM_PROMPT", "").strip()

    print(f"[MAG73 Config] Plugin={plugin_cfg} | CustomPrompt='{custom_prompt}'")

    transcript_text, word_timestamps, _ = extract_accurate_transcript(video_path, caption_lang=caption_lang)
    vid_dur = _get_video_duration_sec(video_path)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(_expert_gemini_vision, video_path, transcript_text, audience_signals, custom_prompt)
        f2 = executor.submit(_expert_groq_dialogue, transcript_text, audience_signals, custom_prompt)
        vision_report = f1.result()
        dialogue_report = f2.result()

    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION (OBEY STRICTLY): {custom_prompt}\n" if custom_prompt else ""

    judge_prompt = f"""
    You are the CHIEF PRO SHORT-FORM DIRECTOR of MAG73.
    {user_rule}
    User style preference: "{style_pref}" (if "auto", pick the EXACT natural style for EACH individual clip!).
    Plugin Settings: BGM={'ON' if bgm_enabled else 'OFF'}, SFX={'ON' if sfx_enabled else 'OFF'}, HookBanner={'ON' if banner_enabled else 'OFF'}
    Vision Report: {vision_report}
    Dialogue Report: {dialogue_report}

    STRICT RULES:
    1. Approve ALL genuinely high-hype, non-overlapping moments (14-35s, score >= 82). Skip boring filler.
    2. VARIETY & ACCURACY: One video can have DIFFERENT clip styles! Assign each clip its true "edit_type":
       - "vlog": Food, street stall, travel, exploring, warm storytelling.
       - "gaming": Shooter/gameplay action, kills, gunfights, esports.
       - "funny": Funny reaction, spicy food shock, laugh, roast, fail.
       - "aura": Cold savage comeback, epic clutch, goosebumps beat drop.
       - "drama": Real heated argument or emotional clash ONLY.
       - "informative": Price reveal, local fact, tip, breakdown.
       - "clean": Pure raw moment with pro captions only.
    3. HOOK TITLE ("title_text"): Punchy 3-5 word ASCII hook tailored to THAT specific clip (e.g. "WAIT FOR THE SPICE!", "CHEAPEST CHAI IN KASHMIR?", "INSANE CLUTCH MOMENT!"). Empty "" only if HookBanner is OFF or style is "clean".
    4. BGM ("bgm_query"): Only if BGM is ON AND the clip genuinely needs music (e.g. "ytsearch1:dark phonk edit instrumental no copyright" for aura/gaming, "ytsearch1:chill lofi travel vlog beat no copyright" for quiet vlog; keep "" if the clip already has loud music or raw comedy!).
    5. SFX ("sfx_query"): Only if SFX is ON and there is a clear punchline/drop at "peak_sec" (e.g. "ytsearch1:vine boom sound effect" for funny, "ytsearch1:bass drop impact sfx" for aura/gaming; else "").

    Return ONLY valid JSON array:
    [
      {{
        "start": 10,
        "end": 30,
        "score": 89,
        "edit_type": "vlog",
        "focus_x": "center",
        "title_text": "HIDDEN GEM IN KASHMIR!",
        "peak_sec": 11,
        "bgm_query": "",
        "sfx_query": ""
      }}
    ]
    """
    final_text = _call_groq(judge_prompt, temperature=0.25)
    raw_clips = _clean_json(final_text)
    if not raw_clips:
        raw_clips = _clean_json(vision_report)
    if not raw_clips:
        raw_clips = _clean_json(dialogue_report)

    clips = [c for c in raw_clips if isinstance(c, dict) and int(c.get("score", 80)) >= 82]
    if not clips and raw_clips:
        dict_clips = [c for c in raw_clips if isinstance(c, dict)]
        if dict_clips:
            clips = [max(dict_clips, key=lambda x: int(x.get("score", 0)))]

    clips = _deduplicate_clips(clips, vid_dur)

    if not clips:
        end_s = min(vid_dur, 24.0)
        fallback_style = style_pref if style_pref in VALID_STYLES else "vlog"
        clips = [
            {
                "start": 0,
                "end": int(max(10.0, end_s)),
                "score": 85,
                "edit_type": fallback_style,
                "focus_x": "center",
                "title_text": "WATCH TILL THE END!" if banner_enabled else "",
                "peak_sec": int(min(10.0, max(3.0, end_s * 0.5))),
                "bgm_query": "",
                "sfx_query": "",
            }
        ]

    # Enforce user override & plugin toggles cleanly
    for c in clips:
        et = str(c.get("edit_type", "vlog")).strip().lower()
        if style_pref in VALID_STYLES and style_pref != "auto":
            et = style_pref
        elif et not in VALID_STYLES:
            et = "vlog"
        c["edit_type"] = et

        if not bgm_enabled:
            c["bgm_query"] = ""
        if not sfx_enabled:
            c["sfx_query"] = ""
        if not banner_enabled:
            c["title_text"] = ""
        elif not str(c.get("title_text", "")).strip() and et != "clean":
            c["title_text"] = "WATCH THIS MOMENT!"

    print(f"[MAG73 Pro Editor] Approved {len(clips)} unique clip(s): {[c['edit_type'] for c in clips]}")
    return clips, word_timestamps
