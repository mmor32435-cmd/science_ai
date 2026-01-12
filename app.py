"""
AI Science Tutor Pro - Complete Final Version (Integrated fixes)
- Provider fallbacks, diagnostics, retries and local MCQ fallback
- Robust audio conversion (pydub/ffmpeg) and improved speech-to-text
- TTS playback using BytesIO and format hints
- Stable text input (text_area + send button) replacing st.chat_input
- Drive book activation persisted in session_state.book_activated
- MCQ generation strictly from activated textbook; stores correct answer in session_state.q_answer
- Improved microphone tab with uploader fallback and clear diagnostics
"""
import streamlit as st
import time
import asyncio
import re
import random
import threading
from io import BytesIO
from datetime import datetime
import pytz
import os
import json
import base64
import logging
import subprocess
import shutil
from typing import Optional, Dict, Any, List, Tuple

# Optional provider & tools imports
try:
    import google.generativeai as genai
except Exception:
    genai = None

try:
    import openai
except Exception:
    openai = None

try:
    import edge_tts
except Exception:
    edge_tts = None

try:
    import speech_recognition as sr
except Exception:
    sr = None

try:
    from streamlit_mic_recorder import mic_recorder
except Exception:
    mic_recorder = None

from PIL import Image
import PyPDF2

# Google API optional
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseDownload
    import gspread
    import pandas as pd
except Exception:
    service_account = None
    build = None
    MediaIoBaseDownload = None
    gspread = None
    pd = None

# ==========================================
# Basic config & secrets
# ==========================================
st.set_page_config(page_title="AI Science Tutor Pro", page_icon="🧬", layout="wide")

TEACHER_MASTER_KEY = st.secrets.get("TEACHER_MASTER_KEY", "ADMIN_2024_PLACEHOLDER")
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "")
GOOGLE_API_KEYS = st.secrets.get("GOOGLE_API_KEYS", [])
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
GCP_SA = st.secrets.get("gcp_service_account", None)

SESSION_DURATION_MINUTES = int(st.secrets.get("SESSION_DURATION_MINUTES", 60))
RATE_LIMIT_MIN_SECONDS = int(st.secrets.get("RATE_LIMIT_MIN_SECONDS", 1))

DAILY_FACTS = st.secrets.get("DAILY_FACTS", [
    "هل تعلم؟ المخ يولد كهرباء تكفي لمصباح! 💡",
    "هل تعلم؟ العظام أقوى من الخرسانة بـ 4 مرات! 🦴",
    "هل تعلم؟ الأخطبوط لديه 3 قلوب! 🐙",
    "هل تعلم؟ العسل لا يفسد أبداً! 🍯",
])

LOCAL_LOG_FILE = "logs_local.json"
CHAT_HISTORY_DIR = "chat_histories"
os.makedirs(CHAT_HISTORY_DIR, exist_ok=True)

# ==========================================
# Logging setup
# ==========================================
logger = logging.getLogger("ai_science_tutor")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)

# ==========================================
# safe_rerun: cross-version safe rerun wrapper
# ==========================================
def safe_rerun():
    try:
        if hasattr(st, "experimental_rerun") and callable(st.experimental_rerun):
            st.experimental_rerun()
            return
        if hasattr(st, "rerun") and callable(st.rerun):
            st.rerun()
            return
    except Exception:
        logger.exception("safe_rerun: rerun attempt failed")
    try:
        st.stop()
    except Exception:
        logger.exception("safe_rerun: st.stop also failed")

# ==========================================
# Utilities
# ==========================================
def now_str():
    tz = pytz.timezone("Africa/Cairo")
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")

def safe_write_local_log(entry: Dict[str, Any]):
    try:
        with open(LOCAL_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to write local log")

def load_chat_history_local(user_name: str) -> List[Dict[str, Any]]:
    path = os.path.join(CHAT_HISTORY_DIR, f"{user_name}.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                out.append(json.loads(line))
    except Exception:
        logger.exception("Error reading chat history local file.")
    return out

def append_chat_history_local(user_name: str, entry: Dict[str, Any]):
    path = os.path.join(CHAT_HISTORY_DIR, f"{user_name}.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        logger.exception("Failed to append chat history locally.")

# ==========================================
# Google Sheets/Drive helpers (optional)
# ==========================================
if gspread and GCP_SA:
    @st.cache_resource
    def get_gspread_client():
        try:
            creds_dict = dict(GCP_SA)
            scope = ['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/spreadsheets']
            creds = service_account.Credentials.from_service_account_info(creds_dict, scopes=scope)
            return gspread.authorize(creds)
        except Exception:
            logger.exception("Failed to authorize gspread.")
            return None
else:
    def get_gspread_client():
        return None

def safe_get_control_sheet_value():
    client = get_gspread_client()
    if not client:
        return None
    try:
        sheet = client.open("App_Control")
        return sheet.sheet1.acell('B1').value
    except Exception:
        logger.exception("Failed to read App_Control B1")
        return None

def safe_append_activity_log(entry: Dict[str, Any]):
    client = get_gspread_client()
    if client:
        try:
            wb = client.open("App_Control")
            try:
                sh = wb.worksheet("Activity")
                sh.append_row([entry.get("time"), entry.get("user"), entry.get("input_type"), entry.get("text")[:1000]])
                return
            except Exception:
                logger.exception("Failed to append to Activity worksheet.")
        except Exception:
            logger.exception("Failed to open App_Control workbook.")
    safe_write_local_log({"type": "activity", **entry})

def safe_update_xp_sheet(user_name: str, points: int):
    client = get_gspread_client()
    if client:
        try:
            wb = client.open("App_Control")
            try:
                sh = wb.worksheet("Gamification")
            except Exception:
                sh = wb.sheet1
            cell = sh.find(user_name)
            if cell:
                cur = sh.cell(cell.row, 2).value
                cur = int(cur) if cur else 0
                sh.update_cell(cell.row, 2, cur + points)
            else:
                sh.append_row([user_name, points])
            return
        except Exception:
            logger.exception("Failed to update XP sheet.")
    safe_write_local_log({"type": "xp", "time": now_str(), "user": user_name, "points": points})

# ==========================================
# Model abstraction and fallback with detailed error capture
# ==========================================
_last_provider_errors: List[str] = []

def init_google_genai_if_available():
    if genai and GOOGLE_API_KEYS:
        for k in GOOGLE_API_KEYS:
            try:
                genai.configure(api_key=k)
                logger.info("Configured Google generativeai with a key")
                return True
            except Exception:
                continue
    return False

_GOOGLE_INITIALIZED = init_google_genai_if_available()

def call_model(prompt: str, *, model_preferences: Optional[List[str]] = None, max_output_chars: int = 4000) -> str:
    global _last_provider_errors
    _last_provider_errors = []
    if not prompt:
        return ""

    # Try Google Generative AI
    if genai and _GOOGLE_INITIALIZED:
        try:
            if hasattr(genai, "TextGenerationModel"):
                for candidate in (model_preferences or ["gemini-2.5-flash", "gemini-flash-latest", "gemini-pro-latest", "gemini-2.0-flash"]):
                    try:
                        model = genai.TextGenerationModel.from_pretrained(candidate)
                        resp = model.generate(prompt=prompt, max_output_tokens=512)
                        text = ""
                        if hasattr(resp, "candidates"):
                            text = resp.candidates[0].content
                        elif hasattr(resp, "outputs"):
                            text = resp.outputs[0].content
                        if text:
                            return text
                    except Exception as e:
                        _last_provider_errors.append(f"Google(TextGenerationModel:{candidate}) error: {e}")
                        continue
            if hasattr(genai, "generate_text"):
                try:
                    resp = genai.generate_text(model="gemini-2.5-flash", prompt=prompt)
                    if isinstance(resp, dict) and "candidates" in resp:
                        return resp["candidates"][0].get("content", "")
                    return str(resp)
                except Exception as e:
                    _last_provider_errors.append(f"Google(generate_text) error: {e}")
            if hasattr(genai, "GenerativeModel"):
                for candidate in (model_preferences or ["gemini-2.5-flash", "gemini-flash-latest"]):
                    try:
                        m = genai.GenerativeModel(candidate)
                        out = m.generate_content(prompt)
                        return out.text
                    except Exception as e:
                        _last_provider_errors.append(f"Google(GenerativeModel:{candidate}) error: {e}")
                        continue
        except Exception as e:
            _last_provider_errors.append(f"Google(general) error: {e}")

    # Try OpenAI
    if openai and OPENAI_API_KEY:
        try:
            openai.api_key = OPENAI_API_KEY
            if hasattr(openai, "ChatCompletion"):
                try:
                    resp = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=512,
                    )
                    return resp.choices[0].message.content
                except Exception as e:
                    _last_provider_errors.append(f"OpenAI(ChatCompletion) error: {e}")
            else:
                try:
                    resp = openai.Completion.create(engine="text-davinci-003", prompt=prompt, max_tokens=512)
                    return resp.choices[0].text
                except Exception as e:
                    _last_provider_errors.append(f"OpenAI(Completion) error: {e}")
        except Exception as e:
            _last_provider_errors.append(f"OpenAI(general) error: {e}")

    if not _last_provider_errors:
        _last_provider_errors.append("No providers configured (no genai and no openai key).")
    raise RuntimeError("No AI provider available. Attempts:\n" + "\n".join(_last_provider_errors))

# safe wrapper and diagnostics
def safe_call_model(prompt: str) -> Tuple[bool, str, Optional[str]]:
    try:
        text = call_model(prompt)
        return True, text, None
    except Exception as e:
        logger.exception("call_model failed")
        return False, "", str(e)

# ==========================================
# RETRY WRAPPER & LOCAL MCQ FALLBACK
# ==========================================
def local_generate_mcq(grade: str, language: str = "العربية") -> str:
    bank_ar = [
        ("ما هو العضو المسؤول عن ضخ الدم في الجسم؟", ["الرئتان", "القلب", "الدماغ", "الكبد"]),
        ("ما لون الدم في معظم الحيوانات الفقارية نتيجة الأكسجين؟", ["أخضر", "أصفر", "أحمر", "أزرق"]),
        ("أي من التالي مصدر للطاقة المتجدد؟", ["الفحم", "النفط", "الرياح", "الغاز الطبيعي"]),
    ]
    bank_en = [
        ("Which organ pumps blood through the body?", ["Lungs", "Heart", "Brain", "Liver"]),
        ("What is the color of oxygen-rich blood in vertebrates?", ["Green", "Yellow", "Red", "Blue"]),
        ("Which is a renewable energy source?", ["Coal", "Oil", "Wind", "Natural gas"]),
    ]

    if language == "العربية":
        q, choices = random.choice(bank_ar)
        random.shuffle(choices)
        options = "\n".join([f"{chr(65+i)}. {c}" for i, c in enumerate(choices)])
        return f"{q}\n{options}\n\n(ملاحظة: هذا سؤال مُولد محلياً كحل بديل — لا يتضمن الإجابة.)"
    else:
        q, choices = random.choice(bank_en)
        random.shuffle(choices)
        options = "\n".join([f"{chr(65+i)}. {c}" for i, c in enumerate(choices)])
        return f"{q}\n{options}\n\n(Note: locally generated fallback, answer not included.)"

def safe_call_model_with_retries(prompt: str, max_retries: int = 3, base_delay: float = 2.0) -> Tuple[bool, str, Optional[str]]:
    attempt = 0
    last_err = None
    while attempt < max_retries:
        attempt += 1
        ok, text, err = safe_call_model(prompt)
        if ok:
            return True, text, None
        last_err = err or "unknown error"
        lowered = last_err.lower()
        if "quota" in lowered or "rate limit" in lowered or "429" in lowered or "retry" in lowered:
            m = re.search(r"retry in\s*([0-9\.]+)s", last_err, flags=re.IGNORECASE)
            if m:
                delay = float(m.group(1)) + 0.5
            else:
                delay = base_delay * (2 ** (attempt - 1))
            logger.warning("AI provider rate/quota error detected. Retry %d/%d after %.1fs. Error: %s", attempt, max_retries, delay, last_err)
            time.sleep(delay)
            continue
        logger.error("Non-retriable provider error: %s", last_err)
        break
    return False, "", last_err

# ==========================================
# Audio conversion helpers (pydub/ffmpeg fallback)
# ==========================================
def _has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None

def convert_audio_to_wav_bytes(raw_bytes: bytes, input_format: Optional[str] = None) -> Optional[bytes]:
    """
    Convert common audio formats (webm/m4a/mp3/ogg) to WAV bytes using pydub or ffmpeg binary.
    Returns WAV bytes or None if conversion failed.
    """
    # Try pydub (if installed and ffmpeg available)
    try:
        from pydub import AudioSegment  # optional dependency
        bio = BytesIO(raw_bytes)
        if input_format:
            seg = AudioSegment.from_file(bio, format=input_format)
        else:
            seg = AudioSegment.from_file(bio)
        out = BytesIO()
        seg = seg.set_frame_rate(16000).set_channels(1)
        seg.export(out, format="wav")
        return out.getvalue()
    except Exception:
        pass

    if _has_ffmpeg():
        try:
            p = subprocess.Popen(
                ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
            out, err = p.communicate(raw_bytes, timeout=30)
            if p.returncode == 0:
                return out
            else:
                logger.error("ffmpeg conversion failed: %s", err.decode("utf-8", errors="ignore"))
        except Exception:
            logger.exception("ffmpeg subprocess conversion failed")
    else:
        logger.debug("ffmpeg binary not found in PATH; cannot convert non-wav audio.")
    return None

# ==========================================
# Speech-to-text helper (uses conversion)
# ==========================================
def speech_to_text_bytes(audio_bytes: bytes, lang_code: str = "ar-EG") -> Optional[str]:
    """
    Accepts raw bytes that may be WAV or other formats (webm/m4a/mp3/ogg).
    Attempts conversion to WAV then runs speech_recognition.
    """
    if not sr:
        logger.warning("speech_recognition not available")
        return None

    # Decode data URLs or base64 strings
    try:
        if isinstance(audio_bytes, str):
            if audio_bytes.startswith("data:"):
                audio_bytes = audio_bytes.split(",", 1)[1]
            audio_bytes = base64.b64decode(audio_bytes)
    except Exception:
        logger.exception("Failed to decode base64 audio string")

    wav_bytes = None
    try:
        if isinstance(audio_bytes, (bytes, bytearray)) and audio_bytes[:4] == b'RIFF':
            wav_bytes = bytes(audio_bytes)
    except Exception:
        pass

    if not wav_bytes:
        wav_bytes = convert_audio_to_wav_bytes(audio_bytes, input_format=None)

    if not wav_bytes:
        logger.error("Could not convert audio to WAV for speech recognition")
        return None

    r = sr.Recognizer()
    try:
        with sr.AudioFile(BytesIO(wav_bytes)) as source:
            r.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = r.record(source)
            return r.recognize_google(audio_data, language=lang_code)
    except sr.UnknownValueError:
        logger.info("Speech not understood by recognizer")
        return None
    except sr.RequestError as e:
        logger.exception("Speech recognition request error: %s", e)
        return None
    except Exception:
        logger.exception("Speech to text general failure")
        return None

# ==========================================
# Stream utilities: safe streaming display
# ==========================================
def stream_text_to_placeholder(text: str, placeholder, delay: float = 0.02):
    buf = ""
    counter = 0
    for ch in text:
        buf += ch
        counter += 1
        if counter % 20 == 0:
            placeholder.markdown(buf)
            time.sleep(delay)
    placeholder.markdown(buf)

# ==========================================
# Business Logic helpers
# ==========================================
def log_login(user_name: str, user_type: str, details: str):
    entry = {"time": now_str(), "type": "login", "user": user_name, "user_type": user_type, "details": details}
    threading.Thread(target=safe_write_local_log, args=(entry,)).start()
    threading.Thread(target=safe_append_activity_log, args=({"time": entry["time"], "user": user_name, "input_type": "login", "text": details},)).start()

def log_activity(user_name: str, input_type: str, text: str):
    entry = {"time": now_str(), "user": user_name, "input_type": input_type, "text": text[:1000]}
    threading.Thread(target=safe_append_activity_log, args=(entry,)).start()
    safe_write_local_log({"type": "activity", **entry})

def update_xp(user_name: str, points: int):
    if 'current_xp' in st.session_state:
        st.session_state.current_xp = st.session_state.get("current_xp", 0) + points
    threading.Thread(target=safe_update_xp_sheet, args=(user_name, points)).start()
    safe_write_local_log({"type": "xp", "time": now_str(), "user": user_name, "points": points})

# Session initialization
if "auth_status" not in st.session_state:
    st.session_state.update({
        "auth_status": False,
        "user_type": "none",
        "chat_history": [],
        "student_grade": "General",
        "current_xp": 0,
        "last_audio_bytes": None,
        "language": "العربية",
        "ref_text": "",
        "last_request_time": None,
        "start_time": time.time(),
        "q_active": False,
        "q_answer": None,
        "q_explanation": None,
        "book_activated": None,
    })

def session_expired() -> bool:
    start = st.session_state.get("start_time", time.time())
    return (time.time() - start) > (SESSION_DURATION_MINUTES * 60)

# ==========================================
# UI helpers
# ==========================================
def draw_header():
    st.markdown("""
        <div style='background:linear-gradient(135deg,#6a11cb,#2575fc);padding:1.2rem;border-radius:12px;text-align:center;color:white;margin-bottom:1rem;'>
            <h1 style='margin:0;'>🧬 AI Science Tutor Pro</h1>
            <div style='font-size:0.95rem;opacity:0.95;'>مُنظّم للتعلم، مدعوم بعدة مزوّدين ونظام تعزيز تكاملي</div>
        </div>
    """, unsafe_allow_html=True)

# ==========================================
# Helper to play TTS bytes safely
# ==========================================
def play_tts_bytes(audio_bytes: bytes):
    if not audio_bytes:
        return
    try:
        st.audio(BytesIO(audio_bytes), format="audio/mp3", start_time=0)
    except Exception:
        try:
            st.audio(BytesIO(audio_bytes), start_time=0)
        except Exception:
            logger.exception("Failed to play TTS audio")

# ==========================================
# Core: process_ai_response (with MCQ JSON flow)
# ==========================================
def process_ai_response(user_text: Any, input_type: str = "text"):
    last = st.session_state.get("last_request_time")
    if last and time.time() - last < RATE_LIMIT_MIN_SECONDS:
        st.warning("رجاءً انتظر قليلاً قبل إرسال طلب آخر.")
        return
    st.session_state["last_request_time"] = time.time()
    user_name = st.session_state.get("user_name", "anonymous")
    log_activity(user_name, input_type, str(user_text)[:1000])

    lang = st.session_state.get("language", "العربية")
    grade = st.session_state.get("student_grade", "General")
    ref = st.session_state.get("ref_text", "")[:20000]

    lang_instr = "Arabic" if lang == "العربية" else "English"

    base_prompt = f"""You are a kind and interactive Science Tutor for grade {grade}.
Language: {lang_instr}.
Context: {ref}
Instructions: Answer clearly, provide step-by-step explanations, give an example, and if appropriate include a small diagram using Graphviz DOT inside ```dot ... ``` tags.
When generating MCQ from the textbook content, return strict JSON only with fields:
{{"question":"...","choices":["A) ...","B) ...","C) ...","D) ..."],"answer":"B","explanation":"..."}}
Do NOT include any extra text outside the JSON.
"""

    st.markdown("---")
    placeholder = st.empty()

    try:
        if input_type == "image":
            caption = "Please explain the image and highlight key science concepts."
            image_obj = None
            if isinstance(user_text, list) and len(user_text) >= 2 and isinstance(user_text[1], Image.Image):
                image_obj = user_text[1]
                buffered = BytesIO()
                image_obj.convert("RGB").resize((480, 480)).save(buffered, format="JPEG", quality=70)
                img_b64 = base64.b64encode(buffered.getvalue()).decode("ascii")
                prompt = base_prompt + f"\nImage (base64 JPEG): {img_b64[:500]}... (trimmed)\nTask: Explain what is visible and the science behind it.\n"
            else:
                prompt = base_prompt + f"\nTask: {caption}\n"
            placeholder.markdown("🔎 يتم تحليل الصورة... الرجاء الانتظار.")
            ok, full_text, err = safe_call_model_with_retries(prompt)
            if not ok:
                fallback = "عذراً، خدمة الذكاء الاصطناعي غير متاحة الآن لتحليل الصورة. يمكنك المحاولة لاحقاً."
                placeholder.error(fallback)
                placeholder.write("تفاصيل الخطأ (موجز):")
                placeholder.write(err)
                append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": "<image>", "response": fallback})
                return
            placeholder.empty()
            stream_text_to_placeholder(full_text, placeholder)
            vc = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-ChristopherNeural"
            try:
                audio_bytes = generate_audio_sync(re.sub(r'```dot[\s\S]*?```', '', full_text)[:800], vc) if edge_tts else None
                if audio_bytes:
                    play_tts_bytes(audio_bytes)
            except Exception:
                logger.exception("TTS failed for image response")
            append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": "<image>", "response": full_text})
            update_xp(user_name, 15)

        elif input_type == "mcq_generate":
            # Require ref_text (book) to generate MCQ from textbook
            if not ref or len(ref) < 200:
                st.error("لم يتم تفعيل كتاب الطالب أو أن نص الكتاب قصير جداً. في الشريط الجانبي اختر كتابًا من Drive ثم اضغط تفعيل.")
                return
            prompt = base_prompt + f"\nContextFromBook:\n{ref}\n\nTask: Generate 1 MCQ strictly based on the textbook content above for grade {grade}. Return only valid JSON as described."
            ok, resp, err = safe_call_model_with_retries(prompt)
            if not ok:
                if err and any(k in err.lower() for k in ["quota", "rate limit", "429", "please retry", "retry in"]):
                    fallback = local_generate_mcq(st.session_state.get("student_grade","General"), st.session_state.get("language","العربية"))
                    st.warning("مزود الذكاء الاصطناعي غير متاح مؤقتًا — عرض سؤال احتياطي محلي.")
                    st.markdown(fallback)
                    st.session_state.q_curr = fallback
                    st.session_state.q_answer = None
                    st.session_state.q_explanation = None
                    st.session_state.q_active = True
                    append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": "<generate_mcq_fallback_local>", "response": fallback})
                    update_xp(user_name, 3)
                    return
                else:
                    st.error("تعذّر إنشاء السؤال: " + (err or "مشكلة غير معروفة"))
                    return
            # Parse JSON from model response
            try:
                m = re.search(r"\{[\s\S]*\}", resp)
                json_str = m.group(0) if m else resp
                qobj = json.loads(json_str)
                # Save answer and explanation server-side
                st.session_state.q_curr = qobj["question"] + "\n\n" + "\n".join(qobj["choices"])
                st.session_state.q_answer = qobj["answer"].strip().upper()
                st.session_state.q_explanation = qobj.get("explanation", "")
                st.session_state.q_active = True
                st.markdown(st.session_state.q_curr)
                append_chat_history_local(user_name, {"time": now_str(), "type":"mcq_generated","question": qobj})
                update_xp(user_name, 5)
            except Exception as e:
                logger.exception("Failed to parse MCQ JSON: %s", e)
                st.error("تعذّر فهم استجابة الموديل. حاول مرة أخرى أو عيّن نص الكتاب بشكل صحيح.")
                return

        elif input_type == "mcq_check":
            q_text = st.session_state.get("q_curr")
            correct = st.session_state.get("q_answer")
            if not q_text or not correct:
                st.error("لا يوجد سؤال نشط أو لم يتم حفظ الإجابة الصحيحة. تأكد من توليد السؤال من كتاب الطالب أولاً.")
                return
            user_ans = None
            if isinstance(user_text, dict):
                user_ans = str(user_text.get("answer","")).strip().upper()
            else:
                user_ans = str(user_text).strip().upper()
            if not user_ans:
                st.warning("اكتب إجابتك أولاً (A/B/C/D).")
                return
            if user_ans == correct:
                st.success("إجابتك صحيحة 🎉")
                explanation = st.session_state.get("q_explanation", "")
                if explanation:
                    st.write(explanation)
                update_xp(user_name, 50)
            else:
                st.error("الإجابة غير صحيحة.")
                st.write(f"الإجابة الصحيحة: {correct}")
                explanation = st.session_state.get("q_explanation", "")
                if explanation:
                    st.write(explanation)
                update_xp(user_name, -5)
            st.session_state.q_active = False

        else:
            prompt = base_prompt + f"\nStudent: {user_text}\nAnswer:"
            ok, raw, err = safe_call_model_with_retries(prompt)
            if not ok:
                fallback = "عذراً، خدمة الذكاء الاصطناعي غير متاحة الآن. حاول إعادة المحاولة أو تحقق من إعدادات المفاتيح."
                placeholder.error(fallback)
                placeholder.write("تفاصيل الخطأ (موجز):")
                placeholder.write(err)
                append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": str(user_text)[:1000], "response": fallback})
                return
            dot_code = None
            if "```dot" in raw:
                try:
                    dot_code = raw.split("```dot")[1].split("```")[0]
                except Exception:
                    dot_code = None
                display_text = raw.split("```dot")[0]
            else:
                display_text = raw
            stream_text_to_placeholder(display_text, placeholder)
            if dot_code:
                try:
                    st.graphviz_chart(dot_code)
                except Exception:
                    logger.exception("Failed to render graphviz dot")
            vc = "ar-EG-ShakirNeural" if lang == "العربية" else "en-US-ChristopherNeural"
            try:
                audio_bytes = generate_audio_sync(re.sub(r'```dot[\s\S]*?```', '', display_text)[:1000], vc) if edge_tts else None
                if audio_bytes:
                    play_tts_bytes(audio_bytes)
            except Exception:
                logger.exception("TTS failed for text response")
            append_chat_history_local(user_name, {"time": now_str(), "input_type": input_type, "input": str(user_text)[:1000], "response": raw})
            update_xp(user_name, 5)

    except Exception as e:
        logger.exception("Processing AI response failed")
        st.error(f"خطأ في المعالجة: {e}")
        safe_write_local_log({"type": "error", "time": now_str(), "error": str(e), "context": str(user_text)[:1000]})

# ==========================================
# UI Layout & Interaction (diagnostics + full UI)
# ==========================================
draw_header()

# Sidebar diagnostics and controls
with st.sidebar:
    st.write(f"أهلاً، **{st.session_state.get('user_name','ضيف')}**")
    diag = st.expander("⚙️ Diagnostics (AI providers)")
    with diag:
        st.write("Installed modules:")
        st.write(f"- google.generativeai: {'✅' if genai else '❌'}")
        st.write(f"- openai: {'✅' if openai else '❌'}")
        st.write(f"- edge-tts: {'✅' if edge_tts else '❌'}")
        st.write(f"- speech_recognition: {'✅' if sr else '❌'}")
        st.write(f"- streamlit_mic_recorder: {'✅' if mic_recorder else '❌'}")
        st.write("---")
        st.write("Configured keys:")
        st.write(f"- GOOGLE_API_KEYS: {len(GOOGLE_API_KEYS) if GOOGLE_API_KEYS else 0}")
        st.write(f"- OPENAI_API_KEY: {'✅' if OPENAI_API_KEY else '❌'}")
        if st.button("Run quick AI ping test"):
            try:
                ok, resp, err = safe_call_model_with_retries("Say 'ping' in a short sentence.", max_retries=2)
                if ok:
                    st.success("AI ping OK")
                    st.write(resp[:500])
                else:
                    st.error("Ping failed. Summary:")
                    st.write(err)
                    st.write("---")
                    st.write("Collected provider attempt errors:")
                    st.write("\n".join(_last_provider_errors))
            except Exception as e:
                st.error("Ping routine failed: " + repr(e))

    st.markdown("---")
    st.session_state.language = st.radio("اللغة:", ["العربية", "English"])
    st.markdown("---")
    if st.session_state.user_type == "student":
        st.metric("XP", st.session_state.current_xp)
        if st.session_state.current_xp >= 100:
            st.success("🎉 مستوى ممتاز! استمر هكذا.")
        st.markdown("---")
        st.caption("🏆 المتصدرون (محلي)")
        try:
            client = get_gspread_client()
            if client and pd:
                wb = client.open("App_Control")
                try:
                    sh = wb.worksheet("Gamification")
                    df = pd.DataFrame(sh.get_all_records())
                    if not df.empty:
                        df_sorted = df.sort_values(by=df.columns[1], ascending=False).head(5)
                        for i, row in df_sorted.iterrows():
                            st.text(f"{row[df.columns[0]]} — {row[df.columns[1]]}")
                    else:
                        st.text("لا يوجد بيانات بعد")
                except Exception:
                    logger.debug("Gamification sheet read failed")
            else:
                st.text("لا تتوفر بيانات السحابة.")
        except Exception:
            logger.exception("Leaderboard load failed")
    elif st.session_state.user_type == "teacher":
        st.markdown("### 🛠️ لوحة المدرّس")
        if st.button("عرض سجلات الدخول المحلية"):
            if os.path.exists(LOCAL_LOG_FILE):
                with open(LOCAL_LOG_FILE, "r", encoding="utf-8") as f:
                    lines = f.readlines()[-50:]
                    for L in lines:
                        try:
                            st.text(json.loads(L).get("time", "") + " — " + json.dumps(json.loads(L), ensure_ascii=False))
                        except Exception:
                            st.text(L.strip())
            else:
                st.text("لا سجلات محلية حتى الآن.")
        if st.button("تصدير السجلات كملف"):
            if os.path.exists(LOCAL_LOG_FILE):
                with open(LOCAL_LOG_FILE, "rb") as f:
                    b = f.read()
                    st.download_button("تحميل السجلات (JSONL)", b, file_name=f"logs_{int(time.time())}.jsonl")
            else:
                st.info("لا سجلات متاحة")
        st.markdown("---")
        msg = st.text_area("رسالة بث للطلاب (تجريبية):")
        if st.button("بث"):
            safe_write_local_log({"type": "broadcast", "time": now_str(), "from": st.session_state.user_name, "message": msg})
            st.success("تم البث محلياً")
    st.markdown("---")
    # Drive listing and activation with persistent flag
    if DRIVE_FOLDER_ID and build and GCP_SA:
        if st.button("تحميل قائمة ملفات Drive"):
            try:
                creds = service_account.Credentials.from_service_account_info(dict(GCP_SA), scopes=['https://www.googleapis.com/auth/drive.readonly'])
                drive_service = build('drive', 'v3', credentials=creds)
                q = f"'{DRIVE_FOLDER_ID}' in parents and trashed = false"
                res = drive_service.files().list(q=q, fields="files(id, name)").execute()
                files = res.get('files', [])
                st.session_state.drive_files = files
                st.success(f"تم جلب {len(files)} ملف(ـاً).")
            except Exception as e:
                logger.exception("Drive listing failed")
                st.error(f"فشل جلب قائمة الملفات: {e}")

        if st.session_state.get("drive_files"):
            st.markdown("**اختر كتابًا ثم اضغط تفعيل**")
            names = [f["name"] for f in st.session_state["drive_files"]]
            sel = st.selectbox("📚 المكتبة:", names, key="drive_select")
            if st.button("تفعيل الكتاب"):
                fid = next((f["id"] for f in st.session_state["drive_files"] if f["name"] == sel), None)
                if fid:
                    try:
                        creds = service_account.Credentials.from_service_account_info(dict(GCP_SA), scopes=['https://www.googleapis.com/auth/drive.readonly'])
                        drive_service = build('drive', 'v3', credentials=creds)
                        req = drive_service.files().get_media(fileId=fid)
                        fh = BytesIO()
                        downloader = MediaIoBaseDownload(fh, req)
                        done = False
                        while not done:
                            _, done = downloader.next_chunk()
                        fh.seek(0)
                        reader = PyPDF2.PdfReader(fh)
                        text = ""
                        for page in reader.pages:
                            text += (page.extract_text() or "")
                        st.session_state.ref_text = text
                        st.session_state.book_activated = sel
                        st.success(f"تم تفعيل الكتاب: {sel}")
                    except Exception as e:
                        logger.exception("فشل تحميل الكتاب من Drive.")
                        st.error(f"فشل تحميل الكتاب من Drive: {e}")
        if st.session_state.get("book_activated"):
            st.info(f"الكتاب المفعل حالياً: {st.session_state['book_activated']}")
    st.caption("نسخة محسّنة - تحكّم كامل")

# If not authenticated show login form
if not st.session_state.auth_status:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info(random.choice(DAILY_FACTS))
        with st.form("login_form"):
            name = st.text_input("الاسم:")
            grade = st.selectbox("الصف:", ["الرابع", "الخامس", "السادس", "الأول ع", "الثاني ع", "الثالث ع", "ثانوي", "Other"])
            code = st.text_input("الكود:", type="password")
            remember = st.checkbox("تذكرني على هذا الجهاز")
            if st.form_submit_button("دخول"):
                db_code = safe_get_control_sheet_value()
                is_teacher = (code == TEACHER_MASTER_KEY)
                is_student = (db_code and code == db_code) or (not db_code and code == TEACHER_MASTER_KEY)
                if is_teacher or is_student:
                    st.session_state.auth_status = True
                    st.session_state.user_type = "teacher" if is_teacher else "student"
                    st.session_state.user_name = name if is_student else "Mr. Elsayed"
                    st.session_state.student_grade = grade
                    st.session_state.start_time = time.time()
                    st.session_state.current_xp = 0 if not is_student else st.session_state.get("current_xp", 0)
                    log_login(st.session_state.user_name, "teacher" if is_teacher else "student", grade)
                    st.success("تم الدخول!")
                    st.session_state["_needs_rerun"] = True
                else:
                    st.error("الكود غير صحيح")

    if st.session_state.pop("_needs_rerun", False):
        time.sleep(0.4)
        safe_rerun()
    st.stop()

# If session expired, force logout
if session_expired():
    st.warning("انتهت الجلسة. يرجى تسجيل الدخول مرة أخرى.")
    st.session_state.auth_status = False
    safe_rerun()

# Main tabs
t1, t2, t3, t4 = st.tabs(["🎙️ صوت", "📝 نص", "📷 صورة", "🧠 تدريب/اختبار"])

# --------------- Voice tab (robust) ---------------
with t1:
    st.write("🎤 تحدث أو حمّل ملف صوتي، تأكد من السماح بالميكروفون في المتصفح.")
    st.caption("تنبيهات: استخدم Chrome/Edge المحدث، وتأكد من السماح بالميكروفون. يعمل فقط عبر HTTPS أو localhost.")

    if not mic_recorder:
        st.warning("مكوّن تسجيل الميكروفون (streamlit_mic_recorder) غير متوفر في بيئة التشغيل هذه.")
        st.info("لتفعيله محلياً: pip install streamlit-mic-recorder ثم أعد تشغيل التطبيق.")
        up_audio = st.file_uploader("أو حمّل ملف صوتي (wav/mp3/m4a/ogg):", type=["wav", "mp3", "m4a", "ogg"])
        if up_audio:
            st.audio(up_audio)
            if st.button("تحويل الملف إلى نص"):
                lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
                audio_bytes = up_audio.read()
                txt = speech_to_text_bytes(audio_bytes, lang)
                if txt:
                    st.success("تم تحويل الملف إلى نص:")
                    st.write(txt)
                    st.chat_message("user").write(txt)
                    update_xp(st.session_state.user_name, 10)
                    process_ai_response(txt, "voice")
                else:
                    st.error("تعذّر تحويل الصوت إلى نص. تأكد من جودة الملف أو جرّب ملفاً آخر.")
        st.stop()

    st.write("اضغط لبدء التسجيل ثم لإيقافه. عند الانتهاء سيتم عرض المقطع وتحويله إلى نص (إن أمكن).")
    aud = None
    try:
        aud = mic_recorder(start_prompt="🎤", stop_prompt="⏹️", key='m')
    except Exception as e:
        logger.exception("mic_recorder invocation failed: %s", e)
        st.error("فشل استدعاء مكوّن التسجيل. تحقق من Console في المتصفح لمعرفة الأخطاء.")
        up_audio = st.file_uploader("أو حمّل ملف صوتي (wav/mp3/m4a/ogg):", type=["wav", "mp3", "m4a", "ogg"])
        if up_audio:
            st.audio(up_audio)
            if st.button("تحويل الملف إلى نص"):
                lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
                audio_bytes = up_audio.read()
                txt = speech_to_text_bytes(audio_bytes, lang)
                if txt:
                    st.success("تم تحويل الملف إلى نص:")
                    st.write(txt)
                    st.chat_message("user").write(txt)
                    update_xp(st.session_state.user_name, 10)
                    process_ai_response(txt, "voice")
                else:
                    st.error("تعذّر تحويل الصوت إلى نص.")
        st.stop()

    if aud:
        audio_bytes = None
        if isinstance(aud, dict):
            audio_bytes = aud.get("bytes") or aud.get("data") or None
        elif isinstance(aud, (bytes, bytearray)):
            audio_bytes = aud
        if audio_bytes:
            if isinstance(audio_bytes, str):
                try:
                    if audio_bytes.startswith("data:"):
                        audio_bytes = audio_bytes.split(",", 1)[1]
                    audio_bytes = base64.b64decode(audio_bytes)
                except Exception:
                    logger.exception("Failed to decode audio bytes from recorder string.")
            if audio_bytes != st.session_state.get("last_audio_bytes"):
                st.session_state.last_audio_bytes = audio_bytes
                st.success("تم استلام تسجيل صوتي — تشغيل معاينة أدناه:")
                try:
                    st.audio(BytesIO(audio_bytes), format="audio/wav")
                except Exception:
                    try:
                        st.audio(BytesIO(audio_bytes))
                    except Exception:
                        st.warning("لا يمكن تشغيل المعاينة. ربما تنسيق الصوت غير مدعوم.")
                lang = "ar-EG" if st.session_state.language == "العربية" else "en-US"
                with st.spinner("يتم تحويل الصوت إلى نص..."):
                    txt = speech_to_text_bytes(audio_bytes, lang) if sr else None
                if txt:
                    st.write("تم تحويل الصوت إلى نص:")
                    st.write(txt)
                    st.chat_message("user").write(txt)
                    update_xp(st.session_state.user_name, 10)
                    process_ai_response(txt, "voice")
                else:
                    st.error("تعذّر تحويل التسجيل إلى نص. تحقق من إعدادات الميكروفون وجودة الصوت.")
                    st.info("اقتراحات: تأكد من السماح بالميكروفون، استخدم بيئة هادئة، أو جرّب رفع ملف صوتي بصيغة WAV/MP3.")
        else:
            st.info("لم يتم التسجيل بعد — اضغط على زر التسجيل وسمح للمتصفح بالوصول إلى الميكروفون إذا طُلب.")

# --- Text tab (stable input) ---
with t2:
    st.markdown("اكتب سؤالك نصياً ثم اضغط إرسال:")
    q_text = st.text_area("سؤالك:", key="text_question", height=120)
    if st.button("إرسال السؤال"):
        if q_text and q_text.strip():
            st.chat_message("user").write(q_text)
            update_xp(st.session_state.user_name, 5)
            process_ai_response(q_text, "text")
            # clear input for UX
            st.session_state["text_question"] = ""
        else:
            st.warning("الرجاء كتابة السؤال أولاً.")

# --- Image tab ---
with t3:
    up = st.file_uploader("حمّل صورة (png, jpg)", type=['png','jpg','jpeg'])
    if up:
        try:
            img = Image.open(up)
            st.image(img, width=300)
            if st.button("تحليل الصورة"):
                update_xp(st.session_state.user_name, 15)
                process_ai_response(["صِف الصورة وعلّم المفاهيم العلمية الموجودة فيها.", img], "image")
        except Exception:
            st.exception("فشل في فتح الصورة.")

# --- Training / MCQ tab ---
with t4:
    st.markdown("### 📝 أسئلة متعددة الاختيارات (MCQ)")
    colA, colB = st.columns(2)
    with colA:
        if st.button("توليد سؤال جديد"):
            process_ai_response(None, "mcq_generate")
    with colB:
        if st.session_state.get("q_active") and st.session_state.get("q_curr"):
            st.markdown("---")
            st.write(st.session_state.q_curr)
            ans = st.text_input("إجابتك (A/B/C/D):", key="mcq_ans")
            if st.button("تحقق الإجابة"):
                if ans:
                    process_ai_response({"answer": ans}, "mcq_check")
                else:
                    st.warning("اكتب إجابتك أولاً (A/B/C/D).")
        else:
            st.info("اضغط 'توليد سؤال جديد' لبدء.")

# Footer and housekeeping
st.markdown("---")
st.caption("AI Science Tutor Pro — محدث. احتفظ بمفاتيحك في st.secrets وراجع لوحة التشخيص إذا ظهرت أخطاء.")

try:
    if st.session_state.get("chat_history"):
        append_chat_history_local(st.session_state.get("user_name", "anonymous"), {"time": now_str(), "history": st.session_state.chat_history})
except Exception:
    logger.exception("Failed to persist session chat history.")
