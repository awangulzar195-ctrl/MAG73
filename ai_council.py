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

gemini_client = genai.Client(api_key=GEMINI_KEY)

def extract_accurate_transcript(video_path="source_video.mp4"):
    """Voice ki asli language detect karke accurate word-level timestamps nikaalta hai"""
    if not GROQ_KEY:
        return "", [], "unknown"
    try:
        subprocess.run([
            "ffmpeg", "-y", "-i", video_path,
            "-vn", "-acodec", "libmp3lame", "-q:a", "4", "temp_audio.mp3"
        ], check=True)

        with open("temp_audio.mp3", "rb") as f:
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {GROQ_KEY}"},
                files={"file": f},
                data={
                    "model": "whisper-large-v3-turbo",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word"
                },
                timeout=120
            )
        if res.status_code != 200:
            return "", [], "unknown"

        data = res.json()
        text = data.get("text", "")
        words = data.get("words", [])
        detected_lang = data.get("language", "unknown")
        print(f"[MAG73 Audio] Detected Language: {detected_lang} | Words: {len(words)}")

        # Hindi/Urdu ya koi bhi non-English script ko 100% accurate Roman Hinglish mein badlo
        if words and (detected_lang in ("hi", "ur", "hindi", "urdu") or re.search(r"[^\x00-\x7F]", text)):
            words = _convert_words_to_hinglish(words)
            text = " ".join(w.get("word", "") for w in words)

        return text, words, detected_lang
    except Exception as e:
        print(f"[MAG73 Audio] Transcript skipped: {e}")
        return "", [], "unknown"

def _convert_words_to_hinglish(words):
    try:
        raw_list = [w.get("word", "").strip() for w in words]
        converted_all = []
        for i in range(0, len(raw_list), 100):
            chunk = raw_list[i:i + 100]
            prompt = (
                "Transliterate each word in this JSON array into natural, casual Roman Hinglish "
                "(e.g. 'भाई' -> 'Bhai', 'क्या' -> 'kya', 'हो' -> 'ho'). Use ONLY English A-Z letters. "
                "Keep English words unchanged. Return ONLY a JSON array of the EXACT SAME LENGTH.\n"
                f"Input: {json.dumps(chunk, ensure_ascii=False)}"
            )
            res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            match = re.search(r"\[.*\]", res.text, re.DOTALL)
            if match:
                out_chunk = json.loads(match.group(0))
                if len(out_chunk) == len(chunk):
                    converted_all.extend(out_chunk)
                    continue
            converted_all.extend(chunk)

        for idx, w in enumerate(words):
            if idx < len(converted_all):
                w["word"] = str(converted_all[idx])
        print("[MAG73 Audio] Converted captions to 100% accurate Roman Hinglish!")
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

def _expert_gemini_vision(video_file, transcript_text, audience_signals):
    try:
        prompt = f"""
        You are the STRICT VIRAL DIRECTOR in MAG73.
        Analyze the video + audience signals:
        - Live Chat Spikes (seconds): {audience_signals.get('chat_spikes', [])}
        - Top Comment Timestamps (seconds): {audience_signals.get('comment_timestamps', [])}
        - Top Viewer Comments: {audience_signals.get('top_comments', [])[:12]}

        CRITICAL RULE: Do NOT chop the entire video into clips!
        Pick ONLY the truly PEAK, HYPE, HILARIOUS, or UNEXPECTED moments (score >= 85/100).
        Skip all normal talking, waiting, or average parts.
        Also note where the main subject is horizontally: "left", "center", or "right".
        Return JSON list: [{{"start": int, "end": int, "score": 85-100, "focus_x": "center", "reason": "..."}}]
        Transcript: {transcript_text[:10000]}
        """
        res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=[video_file, prompt])
        return res.text
    except Exception:
        return "[]"

def _expert_groq_dialogue(transcript_text, audience_signals):
    if not GROQ_KEY or not transcript_text:
        return "[]"
    try:
        prompt = f"""
        Pick ONLY the absolute PEAK hype/funny/shocking dialogue moments (score >= 85/100).
        Do NOT include average parts of the video.
        Comment Timestamps: {audience_signals.get('comment_timestamps', [])}
        Top Comments: {audience_signals.get('top_comments', [])[:10]}
        Chat Spikes: {audience_signals.get('chat_spikes', [])}
        Transcript: {transcript_text[:14000]}
        Return JSON list with start, end, score, reason.
        """
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={"model": "llama-3.3-70b-versatile", "messages": [{"role": "user", "content": prompt}]},
            timeout=60
        ).json()
        return res["choices"][0]["message"]["content"]
    except Exception:
        return "[]"

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

    transcript_text, word_timestamps, detected_lang = extract_accurate_transcript(video_path)
    uploaded_file = gemini_client.files.upload(file=video_path)
    video_file = _wait_for_gemini_file(uploaded_file)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(_expert_gemini_vision, video_file, transcript_text, audience_signals)
        f2 = executor.submit(_expert_groq_dialogue, transcript_text, audience_signals)
        vision_report = f1.result()
        dialogue_report = f2.result()

    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()

    judge_prompt = f"""
    You are the CHIEF PRO VIDEO EDITOR of MAG73.
    User style preference: "{style_pref}"
    Detected Language: {detected_lang}
    Vision Report: {vision_report}
    Dialogue Report: {dialogue_report}
    Audience Signals: {json.dumps(audience_signals)[:3000]}

    STRICT RULES:
    1. ONLY select genuinely PEAK hype/viral moments (score >= 85). NEVER chop the whole video into 10 clips!
       If a video only has 1 or 2 real hype moments, return ONLY 1 or 2. If it has 4 real bangers, return 4.
    2. Each clip must be 15 to 50 seconds, tightly cut with zero boring dead air.
    3. Visual Hook: If the clip has a hilarious/surprising 4-second peak near the end, set "visual_hook_start" (seconds). Otherwise null.
    4. BGM & SFX: Always pick a great, fitting no-copyright BGM query ("bgm_query") matching the clip's energy (e.g. "ytsearch1:dark phonk beat no copyright", "ytsearch1:funny upbeat background music no copyright", "ytsearch1:intense suspense music no copyright").
    5. Title: Short punchy 2-4 word title ("title_text") in English/Hinglish (ASCII only), or "" if not needed.
    6. Subject Framing: Set "focus_x" to "left", "center", or "right".

    Return ONLY valid JSON array:
    [
      {{
        "start": 10,
        "end": 35,
        "score": 92,
        "mood": "hype_pro",
        "focus_x": "center",
        "title_text": "POWER GAYA BHAI",
        "visual_hook_start": 31,
        "bgm_query": "ytsearch1:suspense dark beat no copyright",
        "sfx_query": "ytsearch1:vine boom sound effect",
        "caption_color": "&H0000FFFF"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=judge_prompt)
    raw_clips = _clean_json(final_res.text)

    # Hard filter: sirf score >= 85 wale hype clips rakho
    clips = [c for c in raw_clips if int(c.get("score", 90)) >= 85]
    if not clips and raw_clips:
        clips = [max(raw_clips, key=lambda x: int(x.get("score", 0)))]
    if not clips:
        clips = [{
            "start": 0, "end": 25, "score": 88, "mood": "hype_pro",
            "focus_x": "center", "title_text": "",
            "visual_hook_start": None,
            "bgm_query": "ytsearch1:trending phonk beat no copyright",
            "sfx_query": "", "caption_color": "&H0000FFFF"
        }]

    print(f"[MAG73 Pro Editor] Approved ONLY {len(clips)} peak hype clip(s)!")
    return clips, word_timestamps
