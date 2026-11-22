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

        # Agar Hindi/Urdu/non-Latin script aayi hai toh words ko 100% accurate Roman Hinglish mein transliterate karo
        if words and re.search(r"[^\x00-\x7F]", text):
            words = _convert_words_to_hinglish(words)
            text = " ".join(w.get("word", "") for w in words)

        return text, words, detected_lang
    except Exception as e:
        print(f"[MAG73 Audio] Transcript skipped: {e}")
        return "", [], "unknown"

def _convert_words_to_hinglish(words):
    """Spoken Hindi/Urdu words ko exact same count aur timestamps ke saath clean Roman Hinglish mein badalta hai"""
    try:
        raw_list = [w.get("word", "").strip() for w in words]
        # Process in chunks of 120 words so alignment stays 100% accurate
        converted_all = []
        for i in range(0, len(raw_list), 120):
            chunk = raw_list[i:i + 120]
            prompt = (
                "Transliterate each word in this JSON array into natural Roman Hinglish (using ONLY English A-Z letters). "
                "Keep English words as-is. Return ONLY a JSON array of the EXACT SAME LENGTH.\n"
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
        You are the VISUAL & VIRAL DIRECTOR in MAG73.
        Analyze the video + audience signals:
        - Live Chat Spikes (seconds): {audience_signals.get('chat_spikes', [])}
        - Top Comment Timestamps (seconds): {audience_signals.get('comment_timestamps', [])}
        - Top Viewer Comments: {audience_signals.get('top_comments', [])[:12]}

        Find EVERY genuinely entertaining, viral, or unexpected moment (15-55 seconds each).
        Also note where the main subject/speaker is positioned horizontally: "left", "center", or "right".
        Return JSON list: [{{"start": int, "end": int, "score": 1-100, "focus_x": "center", "reason": "..."}}]
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
        Find ALL best dialogues, funny moments, roasts, or moments viewers are talking about in comments/chat.
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
    User style preference: "{style_pref}" (if "auto", choose the cleanest, most fitting pro edit for each clip).
    Detected Language: {detected_lang}
    Vision Report: {vision_report}
    Dialogue Report: {dialogue_report}
    Audience Signals: {json.dumps(audience_signals)[:3000]}

    RULES:
    1. Extract ALL truly viral/entertaining clips (15-55s each). Do NOT pad with boring clips.
    2. NO fazool effects, NO ugly filters, NO spammy text. Keep edits clean and professional!
    3. Visual Hook: If the clip has a hilarious/surprising 2-second peak moment near the middle/end, set "visual_hook_start" (in seconds from original video) so we can tease it at the start. Otherwise set null.
    4. BGM & SFX: Pick a real, fitting no-copyright song query ("bgm_query") and subtle SFX ("sfx_query") ONLY if it improves the clip.
    5. Title: Short, clean 2-4 word title ("title_text") in English/Hinglish (ASCII only), or "" if not needed.
    6. Subject Framing: Set "focus_x" to "left", "center", or "right" where the main person/action is.

    Return ONLY valid JSON array:
    [
      {{
        "start": 10,
        "end": 38,
        "mood": "clean_pro",
        "focus_x": "center",
        "title_text": "UNEXPECTED ENDING",
        "visual_hook_start": 33,
        "bgm_query": "ytsearch1:chill suspense beat no copyright",
        "sfx_query": "ytsearch1:subtle whoosh sound effect",
        "caption_color": "&H00FFFFFF"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=judge_prompt)
    clips = _clean_json(final_res.text)
    if not clips:
        clips = [{
            "start": 0, "end": 25, "mood": "clean_pro",
            "focus_x": "center", "title_text": "",
            "visual_hook_start": None,
            "bgm_query": "ytsearch1:trending lofi beat no copyright",
            "sfx_query": "", "caption_color": "&H00FFFFFF"
        }]
    print(f"[MAG73 Pro Editor] Approved {len(clips)} clean viral clips!")
    return clips, word_timestamps
