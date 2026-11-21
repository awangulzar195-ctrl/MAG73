import os
import json
import re
import subprocess
import concurrent.futures
import requests
from google import genai

GEMINI_KEY = os.getenv("GEMINI_API_KEY")
GROQ_KEY = os.getenv("GROQ_API_KEY")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")

gemini_client = genai.Client(api_key=GEMINI_KEY)

def extract_word_transcript(video_path="source_video.mp4"):
    """Groq Whisper Large v3 Turbo se exact word-by-word timestamps nikaalta hai"""
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
    data = res.json()
    return data.get("text", ""), data.get("words", [])

def _expert_gemini_vision(video_file, transcript_text, chat_spikes):
    """Expert 1: Video ke visuals, action, face reactions aur gameplay dekhta hai"""
    prompt = f"""
    You are the VISUAL & ACTION DIRECTOR in the MAG73 AI Council.
    Watch the video frames, read the transcript, and check live chat hype spikes (in seconds): {chat_spikes}.
    Find up to 8 best viral moments (25 to 58 seconds each).
    Return a JSON list with: start (int seconds), end (int seconds), score (1-100), reason.
    Transcript: {transcript_text[:10000]}
    """
    res = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[video_file, prompt]
    )
    return res.text

def _expert_groq_dialogue(transcript_text, chat_spikes):
    """Expert 2: Llama 3.3 70B comedy, roasting, storytelling aur emotional depth check karta hai"""
    prompt = f"""
    You are the DIALOGUE, COMEDY & STORYTELLING EXPERT in the MAG73 AI Council.
    Analyze this transcript and live chat spikes ({chat_spikes}) to find the funniest or most engaging moments (25-58s).
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

def _expert_openrouter_hooks(transcript_text, chat_spikes):
    """Expert 3: DeepSeek / Qwen free models scroll-stopping viral hooks & retention check karte hain"""
    prompt = f"""
    You are the VIRAL RETENTION & HOOK SPECIALIST.
    Find moments (25-58s) with an explosive 3-second opening hook and clean ending.
    Chat spikes: {chat_spikes}. Transcript: {transcript_text[:14000]}
    Return a JSON list with: start (int seconds), end (int seconds), score (1-100), hook_banner (max 5 words), mood (phonk/funny/intense).
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

def _clean_json(raw_text):
    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    return []

def run_super_ai_council(video_path, chat_spikes):
    """Saare AIs ko ek saath chala kar unka combined Super-Decision banata hai"""
    transcript_text, word_timestamps = extract_word_transcript(video_path)

    print("[MAG73 Council] Uploading video to Gemini Vision & waking up AI Council...")
    video_file = gemini_client.files.upload(file=video_path)

    # Teeno AI Experts ek hi time par parallel analyze karenge
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

    Select the TOP 5 ULTIMATE CLIPS (between 25 and 58 seconds each) where multiple experts agree or hype is highest.
    Return ONLY a valid JSON array with exact keys:
    [
      {{
        "start": 10,
        "end": 48,
        "combined_score": 94,
        "hook_text": "WAIT FOR THE END",
        "mood": "phonk",
        "yt_title": "Insane Clutch Moment #shorts #gaming",
        "yt_description": "Auto-clipped by MAG73 Multi-AI Engine #shorts"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(
        model="gemini-2.5-flash",
        contents=judge_prompt
    )
    clips = _clean_json(final_res.text)
    print(f"[MAG73 Judge] Approved {len(clips)} viral clips!")
    return clips, word_timestamps
