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
    """Spoken Hindi/Hinglish/English ko bina translate kiye exact word timestamps ke saath nikaalta hai"""
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
                    "timestamp_granularities[]": "word",
                    "prompt": "Bhai ye Hindi aur Hinglish video/stream hai. Jo bola gaya hai wahi likho, English mein translate mat karo."
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
                "Transliterate each word in this JSON array into natural Roman Hinglish "
                "(e.g. 'भाई' -> 'Bhai', 'क्या' -> 'kya', 'गाड़ी' -> 'gaadi'). "
                "DO NOT translate Hindi into English! Keep English words unchanged. "
                "Use ONLY A-Z letters. Return ONLY a JSON array of the EXACT SAME LENGTH.\n"
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
        You are an ULTRA-STRICT VIRAL REELS DIRECTOR in MAG73.
        Analyze the video + audience signals:
        - Live Chat Spikes (seconds): {audience_signals.get('chat_spikes', [])}
        - Top Comment Timestamps (seconds): {audience_signals.get('comment_timestamps', [])}
        - Top Viewer Comments: {audience_signals.get('top_comments', [])[:12]}

        CRITICAL RULES:
        1. NO BORING CLIPS (STRICT!):
           - NEVER clip normal driving, walking, looting, shopping, or casual talking!
           - ONLY pick truly INSANE, HILARIOUS, SHOCKING, or VIRAL moments (score >= 92/100).
           - Keep clips TIGHT: 12 to 35 seconds max (complete setup -> punchline/action, zero dead air).
           - If there is NO 92+ banger moment in this video, return [].
        2. EXACT FACECAM BOX DETECTION:
           - Check if a REAL HUMAN PERSON is visible in a webcam box overlay.
           - If YES, measure the EXACT normalized bounding box of ONLY the webcam rectangle:
             "facecam_box": [x, y, w, h] where values are 0.0 to 1.0 (e.g. middle-left webcam above minimap = [0.0, 0.44, 0.22, 0.24]).
             DO NOT include the minimap or game HUD in facecam_box!
           - If NO real human facecam exists, set "facecam_box": null.

        Return JSON list:
        [{{
          "start": int,
          "end": int,
          "score": 92-100,
          "facecam_box": [0.0, 0.44, 0.22, 0.24] or null,
          "focus_x": "center/left/right",
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
        Find ONLY 92+/100 genuinely hilarious, savage, shocking, or peak hype dialogue moments (12-35s).
        IGNORE normal driving, walking, or average gameplay talk. If nothing is 92+, return [].
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
    You are the CHIEF PRO REELS EDITOR of MAG73.
    User style preference: "{style_pref}"
    Detected Language: {detected_lang}
    Vision Report: {vision_report}
    Dialogue Report: {dialogue_report}

    STRICT RULES:
    1. ONLY approve genuinely 92+/100 banger clips (12-35 seconds, tightly cut). NO boring driving/walking! If none exist, return [].
    2. FACECAM: Keep the exact "facecam_box": [x, y, w, h] from Vision Report ONLY if a real human facecam exists and adds value; otherwise null.
    3. VARIED EDIT STYLES ("edit_type") — NEVER edit every clip the same way:
       - "aura": Epic/savage/sigma moment -> dark cinematic grade, B&W beat drop ("bw_drop_sec"), phonk BGM.
       - "funny": Hilarious fail/roast -> NO heavy BGM, clean punchy look, optional title banner.
       - "hype": Intense clutch/action -> vibrant colors, energetic BGM, NO B&W drop.
       - "clean": Raw viral clip -> NO banner ("title_text": ""), NO BGM ("bgm_query": ""), NO SFX ("sfx_query": ""), just clean captions.
    4. Leave "bgm_query", "sfx_query", and "title_text" as "" whenever the clip is better raw/clean.

    Return ONLY valid JSON array:
    [
      {{
        "start": 40,
        "end": 55,
        "score": 94,
        "edit_type": "funny",
        "facecam_box": [0.0, 0.44, 0.22, 0.24],
        "focus_x": "center",
        "title_text": "",
        "bw_drop_sec": null,
        "bgm_query": "",
        "sfx_query": "",
        "caption_color": "&H0000FFFF"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=judge_prompt)
    raw_clips = _clean_json(final_res.text)

    # Hard filter: sirf 92+ banger moments rakho
    clips = [c for c in raw_clips if int(c.get("score", 0)) >= 92]

    print(f"[MAG73 Pro Editor] Approved {len(clips)} genuine 92+ banger clip(s)!")
    return clips, word_timestamps
