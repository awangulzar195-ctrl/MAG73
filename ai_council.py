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


def _call_groq(prompt, temperature=0.25):
    """Fast, 14,400 req/day free Groq Llama-3.3-70B engine"""
    if not GROQ_KEY:
        return ""
    try:
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "temperature": temperature,
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        )
        if res.status_code == 200:
            return res.json()["choices"][0]["message"]["content"]
        print(f"[MAG73 Groq] HTTP {res.status_code}: {res.text[:150]}")
    except Exception as e:
        print(f"[MAG73 Groq] Error: {e}")
    return ""


def _build_timestamped_transcript(words):
    """Groq aur Gemini ke liye exact [12s] timestamped transcript banata hai"""
    if not words:
        return ""
    lines = []
    bucket_start = int(words[0].get("start", 0))
    curr = []
    for w in words:
        ws = int(w.get("start", 0))
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


def extract_accurate_transcript(video_path="source_video.mp4"):
    """Whisper language='hi' + Groq Roman Hinglish + exact timestamps"""
    if not GROQ_KEY:
        return "", [], "hi"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "4", "temp_audio.mp3"
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        with open("temp_audio.mp3", "rb") as f:
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": f},
                data={
                    "model": "whisper-large-v3-turbo",
                    "language": "hi",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word"
                },
                timeout=120
            )
        if res.status_code != 200:
            return "", [], "hi"

        data = res.json()
        words = data.get("words", [])
        text = data.get("text", "")
        print(f"[MAG73 Audio] Extracted {len(words)} words.")

        if words:
            words = _convert_words_to_hinglish_groq(words, text)
            ts_text = _build_timestamped_transcript(words)
            return ts_text, words, "hi"

        return text, words, "hi"
    except Exception as e:
        print(f"[MAG73 Audio] Transcript skipped: {e}")
        return "", [], "hi"


def _convert_words_to_hinglish_groq(words, full_context):
    """Groq se 100% accurate Roman Hinglish conversion"""
    try:
        raw_list = [w.get("word", "").strip() for w in words]
        converted_all = []
        for i in range(0, len(raw_list), 70):
            chunk = raw_list[i:i + 70]
            prompt = (
                "Transliterate each word in this JSON array into clean, natural Roman Hinglish "
                "(e.g. 'भाई' -> 'Bhai', 'चिकन' -> 'Chicken', 'मार' -> 'Maar', 'क्या' -> 'Kya').\n"
                "RULES:\n"
                "1. Keep English words in proper English spelling.\n"
                "2. DO NOT translate Hindi words into English! Write Hindi words in Roman letters (A-Z).\n"
                "3. Return ONLY a valid JSON array of strings with the EXACT SAME LENGTH.\n"
                f"Context: {full_context[:350]}\n"
                f"Input: {json.dumps(chunk, ensure_ascii=False)}"
            )
            out = _call_groq(prompt, temperature=0.1)
            match = re.search(r"\[.*\]", out, re.DOTALL)
            if match:
                out_chunk = json.loads(match.group(0))
                if len(out_chunk) == len(chunk):
                    converted_all.extend(out_chunk)
                    continue
            converted_all.extend(chunk)

        for idx, w in enumerate(words):
            if idx < len(converted_all):
                w["word"] = str(converted_all[idx])
        print("[MAG73 Audio] Converted captions to 100% accurate Roman Hinglish via Groq!")
    except Exception as e:
        print(f"[MAG73 Audio] Hinglish conversion warning: {e}")
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


def _expert_gemini_vision(video_path, transcript_text, audience_signals):
    """Sirf 1 Gemini call per video + automatic model fallback"""
    if not gemini_client:
        return "[]"
    try:
        uploaded_file = gemini_client.files.upload(file=video_path)
        video_file = _wait_for_gemini_file(uploaded_file)

        prompt = f"""
        You are a PRO VIRAL REELS DIRECTOR.
        Analyze the video + audience signals:
        - Live Chat Spikes (sec): {audience_signals.get('chat_spikes', [])}
        - Top Comment Timestamps (sec): {audience_signals.get('comment_timestamps', [])}

        RULES:
        1. Pick the TOP 1 to 3 best, complete viral/funny/clutch/exposing moments (15-38s, score 80-100).
        2. REAL HUMAN FACECAM CHECK: ONLY set "facecam_box": [x, y, w, h] if a REAL HUMAN PERSON is clearly visible in a webcam overlay (never minimap/HUD). Otherwise null.
        3. Identify "peak_sec" (seconds from clip start where the kill/punchline/drop hits).

        Return JSON list:
        [{{"start": int, "end": int, "score": 80-100, "peak_sec": int, "facecam_box": null, "focus_x": "center", "reason": "..."}}]
        Timestamped Transcript:
        {transcript_text[:8000]}
        """
        for model_name in ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite"):
            try:
                res = gemini_client.models.generate_content(model=model_name, contents=[video_file, prompt])
                print(f"[MAG73 Vision] Analyzed via {model_name}")
                return res.text
            except Exception as e:
                print(f"[MAG73 Vision] {model_name} skipped ({str(e)[:80]}), trying next...")
    except Exception as e:
        print(f"[MAG73 Vision] Fallback to Groq-only mode: {e}")
    return "[]"


def _expert_groq_dialogue(transcript_text, audience_signals):
    if not transcript_text:
        return "[]"
    prompt = f"""
    You are a viral short-form video director.
    Read this TIMESTAMPED transcript (each line starts with [Xs] seconds) and pick the TOP 1 to 3 most engaging, funny, shocking, or high-hype complete moments (15-38 seconds each).
    Comment Timestamps: {audience_signals.get('comment_timestamps', [])}
    Top Comments: {audience_signals.get('top_comments', [])[:10]}
    Chat Spikes: {audience_signals.get('chat_spikes', [])}

    Timestamped Transcript:
    {transcript_text[:14000]}

    Return ONLY a JSON list:
    [{{"start": 10, "end": 32, "score": 88, "peak_sec": 15, "reason": "..."}}]
    """
    return _call_groq(prompt, temperature=0.3)


def _clean_json(raw_text):
    try:
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return []


def run_super_ai_council(video_path, audience_signals):
    if isinstance(audience_signals, list):
        audience_signals = {"chat_spikes": audience_signals, "comment_timestamps": [], "top_comments": []}

    transcript_text, word_timestamps, _ = extract_accurate_transcript(video_path)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(_expert_gemini_vision, video_path, transcript_text, audience_signals)
        f2 = executor.submit(_expert_groq_dialogue, transcript_text, audience_signals)
        vision_report = f1.result()
        dialogue_report = f2.result()

    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()

    judge_prompt = f"""
    You are the CHIEF PRO REELS EDITOR of MAG73.
    User style preference: "{style_pref}"
    Vision Report: {vision_report}
    Dialogue Report: {dialogue_report}

    RULES:
    1. Approve the TOP 1 to 3 best complete moments (15-38s, score >= 80). Always pick the strongest moment(s) from the reports.
    2. Choose the best "edit_type":
       - "aura": Epic clutch / sigma / savage moment -> phonk BGM, B&W drop at "peak_sec", bass drop SFX.
       - "hype": Fast gaming action / esports -> energetic subtle BGM, crisp colors, NO B&W drop.
       - "funny": Hilarious roast / fail -> raw comedy timing (no BGM), optional vine boom SFX at "peak_sec".
       - "expose": Serious exposé / storytelling -> dark suspense subtle BGM, punchy hook title, NO SFX.
       - "clean": Pure raw viral clip -> no BGM, no SFX, no banner, just pro captions.
    3. HOOK TITLE ("title_text"): Catchy 3-5 word viral hook in Hinglish/English (ASCII only), or "" for clean.
    4. BGM & SFX: Only provide "bgm_query" / "sfx_query" when it genuinely improves the clip (otherwise "").

    Return ONLY valid JSON array:
    [
      {{
        "start": 10,
        "end": 32,
        "score": 89,
        "edit_type": "hype",
        "facecam_box": null,
        "focus_x": "center",
        "title_text": "INSANE MOMENT!",
        "peak_sec": 14,
        "bgm_query": "ytsearch1:dark phonk gaming edit instrumental no copyright",
        "sfx_query": ""
      }}
    ]
    """
    final_text = _call_groq(judge_prompt, temperature=0.2)
    raw_clips = _clean_json(final_text)

    clips = [c for c in raw_clips if int(c.get("score", 80)) >= 80]
    if not clips and raw_clips:
        clips = [max(raw_clips, key=lambda x: int(x.get("score", 0)))]

    print(f"[MAG73 Pro Editor] Approved {len(clips)} viral clip(s) via Groq Judge!")
    return clips, word_timestamps
