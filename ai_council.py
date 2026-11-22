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
    """Whisper language='hi' ke saath exact Hindi/Hinglish word timestamps nikaalta hai"""
    if not GROQ_KEY:
        return "", [], "hi"
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
                    "language": "hi",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word",
                    "prompt": "Ye ek Indian Hindi aur Hinglish video hai. Exact bole gaye shabd likho."
                },
                timeout=120
            )
        if res.status_code != 200:
            return "", [], "hi"

        data = res.json()
        words = data.get("words", [])
        text = data.get("text", "")
        print(f"[MAG73 Audio] Extracted {len(words)} accurate Hindi/Hinglish words.")

        if words:
            words = _convert_words_to_hinglish(words, text)
            text = " ".join(w.get("word", "") for w in words)

        return text, words, "hi"
    except Exception as e:
        print(f"[MAG73 Audio] Transcript skipped: {e}")
        return "", [], "hi"

def _convert_words_to_hinglish(words, full_context):
    """Full sentence context ke saath 100% clean Roman Hinglish mein convert karta hai"""
    try:
        raw_list = [w.get("word", "").strip() for w in words]
        converted_all = []
        for i in range(0, len(raw_list), 80):
            chunk = raw_list[i:i + 80]
            prompt = (
                "Convert each word in this JSON array into clean, accurate, natural Roman Hinglish "
                "(e.g. 'चिकन' -> 'Chicken', 'सब्जी' -> 'Sabzi', 'ग्लव्स' -> 'Gloves', 'भाई' -> 'Bhai', 'क्या' -> 'Kya').\n"
                "RULES:\n"
                "1. Fix any minor spelling errors using the sentence context.\n"
                "2. Keep English words in proper English spelling (Chicken, Fresh, Gloves, Hygiene, Boneless).\n"
                "3. DO NOT translate Hindi words into English! Keep them in Roman Hindi.\n"
                "4. Return ONLY a JSON array of strings of the EXACT SAME LENGTH.\n"
                f"Context: {full_context[:500]}\n"
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
        print("[MAG73 Audio] 100% accurate Roman Hinglish captions ready!")
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
        You are an ULTRA-STRICT VIRAL REELS DIRECTOR in MAG73.
        Analyze the video + audience signals:
        - Live Chat Spikes (seconds): {audience_signals.get('chat_spikes', [])}
        - Top Comment Timestamps (seconds): {audience_signals.get('comment_timestamps', [])}
        - Top Viewer Comments: {audience_signals.get('top_comments', [])[:12]}

        STRICT RULES:
        1. ONLY pick genuinely VIRAL, SHOCKING, FUNNY, EXPOSING, or HIGH-HYPE moments (score >= 90/100).
           Skip boring/filler/normal talking parts! If there is NO 90+ banger moment, return [].
        2. COMPLETE STORY ARC: 15 to 40 seconds max. Start at the exact hook/setup and end after the punchline.
        3. REAL HUMAN FACECAM CHECK: Only set "facecam_box": [x, y, w, h] if this is a gaming/reaction stream with a real human webcam overlay. For normal vlogs/shows/exposés, ALWAYS set "facecam_box": null.

        Return JSON list:
        [{{
          "start": int,
          "end": int,
          "score": 90-100,
          "facecam_box": null,
          "focus_x": "center",
          "reason": "..."
        }}]
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
        Pick ONLY 90+/100 genuinely shocking, hilarious, exposing, or peak hype dialogue moments (15-40s).
        Skip boring parts. If nothing is 90+, return [].
        Comment Timestamps: {audience_signals.get('comment_timestamps', [])}
        Top Comments: {audience_signals.get('top_comments', [])[:10]}
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
    You are the CHIEF PRO REELS EDITOR of MAG73.
    User style preference: "{style_pref}"
    Vision Report: {vision_report}
    Dialogue Report: {dialogue_report}

    STRICT PRO RULES:
    1. ONLY approve genuinely 90+/100 banger clips (15-40s). Zero boring clips!
    2. Choose the best "edit_type":
       - "expose": Serious/exposé/storytelling -> dark suspense BGM (subtle), punchy hook title at top, NO cheesy meme SFX.
       - "aura": Epic/savage/sigma moment -> phonk BGM, B&W beat drop ("bw_drop_sec") at peak, bass drop SFX.
       - "funny": Hilarious roast/fail -> light upbeat/meme BGM, vine boom SFX ONLY at punchline.
       - "hype": Gaming clutch/action -> energetic BGM, crisp colors, NO B&W drop.
    3. HOOK TITLE ("title_text"): Always write a catchy 3-5 word viral hook in Hinglish/English (ASCII only, e.g. "ROTTEN MEAT EXPOSED!", "GLOVES KYUN NAHI PEHNE?").
    4. BGM: Always pick a clean, fitting no-copyright BGM query ("bgm_query") matching the clip's vibe.
    5. SFX: Only set "sfx_query" if there is a real punchline/beat drop (otherwise "").

    Return ONLY valid JSON array:
    [
      {{
        "start": 10,
        "end": 35,
        "score": 93,
        "edit_type": "expose",
        "facecam_box": null,
        "focus_x": "center",
        "title_text": "REALITY EXPOSED!",
        "bw_drop_sec": null,
        "bgm_query": "ytsearch1:dark suspense documentary background music no copyright",
        "sfx_query": "",
        "caption_color": "&H00FFFFFF"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=judge_prompt)
    raw_clips = _clean_json(final_res.text)

    clips = [c for c in raw_clips if int(c.get("score", 0)) >= 90]
    print(f"[MAG73 Pro Editor] Approved {len(clips)} genuine 90+ banger clip(s)!")
    return clips, word_timestamps
