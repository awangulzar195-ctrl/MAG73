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
    """Groq Whisper se Roman Hinglish/English word timestamps nikaalta hai (no tofu boxes)"""
    if not GROQ_KEY:
        return "", []
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
                    "language": "en",
                    "prompt": "Transcribe in clean English or Roman Hinglish using ONLY English A-Z letters. Never use Devanagari or Urdu script.",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word"
                },
                timeout=120
            )
        if res.status_code != 200:
            return "", []
        data = res.json()
        return data.get("text", ""), data.get("words", [])
    except Exception as e:
        print(f"[MAG73 Audio] Skipped: {e}")
        return "", []

def _wait_for_gemini_file(video_file):
    while True:
        info = gemini_client.files.get(name=video_file.name)
        state = getattr(info.state, "name", str(info.state))
        if state == "ACTIVE":
            return info
        if state == "FAILED":
            raise RuntimeError("Gemini video processing failed.")
        time.sleep(3)

def _expert_gemini_vision(video_file, transcript_text, chat_spikes):
    try:
        prompt = f"""
        You are the VISUAL & VIRAL DIRECTOR in MAG73.
        Watch the entire video + check live chat bursts ({chat_spikes}).
        Find EVERY SINGLE viral moment (funny reaction, game glitch, insane dialogue, roast, clutch, plot twist).
        Do NOT limit to a fixed count — extract as many great 12-58s clips as exist in this video.
        Return JSON list: [{{ "start": int, "end": int, "score": 1-100, "reason": "..." }}]
        Transcript: {transcript_text[:10000]}
        """
        res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=[video_file, prompt])
        return res.text
    except Exception:
        return "[]"

def _expert_groq_dialogue(transcript_text, chat_spikes):
    if not GROQ_KEY or not transcript_text:
        return "[]"
    try:
        prompt = f"""
        Find ALL funny dialogues, roasts, shocking lines, or chat-burst moments (12-58s).
        Chat spikes: {chat_spikes}. Transcript: {transcript_text[:14000]}
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

def run_super_ai_council(video_path, chat_spikes):
    transcript_text, word_timestamps = extract_word_transcript(video_path)
    uploaded_file = gemini_client.files.upload(file=video_path)
    video_file = _wait_for_gemini_file(uploaded_file)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        f1 = executor.submit(_expert_gemini_vision, video_file, transcript_text, chat_spikes)
        f2 = executor.submit(_expert_groq_dialogue, transcript_text, chat_spikes)
        vision_report = f1.result()
        dialogue_report = f2.result()

    style_pref = os.getenv("EDIT_STYLE", "auto").strip().lower()

    judge_prompt = f"""
    You are the CHIEF CREATIVE DIRECTOR of MAG73.
    User style preference: "{style_pref}" (if "auto", be 100% creative and invent a unique pro editing style for EACH clip!).
    Combine Vision Report ({vision_report}), Dialogue Report ({dialogue_report}), and Chat Spikes ({chat_spikes}).

    Extract ALL genuinely viral clips (12 to 58 seconds each — no fixed limit, extract 1 if short video, or 8+ if long video).
    For EACH clip, design a UNIQUE, creative pro-editor recipe using these dynamic parameters:
    - "effects": choose 2-4 from ["punch_zoom", "camera_shake", "rgb_glitch", "flash_impact", "slow_zoom", "vignette"]
    - "bgm_query": specific YouTube search for no-copyright BGM matching THIS clip's exact emotion
    - "sfx_query": specific YouTube search for viral SFX (e.g. "vine boom sfx", "bass drop whoosh sfx", "glitch sound effect")
    - "contrast": float 1.05 to 1.25
    - "saturation": float 0.85 to 1.35
    - "caption_color": ASS hex color like "&H0000FFFF" (yellow), "&H0000FF88" (mint), "&H00FFFFFF" (white), "&H00FF99FF" (pink)
    - "hook_text": punchy 2-4 word English/Hinglish hook (ASCII letters only)

    Return ONLY valid JSON array:
    [
      {{
        "start": 0,
        "end": 22,
        "mood": "creative_vibe_name",
        "hook_text": "WAIT FOR THIS",
        "effects": ["punch_zoom", "flash_impact", "camera_shake"],
        "bgm_query": "ytsearch1:phonk aggressive bass no copyright",
        "sfx_query": "ytsearch1:vine boom sound effect",
        "contrast": 1.15,
        "saturation": 1.22,
        "caption_color": "&H0000FFFF"
      }}
    ]
    """
    final_res = gemini_client.models.generate_content(model="gemini-2.5-flash", contents=judge_prompt)
    clips = _clean_json(final_res.text)
    if not clips:
        clips = [{
            "start": 0, "end": 22, "mood": "pro_dynamic",
            "hook_text": "INSANE MOMENT",
            "effects": ["punch_zoom", "flash_impact", "vignette"],
            "bgm_query": "ytsearch1:viral phonk edit music no copyright",
            "sfx_query": "ytsearch1:bass drop impact sound effect",
            "contrast": 1.15, "saturation": 1.2, "caption_color": "&H0000FFFF"
        }]
    print(f"[MAG73 Creative Director] Designed {len(clips)} unique viral clips!")
    return clips, word_timestamps
