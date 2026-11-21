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
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()

gemini_client = genai.Client(api_key=GEMINI_KEY)

def extract_word_transcript(video_path="source_video.mp4"):
    """Groq Whisper se word-level timestamps nikaalta hai (safe fallback ke saath)"""
    if not GROQ_KEY:
        print("[MAG73 Audio] No GROQ_API_KEY found, skipping Whisper transcript.")
        return "", []
    try:
        print("[MAG73 Audio] Extracting audio & word-level timestamps...")
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
            print(f"[MAG73 Audio] Whisper warning ({res.status_code}): {res.text[:200]}")
            return "", []
        data = res.json()
        return data.get("text", ""), data.get("words", [])
    except Exception as e:
        print(f"[MAG73 Audio] Transcript skipped due to error: {e}")
        return "", []

def _wait_for_gemini_file(video_file):
    """Jab tak Gemini video ko ACTIVE na kar de, tab tak wait karta hai"""
    print("[MAG73 Vision] Waiting for Gemini to process video...")
    while True:
        file_info = gemini_client.files.get(name=video_file.name)
        state = getattr(file_info.state, "name", str(file_info.state))
        if state == "ACTIVE":
            print("[MAG73 Vision] Video is ACTIVE and ready!")
            return file_info
        elif state == "FAILED":
            raise RuntimeError("Gemini failed to process the uploaded video.")
        time.sleep(3)

def _expert_gemini_vision(video_file, transcript_text, chat_spikes):
    try:
        prompt = f"""
        You are the VISUAL & ACTION DIRECTOR in the MAG73 AI Council.
        Watch the video frames, read the transcript, and check live chat hype spikes (in seconds): {chat_spikes}.
        Find up to 5 best viral moments (15 to 58 seconds each).
        Return a JSON list with: start (int seconds), end (int seconds), score (1-100), reason.
        Transcript: {transcript_text[:10000]}
        """
        res = gemini_client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[video_file, prompt]
        )
        return res.text
    except Exception as e:
        print(f"[MAG73 Vision] Error: {e}")
        return "[]"

def _expert_groq_dialogue(transcript_text, chat_spikes):
    if not GROQ_KEY or not transcript_text:
        return "[]"
    try:
        prompt = f"""
        You are the DIALOGUE, COMEDY & STORYTELLING EXPERT in the MAG73 AI Council.
        Analyze this transcript and live chat spikes ({chat_spikes}) to find the funniest or most engaging moments (15-58s).
        Return a JSON list with: start (int seconds), end (int seconds), score (1-100), reason.
        Transcript: {transcript_text[:14000]}
        """
        res = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        ).json()
        return res["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[MAG73 Llama] Skipped: {e}")
        return "[]"

def _expert_openrouter_hooks(transcript_text, chat_spikes):
    if not OPENROUTER_KEY or not transcript_text:
        return "[]"
    try:
        prompt = f"""
        You are the VIRAL RETENTION & HOOK SPECIALIST.
        Find moments (15-58s) with an explosive 3-second opening hook and clean ending.
        Chat spikes: {chat_spikes}. Transcript: {transcript_text[:14000]}
        Return a JSON list with: start (int seconds), end (int seconds), score (1-100), hook_banner (max 5 words), mood (aura/funny/documentary/casual).
        """
        res = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_KEY}"},
            json={
                "model": "openrouter/free",
                "messages": [{"role": "user", "content": prompt}]
            },
            timeout=60
        ).json()
        return res["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[MAG73 OpenRouter] Skipped: {e}")
        return "[]"

def _clean_json(raw_text):
    try:
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"[MAG73 JSON] Parse warning: {e}")
    return []

def run_super_ai_council(video_path, chat_spikes):
    transcript_text, word_timestamps = extract_word_transcript(video_path)

    print("[MAG73 Council] Uploading video to Gemini Vision...")
    uploaded_file = gemini_client.files.upload(file=video_path)
    video_file = _wait_for_gemini_file(uploaded_file)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(_expert_gemini_vision, video_file, transcript_text, chat_spikes)
        f2 = executor.submit(_expert_groq_dialogue, transcript_text, chat_spikes)
        f3 = executor.submit(_expert_openrouter_hooks, transcript_text, chat_spikes)

        vision_report = f1.result()
        dialogue_report = f2.result()
        hook_report = f3.result()

    print("[MAG73 Judge] Merging all AI opinions into final Master Cut list...")
    judge_prompt = f"""
    You are the CHIEF AI JUDGE of MAG73. Combine the reports from all 3 AI experts + Live Chat Spikes ({chat_spikes}):
    1. Gemini Vision Report: {vision_report}
    2. Llama 70B Dialogue Report: {dialogue_report}
    3. OpenRouter Viral Hook Report: {hook_report}

    Select the TOP 3 to 5 ULTIMATE CLIPS (between 15 and 58 seconds each). If the video is short, select at least 1 clip covering the best part.
    Return ONLY a valid JSON array with exact keys:
    [
      {{
        "start": 0,
        "end": 30,
        "combined_score": 94,
        "hook_text": "WAIT FOR THE END",
        "mood": "aura",
        "yt_title": "Insane Moment #shorts #viral",
        "yt_description": "Edited by MAG73 Multi-AI Engine #shorts"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=judge_prompt
    )
    clips = _clean_json(final_res.text)
    if not clips:
        # Guaranteed fallback agar video chhota ho ya JSON empty aaye
        clips = [{
            "start": 0,
            "end": 30,
            "combined_score": 85,
            "hook_text": "WATCH TILL END",
            "mood": "casual",
            "yt_title": "Highlight Clip #shorts",
            "yt_description": "Edited by MAG73 Studio"
        }]
    print(f"[MAG73 Judge] Approved {len(clips)} viral clips!")
    return clips, word_timestamps
