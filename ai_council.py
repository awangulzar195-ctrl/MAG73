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
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "gemma2-9b-it",
]

_working_groq_model = None


def _get_plugin_config():
    defaults = {
        "caption_lang": "hinglish",
        "bgm_enabled": True,
        "sfx_enabled": True,
        "banner_enabled": True,
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


def _call_groq(prompt, temperature=0.25):
    """Multi-model Groq engine with automatic fallback."""
    global _working_groq_model
    if not GROQ_KEY:
        return ""

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
            last_err = f"HTTP {res.status_code}: {res.text[:160]}"
        except Exception as e:
            last_err = str(e)

    print(f"[MAG73 Groq] All models failed ({last_err})")
    return ""


def _build_timestamped_transcript(words):
    """Creates [Xs] timestamped lines for AI analysis."""
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
    """Extracts word timestamps via Whisper and formats per caption_lang."""
    if not GROQ_KEY:
        return "", [], caption_lang
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                video_path,
                "-vn",
                "-acodec",
                "libmp3lame",
                "-q:a",
                "4",
                "temp_audio.mp3",
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        whisper_lang = "en" if caption_lang == "en" else "hi"
        with open("temp_audio.mp3", "rb") as f:
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": f},
                data={
                    "model": "whisper-large-v3-turbo",
                    "language": whisper_lang,
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                },
                timeout=120,
            )
        if res.status_code != 200:
            print(f"[MAG73 Audio] Whisper HTTP {res.status_code}")
            return "", [], caption_lang

        data = res.json()
        words = data.get("words") or []
        text = data.get("text") or ""
        print(f"[MAG73 Audio] Extracted {len(words)} words (lang={caption_lang}).")

        if words:
            if caption_lang == "hinglish":
                words = _convert_words_groq(words, text, mode="hinglish")
            elif caption_lang == "en":
                words = _convert_words_groq(words, text, mode="en")
            ts_text = _build_timestamped_transcript(words)
            return ts_text, words, caption_lang

        return text, words, caption_lang
    except Exception as e:
        print(f"[MAG73 Audio] Transcript skipped: {e}")
        return "", [], caption_lang


def _convert_words_groq(words, full_context, mode="hinglish"):
    """Converts words to clean Roman Hinglish or clean English."""
    try:
        raw_list = [str(w.get("word", "")).strip() for w in words]
        converted_all = []
        for i in range(0, len(raw_list), 70):
            chunk = raw_list[i:i + 70]
            if mode == "en":
                instruction = (
                    "Clean or translate each word in this JSON array into natural, crisp English captions (A-Z).\n"
                    "Return ONLY a JSON array of strings of the EXACT SAME LENGTH.\n"
                )
            else:
                instruction = (
                    "Transliterate each word in this JSON array into clean, natural Roman Hinglish "
                    "(e.g. 'भाई' -> 'Bhai', 'क्या' -> 'Kya', 'लड़ाई' -> 'Ladai', 'मज़ाक' -> 'Mazaak').\n"
                    "RULES:\n"
                    "1. Keep English words in proper English spelling.\n"
                    "2. Do NOT translate Hindi words into English; write them in clean Roman Hinglish (A-Z).\n"
                    "3. Return ONLY a JSON array of strings of the EXACT SAME LENGTH.\n"
                )

            prompt = (
                f"{instruction}"
                f"Context: {full_context[:350]}\n"
                f"Input: {json.dumps(chunk, ensure_ascii=False)}"
            )
            out = _call_groq(prompt, temperature=0.1)
            match = re.search(r"\[.*\]", out, re.DOTALL)
            if match:
                out_chunk = json.loads(match.group(0))
                if isinstance(out_chunk, list) and len(out_chunk) == len(chunk):
                    converted_all.extend(out_chunk)
                    continue
            converted_all.extend(chunk)

        for idx, w in enumerate(words):
            if idx < len(converted_all):
                w["word"] = str(converted_all[idx])
        print(f"[MAG73 Audio] {mode.upper()} captions ready.")
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
    """Single vision pass with safe fallback."""
    if not gemini_client:
        return "[]"
    try:
        uploaded_file = gemini_client.files.upload(file=video_path)
        video_file = _wait_for_gemini_file(uploaded_file)

        user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""

        prompt = f"""
        You are a PRO SHORT-FORM VIRAL EDITOR.
        {user_rule}
        Analyze the video + audience signals:
        - Live Chat Spikes (sec): {audience_signals.get('chat_spikes', [])}
        - Top Comment Timestamps (sec): {audience_signals.get('comment_timestamps', [])}

        RULES:
        1. Pick TOP 1 to 3 engaging, complete moments (12-32s, score 80-100).
        2. REAL HUMAN FACECAM CHECK: ONLY set "facecam_box": [x, y, w, h] (0.0-1.0) if a real human webcam overlay is clearly visible and relevant; otherwise null.
        3. Identify "peak_sec" (seconds from clip start where the main reaction/punchline/drop occurs).

        Return JSON list:
        [{{"start": int, "end": int, "score": 80-100, "peak_sec": int, "facecam_box": null, "focus_x": "center", "reason": "..."}}]
        Timestamped Transcript:
        {transcript_text[:8000]}
        """
        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"):
            try:
                res = gemini_client.models.generate_content(model=model_name, contents=[video_file, prompt])
                print(f"[MAG73 Vision] Analyzed via {model_name}")
                return res.text or "[]"
            except Exception as e:
                print(f"[MAG73 Vision] {model_name} skipped ({str(e)[:80]}), trying next...")
    except Exception as e:
        print(f"[MAG73 Vision] Fallback to transcript/Groq mode: {e}")
    return "[]"


def _expert_groq_dialogue(transcript_text, audience_signals, custom_prompt):
    if not transcript_text:
        return "[]"
    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION: {custom_prompt}\n" if custom_prompt else ""
    prompt = f"""
    {user_rule}
    Read this TIMESTAMPED transcript ([Xs] seconds) and pick TOP 1 to 3 engaging, complete moments (12-32s each).
    Include "peak_sec" (seconds from clip start where the punchline/climax happens).
    Comment Timestamps: {audience_signals.get('comment_timestamps', [])}
    Top Comments: {audience_signals.get('top_comments', [])[:10]}
    Chat Spikes: {audience_signals.get('chat_spikes', [])}

    Timestamped Transcript:
    {transcript_text[:14000]}

    Return ONLY a JSON list:
    [{{"start": 10, "end": 28, "score": 88, "peak_sec": 14, "reason": "..."}}]
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
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return max(10.0, float(out))
    except Exception:
        return 60.0


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

    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(_expert_gemini_vision, video_path, transcript_text, audience_signals, custom_prompt)
        f2 = executor.submit(_expert_groq_dialogue, transcript_text, audience_signals, custom_prompt)
        vision_report = f1.result()
        dialogue_report = f2.result()

    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()
    user_rule = f"\nHIGHEST PRIORITY USER INSTRUCTION (OBEY STRICTLY): {custom_prompt}\n" if custom_prompt else ""

    judge_prompt = f"""
    You are the CHIEF PRO SHORT-FORM EDITOR of MAG73.
    {user_rule}
    User style preference: "{style_pref}"
    Plugin Settings: BGM={'ON' if bgm_enabled else 'OFF'}, SFX={'ON' if sfx_enabled else 'OFF'}, HookBanner={'ON' if banner_enabled else 'OFF'}
    Vision Report: {vision_report}
    Dialogue Report: {dialogue_report}

    RULES:
    1. Approve TOP 1 to 3 strong complete moments (12-32s, score >= 80).
    2. Match "edit_type" to each clip's actual mood (do NOT force one style on every clip):
       - "drama": Intense argument / emotional / reality clash -> subtle dramatic grade.
       - "clash": High-energy confrontation / intense banter -> crisp contrast.
       - "funny": Hilarious roast / reaction / comic moment -> lively colors.
       - "aura": Savage/cold/sigma comeback -> moody grade, B&W shift from "peak_sec".
       - "clean": Pure raw moment with crisp captions & subtle pacing only.
    3. HOOK TITLE ("title_text"): Short 2-5 word hook (ASCII only) ONLY if HookBanner is ON, else "".
    4. BGM & SFX: Provide "bgm_query" ONLY if BGM is ON and fits the mood (else ""). Provide "sfx_query" ONLY if SFX is ON and fits a punchline (else "").

    Return ONLY valid JSON array:
    [
      {{
        "start": 5,
        "end": 23,
        "score": 88,
        "edit_type": "drama",
        "facecam_box": null,
        "focus_x": "center",
        "title_text": "BAAT YAHAN TAK AAYI!",
        "peak_sec": 9,
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

    clips = [c for c in raw_clips if isinstance(c, dict) and int(c.get("score", 80)) >= 80]
    if not clips and raw_clips:
        dict_clips = [c for c in raw_clips if isinstance(c, dict)]
        if dict_clips:
            clips = [max(dict_clips, key=lambda x: int(x.get("score", 0)))]

    if not clips:
        dur = _get_video_duration_sec(video_path)
        start_s = 0.0
        end_s = min(dur, 22.0)
        clips = [
            {
                "start": int(start_s),
                "end": int(max(8.0, end_s)),
                "score": 85,
                "edit_type": style_pref if style_pref in ("drama", "clash", "funny", "aura", "clean") else "drama",
                "facecam_box": None,
                "focus_x": "center",
                "title_text": "",
                "peak_sec": int(min(8.0, max(2.0, (end_s - start_s) * 0.5))),
                "bgm_query": "",
                "sfx_query": "",
            }
        ]

    # Strictly enforce plugin toggles
    for c in clips:
        if not bgm_enabled:
            c["bgm_query"] = ""
        if not sfx_enabled:
            c["sfx_query"] = ""
        if not banner_enabled:
            c["title_text"] = ""

    print(f"[MAG73 Pro Editor] Approved {len(clips)} clip(s).")
    return clips, word_timestamps
