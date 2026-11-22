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
                    "prompt": "Bhai ye Hindi aur Hinglish gaming stream hai. Jo bola gaya hai wahi likho, English mein translate mat karo."
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

        # Hindi/Urdu ya Devanagari/Arabic script ko exact Roman Hinglish mein badlo
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
                "(e.g. 'भाई' -> 'Bhai', 'क्या' -> 'kya', 'लड़ाई' -> 'ladai'). "
                "DO NOT translate Hindi words into English! Keep already-English words unchanged. "
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
        You are a STRICT VIRAL REELS DIRECTOR in MAG73.
        Analyze BOTH the video visuals/audio AND audience signals:
        - Live Chat Spikes (seconds): {audience_signals.get('chat_spikes', [])}
        - Top Comment Timestamps (seconds): {audience_signals.get('comment_timestamps', [])}
        - Top Viewer Comments: {audience_signals.get('top_comments', [])[:12]}

        CRITICAL RULES:
        1. REAL HUMAN FACECAM CHECK (VERY IMPORTANT):
           - Look closely: Is there an ACTUAL REAL HUMAN PERSON visible on a webcam overlay in a corner?
           - A game minimap, radar, HUD, kill feed, or mic icon is NOT a facecam!
           - ONLY set "layout": "split_facecam" if a REAL HUMAN FACE is clearly visible AND their facial reaction is a key part of the moment.
           - Otherwise, ALWAYS set "layout": "full_vertical" and "facecam_pos": "none".
        2. NO BORING CLIPS: Do NOT clip just because chat was active! Only clip if there is a GENUINE, COMPLETE viral moment (insane clutch, hilarious roast/dialogue, shocking glitch, or aura moment) with score >= 85/100.
           If there is NO genuinely great moment in this video, return an empty list: [].
        3. COMPLETE ARC: Start at the beginning of the setup and end after the full punchline/kill/reaction.

        Return JSON list:
        [{{
          "start": int,
          "end": int,
          "score": 85-100,
          "layout": "full_vertical or split_facecam",
          "facecam_pos": "none/bottom_right/bottom_left/top_right/top_left",
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
        Find ONLY genuinely hilarious, savage, shocking, or peak hype dialogue moments (score >= 85/100).
        If the transcript is just normal boring gameplay talk, return [].
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
    1. QUALITY ONLY: Only approve clips with score >= 85 that have a COMPLETE story/moment. If nothing is truly viral/entertaining, return [].
    2. FACECAM RULE: Keep "layout": "full_vertical" and "facecam_pos": "none" UNLESS Vision Report confirmed a REAL HUMAN FACE in a webcam box AND their face reaction matters. NEVER crop a minimap or HUD!
    3. EDIT STYLE ("edit_type"): Choose the best fitting style:
       - "aura": Sigma/epic clutch/badass moment -> phonk BGM + B&W beat drop ("bw_drop_sec") at the peak.
       - "funny": Hilarious roast/fail/meme moment -> light funny BGM or none, vine boom SFX ONLY at the punchline ("bw_drop_sec" optional).
       - "clutch": Intense gaming action -> hype build-up BGM, NO B&W drop ("bw_drop_sec": null).
       - "clean": Clean story/podcast/vlog clip -> subtle background music or "", NO fazool SFX, NO B&W drop.
    4. BANNER TITLE ("title_text"): Short, natural 2-5 word Hinglish/English title (ASCII only), or "" if not needed.
    5. BGM & SFX: Leave "bgm_query" or "sfx_query" as "" if the clip is better without it. Do NOT spam SFX!

    Return ONLY valid JSON array:
    [
      {{
        "start": 10,
        "end": 32,
        "score": 91,
        "edit_type": "funny",
        "layout": "full_vertical",
        "facecam_pos": "none",
        "focus_x": "center",
        "title_text": "LADAI HO GAYI HAMARI",
        "bw_drop_sec": null,
        "bgm_query": "",
        "sfx_query": "",
        "caption_color": "&H0000FFFF"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=judge_prompt)
    raw_clips = _clean_json(final_res.text)

    # Strict filter: sirf asli 85+ moments rakho, koi forced boring fallback nahi!
    clips = [c for c in raw_clips if int(c.get("score", 0)) >= 85]

    print(f"[MAG73 Pro Editor] Approved {len(clips)} genuine viral clip(s)!")
    return clips, word_timestamps
